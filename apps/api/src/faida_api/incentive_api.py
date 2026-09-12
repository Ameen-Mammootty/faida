"""The owner's incentive screen, served (M13, plan.md §8 D18; issue #8).

One read serves the whole `/incentive` screen - `GET /api/incentive` - the
dashboard's rule (M9): every figure on the screen comes out of one request,
so nothing on it can disagree with anything else on it. The scores, the pool
and the statement are derived on every read by `incentive.py` and stored
nowhere (C16); only what the owner typed and what the owner approved are
rows.

This ticket is the first block of that screen and the first door beside it:
the three role shares that split a pool between the manager, the supervisor
and the sales team (D2). The read grows a block per ticket from here - the
scheme month with its branch targets, the push weeks and their lists, and
each branch's statement - and every door lands beside it in the same shape:
the pure module decides, the route stores, the audit row names the actor.

Every refusal about what a share *is* - missing, negative, more decimals than
a share is kept to, three that do not add to a hundred - is the pure module's
own sentence, so the screen, the API and the tests can never word the same
refusal twice. The one sentence worded here is the wire's own ("that is not a
percentage"), which is where `menu.py` and `sales.py` word theirs too.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from . import incentive
from .auth import AuthContext, require_context
from .confirm import _parse_number
from .db import Database

router = APIRouter(prefix="/api", dependencies=[Depends(require_context)])
Context = Annotated[AuthContext, Depends(require_context)]


class RoleSharesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Optional on the wire so a share left out is refused in the pure
    # module's words ("the sales team share is missing: three percentages
    # summing to 100 are needed") rather than in Pydantic's.
    manager_pct: str | None = None
    supervisor_pct: str | None = None
    sales_pct: str | None = None


def _share(value: str | None, *, what: str):
    """A share as a number, or None when it was left out. A value that is not
    a number at all is refused here; a negative one is not - it parses, and
    the pure module refuses it in the sentence the screen already knows.

    The sign is peeled off rather than written into a second number grammar,
    so "how Faida reads a number the owner typed" stays one rule.
    """
    if value is None:
        return None
    text = value.strip()
    negative = text.startswith("-")
    number = _parse_number(text[1:] if negative else text)
    if number is None:
        raise HTTPException(
            status_code=422,
            detail=f"'{value}' is not a {what}: send a percentage, like \"40\"",
        )
    return -number if negative else number


def _shares_payload(row) -> dict | None:
    """The shares block: the three percentages as the pure module writes them,
    plus when they were last set."""
    if row is None:
        return None
    shares = incentive.Shares(row["manager_pct"], row["supervisor_pct"], row["sales_pct"])
    return {**incentive.shares_json(shares), "updated_at": row["updated_at"].isoformat()}


async def _read(db: Database, tenant_id: str) -> dict:
    return {"shares": _shares_payload(await db.get_role_shares(tenant_id=tenant_id))}


@router.get("/incentive")
async def read_incentive(request: Request, ctx: Context) -> dict:
    """The screen, for this tenant and no other: a tenant with no row of its
    own reads no shares, never another chain's."""
    db: Database = request.app.state.db
    return await _read(db, ctx.tenant_id)


@router.put("/incentive/shares")
async def set_role_shares(body: RoleSharesBody, request: Request, ctx: Context) -> dict:
    """The owner said how a pool is split. One row per tenant, replaced in
    place with an audit row naming them (D2).

    A scheme month already created is untouched: it snapshots the shares when
    it is created, which is how "applies from the next month" holds without a
    version table. Returns the whole read, so the screen refreshes from one
    shape.
    """
    db: Database = request.app.state.db
    manager = _share(body.manager_pct, what="manager share")
    supervisor = _share(body.supervisor_pct, what="supervisor share")
    sales = _share(body.sales_pct, what="sales team share")
    problem = incentive.shares_problem(manager, supervisor, sales)
    if problem is not None:
        raise HTTPException(status_code=422, detail=problem)
    await db.set_role_shares(
        tenant_id=ctx.tenant_id,
        manager_pct=manager,
        supervisor_pct=supervisor,
        sales_pct=sales,
        actor=ctx.actor,
    )
    return await _read(db, ctx.tenant_id)
