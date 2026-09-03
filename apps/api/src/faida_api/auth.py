"""M7 WP-73: the auth context every API read and write is scoped by.

`AuthContext` is the one thing a handler knows about who is calling: which
tenant their rows belong to, and the actor name that goes on every audit row
and provenance stamp they cause. Handlers never resolve a tenant themselves
and never name an actor themselves; both come from here, and both are
handed down to the db layer as required keyword arguments, so a query that
forgot its tenant does not compile.

**This wave's only source is the legacy shared token.** `require_context`
runs the C6 bearer check unchanged and resolves the seeded tenant, with
actor `console` - the same answers the API gave before, now carried on a
real type rather than looked up ad hoc in each handler. That is the
strangler step on purpose: the type and its plumbing are permanent, the
source is temporary. WP-70 replaces the body of `require_context` with a
verified Supabase token and the memberships row (migration 0018), and
nothing downstream changes - not the handlers, not the db signatures, not
the tenancy tests. Do not add token verification here before then.

A row outside `tenant_id` does not exist for the caller. The API answers
404, never 403: a 403 would confirm the row is there, which is the one bit
of information a wrong tenant must not get.
"""

import hmac
from dataclasses import dataclass

from fastapi import HTTPException, Request

#: C8 actor for the review screen while the API is one shared bearer token:
#: there is no person to name yet, so "console" is the honest answer, and it
#: becomes a real user id when WP-70 brings Supabase Auth. Deliberately never
#: taken from a client-supplied header: a name anyone holding the token can
#: choose looks like identity without being it, which is worse than admitting
#: we do not know yet.
CONSOLE_ACTOR = "console"


@dataclass(frozen=True)
class AuthContext:
    """Who is calling, resolved server-side, never from the client.

    `user_id` is None until WP-70: the shared token has no person behind it.
    `tenant_id` scopes every read and write. `actor` is the C8 name that
    lands on audit rows and provenance stamps."""

    user_id: str | None
    tenant_id: str
    actor: str


def require_api_token(request: Request) -> None:
    """C6 demo auth: one shared-secret bearer token, compared in constant
    time. No configured token means no access at all - misconfiguration must
    fail loudly, never open, exactly like the webhook app secret."""
    expected = request.app.state.settings.api_token
    header = request.headers.get("Authorization") or ""
    provided = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
    if not expected or not provided:
        raise HTTPException(status_code=401, detail="unauthorized")
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="unauthorized")


async def require_context(request: Request) -> AuthContext:
    """The one door: the token check first, then the tenant it stands for.

    The token check runs before anything touches the database, so a missing
    or wrong token is refused without a query. The tenant is the seeded
    default - the temporary source described above - and an empty tenants
    table is a deployment error, not a request error."""
    require_api_token(request)
    tenant_id = await request.app.state.db.default_tenant_id()
    if tenant_id is None:
        raise HTTPException(status_code=500, detail="no tenant seeded; run supabase/seed.sql")
    return AuthContext(user_id=None, tenant_id=tenant_id, actor=CONSOLE_ACTOR)
