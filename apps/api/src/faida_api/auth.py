"""M7: the auth context every API read and write is scoped by.

`AuthContext` is the one thing a handler knows about who is calling: which
tenant their rows belong to, and the actor name that goes on every audit row
and provenance stamp they cause. Handlers never resolve a tenant themselves
and never name an actor themselves; both come from here, and both are
handed down to the db layer as required keyword arguments, so a query that
forgot its tenant does not compile.

**The source is a Supabase access token, verified here, plus the
memberships row (WP-70).** The browser sends the user's own access token as
the bearer; the API checks its signature against the project's published
signing keys (the JWKS at `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`),
its issuer, its `authenticated` audience and its expiry, and only then asks
the database which tenant the token's subject belongs to. The API holds no
secret that could mint or forge a session: asymmetric algorithms only, and
a symmetric (HS256) token is refused outright, never as a fallback, because
the one secret that could verify it is the legacy JWT secret that also signs
the storage service key, and Railway must never hold anything that can sign
a login.

Three answers, each with one meaning. 401: no token, or one that fails
verification against a key we hold. 403: a real person with no membership.
503 "sign-in service unreachable": the keys could not be fetched and none
are cached, which is the only time the API cannot tell a good token from a
bad one and says so rather than guessing.

A row outside `tenant_id` does not exist for the caller. The API answers
404, never 403: a 403 would confirm the row is there, which is the one bit
of information a wrong tenant must not get.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import jwt
from fastapi import HTTPException, Request

from .config import Settings

log = logging.getLogger(__name__)

#: The only signature algorithms a token may carry. Both are asymmetric: the
#: public half verifies, the private half never leaves Supabase. HS256 is not
#: here and must never be added (Decision Log 2026-09-03).
ALLOWED_ALGORITHMS = ("ES256", "RS256")
#: JWK key types the cache will load; "oct" (a symmetric secret) is not one.
ASYMMETRIC_KEY_TYPES = ("EC", "RSA")
#: Supabase mints access tokens for signed-in people with this audience.
AUDIENCE = "authenticated"
#: Clock skew tolerated on `exp` and `iat`. Small on purpose: an expired
#: token is the browser's cue to refresh, and it refreshes per request.
JWT_LEEWAY_SECONDS = 30
#: A key id we do not hold triggers one JWKS refetch (the key may have
#: rotated), and never more than one a minute however many unknown ids
#: arrive: a flood of forged tokens must not become a flood of fetches.
JWKS_REFETCH_MIN_SECONDS = 60
JWKS_FETCH_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class AuthContext:
    """Who is calling, resolved server-side, never from the client.

    `user_id` is the verified token's subject (the Supabase auth user id).
    `tenant_id` scopes every read and write. `actor` is the C8 name that
    lands on audit rows and provenance stamps: `user:<user_id>`."""

    user_id: str | None
    tenant_id: str
    actor: str


def actor_for(user_id: str) -> str:
    return f"user:{user_id}"


class TokenVerifier:
    """Verifies Supabase access tokens against the project's JWKS.

    Keys are fetched with async httpx through an injected transport - the
    wa.py / storage.py convention, and the only shape the test suite can
    mock - never with PyJWT's own client, which does blocking I/O on the one
    event loop the API shares with the WhatsApp worker. The cache is in
    process, keyed by key id. `clock` is monotonic seconds, injected so the
    rate limit is testable by moving time."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        base = settings.supabase_url.rstrip("/")
        self.issuer = f"{base}/auth/v1"
        self.jwks_url = f"{self.issuer}/.well-known/jwks.json"
        self._http = httpx.AsyncClient(timeout=JWKS_FETCH_TIMEOUT_SECONDS, transport=transport)
        self._clock = clock
        # None until a fetch has succeeded; {} after one that published no
        # usable key (a project still on its legacy secret). The difference
        # is 503 versus 401: only the first means we could not find out.
        self._keys: dict[str, jwt.PyJWK] | None = None
        self._last_fetch_at: float | None = None
        # One fetch in flight at a time: a burst of misses waits for the one
        # refetch rather than each starting its own.
        self._fetch_lock = asyncio.Lock()

    async def close(self) -> None:
        await self._http.aclose()

    @property
    def has_keys(self) -> bool:
        return bool(self._keys)

    async def warm(self) -> None:
        """Best-effort prefetch at startup, so the first request after a
        deploy does not pay for the fetch and an outage at boot leaves the
        API answering 503 rather than crashing."""
        try:
            await self._fetch()
        except Exception as exc:  # noqa: BLE001 - startup must not die on a blip
            log.warning("JWKS warm-up failed; will retry on the first request: %s", exc)

    async def verify(self, token: str) -> str:
        """The token's subject if it verifies against a key we hold. Raises
        HTTPException 401 for anything that does not, 503 only when no key
        could be fetched and none is cached."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="unauthorized") from None
        # The algorithm is checked before any key is looked up: a symmetric
        # token never reaches the cache, and never costs a fetch.
        if header.get("alg") not in ALLOWED_ALGORITHMS:
            raise HTTPException(status_code=401, detail="unauthorized")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise HTTPException(status_code=401, detail="unauthorized")

        key = await self._key_for(kid)
        if key is None:
            raise HTTPException(status_code=401, detail="unauthorized")
        try:
            claims = jwt.decode(
                token,
                key.key,
                # The key's own algorithm, not the header's: an RS256 header
                # over an EC key is a forgery attempt, and must be a 401, not
                # a type error deep inside the library.
                algorithms=[key.algorithm_name],
                audience=AUDIENCE,
                issuer=self.issuer,
                leeway=JWT_LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            )
        except (jwt.PyJWTError, TypeError, ValueError):
            raise HTTPException(status_code=401, detail="unauthorized") from None
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub:
            raise HTTPException(status_code=401, detail="unauthorized")
        return sub

    async def _key_for(self, kid: str) -> jwt.PyJWK | None:
        key = (self._keys or {}).get(kid)
        if key is not None:
            return key
        await self._refetch()
        return (self._keys or {}).get(kid)

    async def _refetch(self) -> None:
        """One attempt per minute, whatever the outcome. A failure leaves the
        cached keys serving; a failure with nothing cached is the one case
        the API cannot answer, and says so with a 503."""
        async with self._fetch_lock:
            now = self._clock()
            due = (
                self._last_fetch_at is None or now - self._last_fetch_at >= JWKS_REFETCH_MIN_SECONDS
            )
            if due:
                self._last_fetch_at = now
                try:
                    await self._fetch()
                except Exception as exc:  # noqa: BLE001 - any transport failure is the same case
                    log.warning("JWKS fetch failed from %s: %s", self.jwks_url, exc)
            if self._keys is None:
                raise HTTPException(status_code=503, detail="sign-in service unreachable")

    async def _fetch(self) -> None:
        response = await self._http.get(self.jwks_url)
        response.raise_for_status()
        keys: dict[str, jwt.PyJWK] = {}
        for jwk in response.json().get("keys", []):
            kid = jwk.get("kid")
            if jwk.get("kty") not in ASYMMETRIC_KEY_TYPES or not kid:
                continue
            try:
                key = jwt.PyJWK(jwk)
            except jwt.PyJWKError as exc:
                log.warning("skipping unusable JWK %s: %s", kid, exc)
                continue
            if key.algorithm_name in ALLOWED_ALGORITHMS:
                keys[kid] = key
        if not keys:
            log.warning(
                "the JWKS at %s publishes no asymmetric signing key; "
                "is the project migrated to JWT signing keys?",
                self.jwks_url,
            )
        # Replace wholesale on success so a retired key stops verifying; on
        # failure this line is never reached and the old set stands.
        self._keys = keys


def bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization") or ""
    scheme, _, token = header.partition(" ")
    token = token.strip()
    if scheme != "Bearer" or not token:
        raise HTTPException(status_code=401, detail="unauthorized")
    return token


async def require_context(request: Request) -> AuthContext:
    """The one door: the token first, the membership second, the context.

    The signature check runs before anything touches the database, so a
    missing or forged token is refused without a query. The membership is
    read on every request, not once at login, so removing a person from a
    tenant takes effect on their next click."""
    token = bearer_token(request)
    user_id = await request.app.state.auth.verify(token)
    tenant_id = await request.app.state.db.membership_tenant_id(user_id)
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="no access")
    return AuthContext(user_id=user_id, tenant_id=tenant_id, actor=actor_for(user_id))
