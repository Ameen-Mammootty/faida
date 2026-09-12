"""The owner's incentive screen, served (M13, plan.md §8 D18; issues #8, #9).

One read serves the whole `/incentive` screen - `GET /api/incentive?month=` -
the dashboard's rule (M9): every figure on the screen comes out of one
request, so nothing on it can disagree with anything else on it. The scores,
the pool and the statement are derived on every read by `incentive.py` and
stored nowhere (C16); only what the owner typed and what the owner approved
are rows.

Two blocks are served so far and the read grows one per ticket. The role
shares that split a pool between the manager, the supervisor and the sales
team (D2, issue #8), and the scheme month: a calendar month with a net sales
target, a percentage of net sales above it and an optional cap per branch,
its push weeks laid out Monday to Sunday clipped to the month, and the shares
snapshotted the day it was created (D3, D4, D5, issue #9). The push lists
inside those weeks and each branch's statement land in the tickets after
this one, out of this same request.

Every refusal about what a figure *is* - a share that does not add to a
hundred, a negative target, a percentage over a hundred, a branch with no
target, a month already created - is the pure module's own sentence, so a
refusal is worded once in the whole product. The two sentences worded here
are the wire's own ("that is not a percentage", "that is not a month"), which
is where `menu.py` and `sales.py` word theirs too.

The reads, enumerated, because the dashboard's rule is that a screen's read
is flat whatever the chain's size: the currency, the branches with their
pauses, the tenant's scheme months for the picker, the previous month's sales
days for the advice figure, and - only when a month exists for the month in
view - that month, its branch targets and its push weeks. Seven queries at
most, whatever the number of branches or weeks.
"""

import datetime
import zoneinfo
from decimal import Decimal
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from . import incentive
from .auth import AuthContext, require_context
from .confirm import DEFAULT_TIMEZONE, _parse_number
from .db import Database

router = APIRouter(prefix="/api", dependencies=[Depends(require_context)])
Context = Annotated[AuthContext, Depends(require_context)]


# --- what day it is ---------------------------------------------------------------


def _local_date(moment: datetime.datetime, timezone_name: str | None) -> datetime.date:
    try:
        return moment.astimezone(zoneinfo.ZoneInfo(timezone_name or DEFAULT_TIMEZONE)).date()
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return moment.astimezone(zoneinfo.ZoneInfo(DEFAULT_TIMEZONE)).date()


def _today(branches: list[asyncpg.Record]) -> datetime.date:
    """The day the screen's freeze rule is measured against: the latest local
    date across the chain's branches.

    The latest rather than any one branch's, because a push week that has
    started *anywhere* in the chain has staff pushing its dishes, and the
    whole point of the freeze is that nobody finds the dish they pushed on
    Wednesday dropped on Thursday (D5). A chain in one timezone, which every
    pilot branch is, sees no difference.
    """
    now = datetime.datetime.now(datetime.UTC)
    return max((_local_date(now, row["timezone"]) for row in branches), default=now.date())


# --- what the owner typed ----------------------------------------------------------


def _typed(value: str | None, *, what: str, example: str) -> Decimal | None:
    """A figure the owner typed, or None when the box was left empty.

    A value that is not a number at all is refused here, because "that is not
    a number" is the wire's own complaint. A negative one is not: it parses,
    and the pure module refuses it in the sentence the screen already knows.
    The sign is peeled off rather than written into a second number grammar,
    so "how Faida reads a number the owner typed" stays one rule.
    """
    if value is None or value.strip() == "":
        return None
    text = value.strip()
    negative = text.startswith("-")
    number = _parse_number(text[1:] if negative else text)
    if number is None:
        raise HTTPException(
            status_code=422,
            detail=f"'{value}' is not a {what}: send a figure, like \"{example}\"",
        )
    return -number if negative else number


def _share(value: str | None, *, what: str) -> Decimal | None:
    return _typed(value, what=what, example="40")


def _month(key: str) -> datetime.date:
    month = incentive.parse_month_key(key)
    if month is None:
        raise HTTPException(
            status_code=422, detail=f"'{key}' is not a month: send one like \"2026-09\""
        )
    return month


# --- the blocks the read is made of ------------------------------------------------


def _shares_payload(row: asyncpg.Record | None) -> dict | None:
    """The shares block: the three percentages as the pure module writes them,
    plus when they were last set."""
    if row is None:
        return None
    shares = incentive.Shares(row["manager_pct"], row["supervisor_pct"], row["sales_pct"])
    return {**incentive.shares_json(shares), "updated_at": row["updated_at"].isoformat()}


def _shares_of(row: asyncpg.Record) -> incentive.Shares:
    return incentive.Shares(row["manager_pct"], row["supervisor_pct"], row["sales_pct"])


async def _previous_month_net_sales(
    db: Database, tenant_id: str, month: datetime.date
) -> dict[str, Decimal]:
    """Each branch's net sales in the calendar month before the one in view,
    for the advice beside the target box (D3). A branch with no day loaded is
    absent from the mapping and says so in words rather than reading as a
    zero it did not earn."""
    end = incentive.month_start(month) - datetime.timedelta(days=1)
    totals: dict[str, Decimal] = {}
    for row in await db.list_sales_days(
        tenant_id=tenant_id, date_from=incentive.month_start(end), date_to=end
    ):
        totals[row["branch_id"]] = totals.get(row["branch_id"], Decimal(0)) + row["net_sales"]
    return totals


def _branches_payload(
    branches: list[asyncpg.Record], previous: dict[str, Decimal], currency: str
) -> list[dict]:
    return [
        incentive.branch_json(
            branch_id=row["id"],
            name=row["name"],
            timezone=row["timezone"],
            paused_at=row["paused_at"],
            previous_month_net_sales=previous.get(row["id"]),
            currency=currency,
        )
        for row in branches
    ]


def _scheme_month(
    row: asyncpg.Record, targets: list[asyncpg.Record], weeks: list[asyncpg.Record]
) -> incentive.SchemeMonth:
    """The rows as the pure module reads them. The weeks are read back from
    `push_weeks` rather than laid out again, so the screen shows the month the
    database holds and a week always has the id a push list is set on."""
    return incentive.SchemeMonth(
        scheme_month_id=row["id"],
        month=row["month"],
        shares=_shares_of(row),
        targets={
            target["branch_id"]: incentive.BranchTargets(
                branch_id=target["branch_id"],
                net_sales_target=target["net_sales_target"],
                above_target_pct=target["above_target_pct"],
                cap=target["cap"],
            )
            for target in targets
        },
        weeks=tuple(
            incentive.PushWeek(
                push_week_id=week["id"],
                window=incentive.Window(week["start_date"], week["end_date"]),
                items=(),
            )
            for week in weeks
        ),
    )


async def _read(db: Database, tenant_id: str, month_key: str | None) -> dict:
    """The whole screen for one month. A month key that is not this tenant's
    is not an error: it reads as no scheme month, with the branches and the
    shares still there to create one with - which is also how another chain's
    month looks from here."""
    currency = await db.tenant_currency(tenant_id) or ""
    branches = await db.list_incentive_branches(tenant_id=tenant_id)
    today = _today(branches)
    month = _month(month_key) if month_key is not None else incentive.month_start(today)
    months = await db.list_scheme_months(tenant_id=tenant_id)
    previous = await _previous_month_net_sales(db, tenant_id, month)

    row = next((m for m in months if m["month"] == month), None)
    scheme_month = None
    if row is not None:
        scheme = _scheme_month(
            row,
            await db.list_scheme_month_targets(row["id"], tenant_id=tenant_id),
            await db.list_push_weeks(row["id"], tenant_id=tenant_id),
        )
        scheme_month = incentive.scheme_month_json(
            scheme,
            created_at=row["created_at"],
            today=today,
            # The push lists and the statements fill in with the tickets that
            # build them; the weeks are empty until then, so nothing here
            # reads a menu item's kept figure or a branch's sales days.
            kept={},
            statements=[],
            currency=currency,
        )

    return {
        "month": incentive.month_key(month),
        "month_words": incentive.month_words(month),
        "today": today.isoformat(),
        "months": [
            {
                "id": m["id"],
                "month": incentive.month_key(m["month"]),
                "words": incentive.month_words(m["month"]),
            }
            for m in months
        ],
        "shares": _shares_payload(await db.get_role_shares(tenant_id=tenant_id)),
        "branches": _branches_payload(branches, previous, currency),
        "scheme_month": scheme_month,
    }


# --- the doors ---------------------------------------------------------------------


class RoleSharesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Optional on the wire so a share left out is refused in the pure
    # module's words ("the sales team share is missing: three percentages
    # summing to 100 are needed") rather than in Pydantic's.
    manager_pct: str | None = None
    supervisor_pct: str | None = None
    sales_pct: str | None = None


class BranchTargetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: str
    # All three optional for the same reason: an empty box is a sentence the
    # pure module owns, naming the branch it belongs to.
    net_sales_target: str | None = None
    above_target_pct: str | None = None
    cap: str | None = None


class SchemeMonthBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: str
    targets: list[BranchTargetBody] = []


@router.get("/incentive")
async def read_incentive(request: Request, ctx: Context, month: str | None = None) -> dict:
    """The screen, for this tenant and no other: a tenant with no rows of its
    own reads no shares and no scheme month, never another chain's."""
    db: Database = request.app.state.db
    return await _read(db, ctx.tenant_id, month)


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
    return await _read(db, ctx.tenant_id, None)


@router.post("/incentive/months", status_code=201)
async def create_scheme_month(body: SchemeMonthBody, request: Request, ctx: Context) -> dict:
    """The owner created the month the team is scored and paid on (D4).

    Everything the month is scored against arrives in this one request and
    nothing edits it afterwards: each branch's net sales target, the
    percentage of net sales above it that goes to the pool and the optional
    cap, the role shares in force today snapshotted onto the month, and the
    push weeks laid out Monday to Sunday clipped to the month (D5) so every
    week is a thing a push list can be set on and a card can name. A month may
    be created after it has begun - a late month still scores the whole
    calendar month, and the weeks that have already ended simply carry no
    list.

    Returns the whole read for the month created, so the screen renders it
    from one shape.
    """
    db: Database = request.app.state.db
    month = _month(body.month)

    shares_row = await db.get_role_shares(tenant_id=ctx.tenant_id)
    if shares_row is None:
        raise HTTPException(status_code=422, detail=incentive.SHARES_NOT_SET)

    branches = await db.list_incentive_branches(tenant_id=ctx.tenant_id)
    typed = [
        incentive.TypedTarget(
            branch_id=target.branch_id,
            net_sales_target=_typed(
                target.net_sales_target, what="net sales target", example="50000"
            ),
            above_target_pct=_typed(target.above_target_pct, what="percentage", example="10"),
            cap=_typed(target.cap, what="cap", example="1500"),
        )
        for target in body.targets
    ]
    problem = incentive.branch_targets_problem({row["id"]: row["name"] for row in branches}, typed)
    if problem is not None:
        raise HTTPException(status_code=422, detail=problem)

    if await db.scheme_month_for(month, tenant_id=ctx.tenant_id) is not None:
        raise HTTPException(status_code=422, detail=incentive.month_taken_sentence(month))

    shares = _shares_of(shares_row)
    try:
        await db.create_scheme_month(
            tenant_id=ctx.tenant_id,
            month=month,
            shares={
                "manager_pct": shares.manager_pct,
                "supervisor_pct": shares.supervisor_pct,
                "sales_pct": shares.sales_pct,
            },
            targets=[
                {
                    "branch_id": target.branch_id,
                    "net_sales_target": target.net_sales_target,
                    "above_target_pct": target.above_target_pct,
                    "cap": target.cap,
                }
                for target in typed
            ],
            weeks=[(window.start, window.end) for window in incentive.push_weeks(month)],
            actor=ctx.actor,
        )
    except asyncpg.UniqueViolationError:
        # Two creates for the same month at once: the database is the one
        # place that can decide, and the owner is told what it decided.
        raise HTTPException(status_code=422, detail=incentive.month_taken_sentence(month)) from None
    return await _read(db, ctx.tenant_id, incentive.month_key(month))
