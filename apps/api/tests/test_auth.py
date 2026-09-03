"""M7 WP-70: the API knows who is asking, and never asks the client.

`require_context`'s source is a Supabase access token verified against the
project's public signing keys, then the memberships row for the token's
subject. Everything a client could say about itself - a header naming a
tenant or an actor, a token it signed with a secret of its own choosing - is
ignored or refused; the only thing the API believes is a signature it can
check against a key it fetched from the sign-in service.

Tokens here are minted with a local key pair whose public half is served
through a mocked JWKS transport (`conftest.FakeJwks`), the wa.py / storage.py
convention: the verifier is the real one, the network is not.

Three answers, each with one meaning:
- 401: no token, or one that fails verification against a key we hold
- 403: a real person with no membership anywhere
- 503: the sign-in service is unreachable and we hold no keys at all
"""

import asyncio
import base64
import hashlib
import hmac
import json
import time
import uuid

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import APIRouter, FastAPI

from faida_api.api import Context
from faida_api.api import router as api_router
from faida_api.auth import JWKS_REFETCH_MIN_SECONDS, TokenVerifier
from faida_api.config import Settings

from .conftest import DEMO_TENANT_ID, TEST_USER_ID, FakeJwks, requires_db, wire_auth

TENANT_A = DEMO_TENANT_ID
TENANT_B = "b0000000-0000-0000-0000-000000000001"

# A route that reports the context it was handed, so a test reads the
# tenant and actor straight off the door rather than inferring them.
probe = APIRouter(prefix="/api")


@probe.get("/whoami")
async def whoami(ctx: Context) -> dict:
    return {"user_id": ctx.user_id, "tenant_id": ctx.tenant_id, "actor": ctx.actor}


class FakeDb:
    """Only what `require_context` reads: the membership lookup."""

    def __init__(self, memberships: dict[str, str]):
        self.memberships = memberships

    async def membership_tenant_id(self, user_id: str) -> str | None:
        return self.memberships.get(user_id)


class Clock:
    """An injected monotonic clock, so the once-a-minute refetch rule is
    tested by moving time rather than by waiting."""

    def __init__(self):
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def tick(self, seconds: float) -> None:
        self.now += seconds


def rig(jwks: FakeJwks, *, memberships: dict[str, str] | None = None, clock: Clock | None = None):
    settings = Settings(supabase_url="http://supabase.test")
    app = FastAPI()
    app.include_router(api_router)
    app.include_router(probe)
    app.state.settings = settings
    app.state.db = FakeDb({TEST_USER_ID: TENANT_A} if memberships is None else memberships)
    app.state.auth = TokenVerifier(settings, transport=jwks.transport(), clock=clock or Clock())
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return app, client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def hmac_token(header: dict, payload: dict, secret: bytes) -> str:
    """A JWT signed with plain HMAC-SHA256, assembled by hand."""
    signing_input = f"{b64url(json.dumps(header).encode())}.{b64url(json.dumps(payload).encode())}"
    signature = hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{b64url(signature)}"


# --- 401: no token, or one that fails against a key we hold --------------------


async def test_no_token_is_401_before_any_key_is_fetched():
    jwks = FakeJwks()
    _, client = rig(jwks)
    assert (await client.get("/api/whoami")).status_code == 401
    assert (await client.get("/api/whoami", headers={"Authorization": ""})).status_code == 401
    assert (
        await client.get("/api/whoami", headers={"Authorization": "Bearer "})
    ).status_code == 401
    # Not a bearer scheme at all, and a bare token with no scheme.
    token = jwks.mint()
    assert (
        await client.get("/api/whoami", headers={"Authorization": f"Basic {token}"})
    ).status_code == 401
    assert (await client.get("/api/whoami", headers={"Authorization": token})).status_code == 401
    assert jwks.fetches == 0


async def test_a_malformed_token_is_401():
    jwks = FakeJwks()
    _, client = rig(jwks)
    for junk in (
        "garbage",
        "a.b",
        "a.b.c",
        "eyJhbGciOiJFUzI1NiJ9.e30.",
        jwks.mint()[:-10] + "tampered",
    ):
        assert (await client.get("/api/whoami", headers=bearer(junk))).status_code == 401, junk


async def test_an_expired_token_is_401_and_a_fresh_one_is_not():
    jwks = FakeJwks()
    _, client = rig(jwks)
    expired = jwks.mint(expires_in=-120)  # past the small leeway
    assert (await client.get("/api/whoami", headers=bearer(expired))).status_code == 401
    assert (await client.get("/api/whoami", headers=bearer(jwks.mint()))).status_code == 200


async def test_a_wrong_issuer_is_401():
    jwks = FakeJwks()
    _, client = rig(jwks)
    other = jwks.mint(issuer="http://other-project.test/auth/v1")
    assert (await client.get("/api/whoami", headers=bearer(other))).status_code == 401


async def test_a_wrong_or_missing_audience_is_401():
    jwks = FakeJwks()
    _, client = rig(jwks)
    for audience in ("anon", "service_role", None):
        token = jwks.mint(audience=audience)
        assert (await client.get("/api/whoami", headers=bearer(token))).status_code == 401, audience


async def test_hs256_is_refused_outright_never_as_a_fallback():
    """A symmetric token is refused before any key is looked up: the API
    holds no secret that could verify one, and a JWKS carrying a symmetric
    key must not make it hold one either."""
    jwks = FakeJwks()
    _, client = rig(jwks)
    assert (await client.get("/api/whoami", headers=bearer(jwks.mint()))).status_code == 200
    fetched = jwks.fetches

    # Signed with a shared secret under the known key id.
    hs = jwks.mint(alg="HS256", key="a-legacy-jwt-secret-of-the-recommended-length")
    assert (await client.get("/api/whoami", headers=bearer(hs))).status_code == 401

    # The classic confusion attack: HS256 with the *public* key as the
    # secret. PyJWT refuses to mint one, so the attacker's token is built by
    # hand, exactly as an attacker would.
    public_pem = jwks.private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    confused = hmac_token(
        {"alg": "HS256", "kid": jwks.kid, "typ": "JWT"},
        {
            "iss": jwks.issuer,
            "sub": TEST_USER_ID,
            "aud": "authenticated",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        public_pem,
    )
    assert (await client.get("/api/whoami", headers=bearer(confused))).status_code == 401

    # Neither refusal cost a key fetch.
    assert jwks.fetches == fetched

    # And a symmetric key published in the JWKS is never loaded.
    secret = "a-shared-secret-published-by-mistake-in-a-jwks"
    jwks.keys.append({"kty": "oct", "kid": "hs-key", "alg": "HS256", "k": b64url(secret.encode())})
    hs_known = jwks.mint(alg="HS256", key=secret, kid="hs-key")
    assert (await client.get("/api/whoami", headers=bearer(hs_known))).status_code == 401


async def test_a_token_signed_by_another_key_under_the_same_kid_is_401():
    jwks = FakeJwks()
    impostor = FakeJwks(kid=jwks.kid)  # same issuer, same key id, another key pair
    _, client = rig(jwks)
    assert (await client.get("/api/whoami", headers=bearer(impostor.mint()))).status_code == 401
    # RS256 is an allowed algorithm, but not over a key we do not hold: an
    # RSA signature under the EC key's id is a 401, not a library error.
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwks.mint(alg="RS256", key=rsa_key)
    assert (await client.get("/api/whoami", headers=bearer(forged))).status_code == 401


# --- the key cache: one refetch on a miss, once a minute, stale on failure ------


async def test_an_unknown_kid_refetches_exactly_once_then_401():
    jwks = FakeJwks()
    clock = Clock()
    _, client = rig(jwks, clock=clock)
    assert (await client.get("/api/whoami", headers=bearer(jwks.mint()))).status_code == 200
    assert jwks.fetches == 1

    clock.tick(JWKS_REFETCH_MIN_SECONDS + 1)
    unknown = jwks.mint(kid="not-published")
    assert (await client.get("/api/whoami", headers=bearer(unknown))).status_code == 401
    assert jwks.fetches == 2  # one refetch, because the key might have rotated
    assert (await client.get("/api/whoami", headers=bearer(unknown))).status_code == 401
    assert jwks.fetches == 2  # and no second one inside the minute


async def test_a_rotated_key_verifies_after_one_refetch():
    jwks = FakeJwks()
    clock = Clock()
    _, client = rig(jwks, clock=clock)
    assert (await client.get("/api/whoami", headers=bearer(jwks.mint()))).status_code == 200

    new_key = ec.generate_private_key(ec.SECP256R1())
    jwks.keys.append(FakeJwks.public_jwk(new_key, "rotated-key"))
    rotated = jwks.mint(kid="rotated-key", key=new_key)
    clock.tick(JWKS_REFETCH_MIN_SECONDS + 1)
    assert (await client.get("/api/whoami", headers=bearer(rotated))).status_code == 200
    assert jwks.fetches == 2
    # Now cached: the old key and the new one both verify without a fetch.
    assert (await client.get("/api/whoami", headers=bearer(jwks.mint()))).status_code == 200
    assert (await client.get("/api/whoami", headers=bearer(rotated))).status_code == 200
    assert jwks.fetches == 2


async def test_the_refetch_rate_limit_holds_under_a_burst_of_unknown_kids():
    jwks = FakeJwks()
    clock = Clock()
    _, client = rig(jwks, clock=clock)
    assert (await client.get("/api/whoami", headers=bearer(jwks.mint()))).status_code == 200
    clock.tick(JWKS_REFETCH_MIN_SECONDS + 1)

    burst = [jwks.mint(kid=f"kid-{uuid.uuid4()}") for _ in range(25)]
    responses = await asyncio.gather(
        *(client.get("/api/whoami", headers=bearer(token)) for token in burst)
    )
    assert {response.status_code for response in responses} == {401}
    assert jwks.fetches == 2  # the burst bought exactly one refetch

    # The known key kept working throughout, and still costs nothing.
    assert (await client.get("/api/whoami", headers=bearer(jwks.mint()))).status_code == 200
    assert jwks.fetches == 2

    # A minute later, one more miss earns one more refetch.
    clock.tick(JWKS_REFETCH_MIN_SECONDS + 1)
    assert (await client.get("/api/whoami", headers=bearer(burst[0]))).status_code == 401
    assert jwks.fetches == 3


async def test_a_fetch_failure_with_a_warm_cache_still_verifies():
    """A Supabase blip must not read as a wrong password to everyone signed
    in: the keys we hold keep serving until the fetch works again."""
    jwks = FakeJwks()
    clock = Clock()
    _, client = rig(jwks, clock=clock)
    assert (await client.get("/api/whoami", headers=bearer(jwks.mint()))).status_code == 200

    jwks.down = True
    clock.tick(JWKS_REFETCH_MIN_SECONDS + 1)
    # A miss tries the refetch, fails, and answers from what is cached: 401,
    # because the token is not verifiable against a key we hold - not 503.
    unknown = jwks.mint(kid="not-published")
    assert (await client.get("/api/whoami", headers=bearer(unknown))).status_code == 401
    assert jwks.fetches == 2
    # The known key is unaffected by the outage.
    assert (await client.get("/api/whoami", headers=bearer(jwks.mint()))).status_code == 200


async def test_a_fetch_failure_with_an_empty_cache_is_503_not_401():
    jwks = FakeJwks()
    jwks.down = True
    clock = Clock()
    _, client = rig(jwks, clock=clock)
    response = await client.get("/api/whoami", headers=bearer(jwks.mint()))
    assert response.status_code == 503
    assert response.json()["detail"] == "sign-in service unreachable"
    assert jwks.fetches == 1
    # Inside the minute the answer is the same and costs no further attempt.
    assert (await client.get("/api/whoami", headers=bearer(jwks.mint()))).status_code == 503
    assert jwks.fetches == 1

    # The service comes back: the next attempt after the minute fills the cache.
    jwks.down = False
    clock.tick(JWKS_REFETCH_MIN_SECONDS + 1)
    assert (await client.get("/api/whoami", headers=bearer(jwks.mint()))).status_code == 200
    assert jwks.fetches == 2

    # A garbage token still never costs a fetch, whatever the cache holds.
    assert (await client.get("/api/whoami", headers=bearer("garbage"))).status_code == 401
    assert jwks.fetches == 2


async def test_a_published_jwks_with_no_asymmetric_key_verifies_nothing():
    """The state of a project still on its legacy JWT secret: the JWKS is
    published and empty. Every token is then 401 - not 503, the service
    answered - and the fix is the dashboard migration, not a code change."""
    jwks = FakeJwks()
    jwks.keys.clear()
    _, client = rig(jwks)
    assert (await client.get("/api/whoami", headers=bearer(jwks.mint()))).status_code == 401
    assert jwks.fetches == 1


# --- who the token is, and where they belong ------------------------------------


async def test_the_context_comes_from_the_token_and_the_membership_never_from_a_header():
    jwks = FakeJwks()
    _, client = rig(jwks)
    headers = {
        **bearer(jwks.mint()),
        "X-Tenant-Id": TENANT_B,
        "X-Actor": "someone-else",
        "X-User-Id": str(uuid.uuid4()),
    }
    response = await client.get("/api/whoami", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "user_id": TEST_USER_ID,
        "tenant_id": TENANT_A,
        "actor": f"user:{TEST_USER_ID}",
    }


async def test_a_real_person_with_no_membership_is_403():
    jwks = FakeJwks()
    _, client = rig(jwks, memberships={})
    response = await client.get("/api/whoami", headers=bearer(jwks.mint(sub=str(uuid.uuid4()))))
    assert response.status_code == 403
    assert response.json()["detail"] == "no access"


# --- against the real memberships table ------------------------------------------


@pytest.fixture
def api(settings, db):
    app = FastAPI()
    app.include_router(api_router)
    app.include_router(probe)
    app.state.settings = settings
    app.state.db = db
    wire_auth(app)
    from .conftest import JWKS

    return JWKS, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@requires_db
async def test_a_valid_token_with_a_membership_lands_in_its_own_tenant_as_the_user(api, db):
    jwks, client = api
    await db.pool.execute(
        "insert into tenants (id, name, currency) values ($1, 'Other Chain', 'AED')", TENANT_B
    )
    other_user = str(uuid.uuid4())
    await db.pool.execute(
        "insert into memberships (tenant_id, user_id) values ($1, $2)", TENANT_B, other_user
    )

    mine = await client.get("/api/whoami", headers=bearer(jwks.mint()))
    assert mine.json() == {
        "user_id": TEST_USER_ID,
        "tenant_id": TENANT_A,
        "actor": f"user:{TEST_USER_ID}",
    }
    theirs = await client.get("/api/whoami", headers=bearer(jwks.mint(sub=other_user)))
    assert theirs.json() == {
        "user_id": other_user,
        "tenant_id": TENANT_B,
        "actor": f"user:{other_user}",
    }

    # And what the door writes carries the same name: an audit row in the
    # member's tenant, signed by the user id, not by "console".
    created = await client.post(
        "/api/ingredients",
        json={"name": "Cardamom", "unit": "g"},
        headers=bearer(jwks.mint(sub=other_user)),
    )
    assert created.status_code == 201, created.text
    event = await db.pool.fetchrow(
        "select tenant_id::text as tenant_id, actor from audit_events "
        "where action = 'ingredient.created'"
    )
    assert (event["tenant_id"], event["actor"]) == (TENANT_B, f"user:{other_user}")


@requires_db
async def test_a_valid_token_with_no_membership_row_is_403_and_writes_nothing(api, db):
    jwks, client = api
    stranger = jwks.mint(sub=str(uuid.uuid4()))
    response = await client.post(
        "/api/ingredients", json={"name": "Cardamom", "unit": "g"}, headers=bearer(stranger)
    )
    assert response.status_code == 403
    assert await db.pool.fetchval("select count(*) from ingredients") == 0
    # Removal is immediate: the membership is read per request, not per login.
    await db.pool.execute("delete from memberships where user_id = $1", TEST_USER_ID)
    assert (await client.get("/api/whoami", headers=bearer(jwks.mint()))).status_code == 403
