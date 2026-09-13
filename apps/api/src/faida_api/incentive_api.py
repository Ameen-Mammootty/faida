"""The owner's incentive screen, served (M13, plan.md §8 D18; issues #8, #9,
#10, #11, #12).

One read serves the whole `/incentive` screen - `GET /api/incentive?month=` -
the dashboard's rule (M9): every figure on the screen comes out of one
request, so nothing on it can disagree with anything else on it. The scores,
the pool and the statement are derived on every read by `incentive.py` and
stored nowhere (C16); only what the owner typed and what the owner approved
are rows.

Four blocks. The role shares that split a pool between the manager, the
supervisor and the sales team (D2, issue #8); the scheme month: a calendar
month with a net sales target, a percentage of net sales above it and an
optional cap per branch, its push weeks laid out Monday to Sunday clipped to
the month, and the shares snapshotted the day it was created (D3, D4, D5,
issue #9); each week's push list with the menu beside it to build the next
one from (D6, D7, issue #10); and each branch's statement for the month -
what the push weeks scored, what the month sold, what the pool has earned so
far, and how many of the month's days are loaded (D9, D10, D11, issue #11);
and the approval door, which is the only way a statement becomes final (D11,
D12, issue #12).

A statement is read and never stored, which is the whole of C16: the screen
cannot disagree with the sales days because it *is* the sales days, re-added
on every request. It is provisional until every calendar day of the month is
loaded for that branch and says how many are; it is final only once the owner
has approved it, and then what is shown is the figures as approved - what was
paid - with the live ones beside them when a day has been replaced since.

What a plate keeps after ingredients - the figure beside every rate box, so
a rate is chosen as a share of what the dish actually earns - comes from
`menu._menu_context`, the one costing path in the product. The Menu screen
and this one therefore print the same figure for the same dish by
construction, and neither can drift from the other.

Every refusal about what a figure *is* - a share that does not add to a
hundred, a negative target, a percentage over a hundred, a branch with no
target, a month already created, a dish with no till name mapped to it, a
week already under way, a month with a day missing, an approval with no
reason, a statement already final - is the pure module's own sentence, so a refusal is
worded once in the whole product. The two sentences worded here are the
wire's own ("that is not a percentage", "that is not a month"), which is
where `menu.py` and `sales.py` word theirs too.

The reads, enumerated, because the dashboard's rule is that a screen's read
is flat whatever the chain's size: the currency, the branches with their
pauses, the tenant's scheme months for the picker, the previous month's sales
days for the advice figure, the costed menu with its till mapping, and - only
when a month exists for the month in view - that month, its branch targets,
its push weeks and their lists, then the month's loaded days, its item-days
and its approvals, which are the whole of every branch's statement. Nineteen
queries at most, whatever the number of branches, weeks, dishes, push items
or statements.
"""

import datetime
import uuid
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
from .menu import _menu_context

router = APIRouter(prefix="/api", dependencies=[Depends(require_context)])
Context = Annotated[AuthContext, Depends(require_context)]


# --- what day it is ---------------------------------------------------------------


def _local_date(moment: datetime.datetime, timezone_name: str | None) -> datetime.date:
    try:
        return moment.astimezone(zoneinfo.ZoneInfo(timezone_name or DEFAULT_TIMEZONE)).date()
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return moment.astimezone(zoneinfo.ZoneInfo(DEFAULT_TIMEZONE)).date()


def _now() -> datetime.datetime:
    """The one clock this screen reads.

    A named seam rather than a call inlined below, because the freeze rule is
    a rule about a *date*: the hour a week stops being re-aimable is a
    boundary, and a boundary with no clock to set cannot be proven at the
    boundary.
    """
    return datetime.datetime.now(datetime.UTC)


def _today(branches: list[asyncpg.Record]) -> datetime.date:
    """The day the screen's freeze rule is measured against: the latest local
    date across the chain's branches.

    The latest rather than any one branch's, because a push week that has
    started *anywhere* in the chain has staff pushing its dishes, and the
    whole point of the freeze is that nobody finds the dish they pushed on
    Wednesday dropped on Thursday (D5). A chain in one timezone, which every
    pilot branch is, sees no difference; a chain that straddles a date line
    is held to the branch that got to Monday first.
    """
    now = _now()
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


class Menu:
    """The whole menu as the push list is built and refused against, costed
    once per request (D6, D7).

    Three things come out of one costing: what each plate keeps after
    ingredients (the figure beside the rate box, fils-precise, or nothing at
    all when the dish is not costed), whether a till name maps to the dish,
    and whether it is archived. The costing is `menu._menu_context`, the one
    path in the product that prices a plate, so this screen's figure for a
    dish is the Menu screen's own figure and can never be a second opinion.
    """

    def __init__(self, rows: list[asyncpg.Record], plates: dict, mapped: set[str]):
        self.rows = rows
        self.kept: dict[str, Decimal | None] = {
            row["id"]: (None if row["id"] not in plates else plates[row["id"]].margin)
            for row in rows
        }
        self.facts: dict[str, incentive.MenuFact] = {
            row["id"]: incentive.MenuFact(
                name=row["name"],
                archived=row["archived_at"] is not None,
                mapped=row["id"] in mapped,
            )
            for row in rows
        }

    def payload(self, currency: str) -> list[dict]:
        """The picker: the live dishes grouped by the menu's own category,
        `Other` last (D6). An archived dish is left out - it cannot be pushed,
        so offering it would only be a refusal waiting to happen."""
        return incentive.group_by_category(
            [
                incentive.menu_item_json(
                    menu_item_id=row["id"],
                    name=row["name"],
                    category=row["category"],
                    kept_per_plate=self.kept.get(row["id"]),
                    mapped=self.facts[row["id"]].mapped,
                    currency=currency,
                )
                for row in self.rows
                if row["archived_at"] is None
            ]
        )


async def _menu(db: Database, tenant_id: str) -> Menu:
    rows, _, plates, _, _, _ = await _menu_context(db, tenant_id)
    return Menu(rows, plates, await db.mapped_menu_item_ids(tenant_id=tenant_id))


def _scheme_month(
    row: asyncpg.Record,
    targets: list[asyncpg.Record],
    weeks: list[asyncpg.Record],
    items: list[asyncpg.Record],
    item_targets: list[asyncpg.Record],
) -> incentive.SchemeMonth:
    """The rows as the pure module reads them. The weeks are read back from
    `push_weeks` rather than laid out again, so the screen shows the month the
    database holds and a week always has the id a push list is set on.

    A push item's name, category, archived flag and till mapping are read
    fresh with it and never stored on the row: a dish taken off the menu or
    unmapped after its list was set becomes a named hole, which is what the
    module turns into a sentence instead of a nought.
    """
    by_item: dict[str, dict[str, Decimal]] = {}
    for target in item_targets:
        by_item.setdefault(target["push_item_id"], {})[target["branch_id"]] = target[
            "portion_target"
        ]
    by_week: dict[str, list[incentive.PushItem]] = {}
    for item in items:
        by_week.setdefault(item["push_week_id"], []).append(
            incentive.PushItem(
                push_item_id=item["id"],
                menu_item_id=item["menu_item_id"],
                name=item["name"],
                category=item["category"],
                rate_per_portion=item["rate_per_portion"],
                archived=item["archived"],
                mapped=item["mapped"],
                targets=by_item.get(item["id"], {}),
            )
        )
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
                items=tuple(by_week.get(week["id"], ())),
            )
            for week in weeks
        ),
    )


async def _statements(
    db: Database,
    tenant_id: str,
    scheme: incentive.SchemeMonth,
    branches: list[asyncpg.Record],
    currency: str,
) -> dict[str, incentive.Statement]:
    """Each branch's statement for the month in view, by branch id, derived
    on this request out of the branch's own loaded days and stored nowhere
    (D10, D11, C16). The read serialises these; the approval door reads the
    one it is approving off the same composition, so what is approved is
    byte for byte what the screen showed.

    Three reads whatever the chain's size, all three on the month's own
    window: the loaded days, for the net sales and for the count against the
    calendar that keeps a statement provisional; the item-days, for the
    portions each push week scored; and the approvals, which are what make a
    statement final.

    Portions are the till's own net quantity - what it sold less what it
    refunded (D9), never a quantity worked back out of money - read through
    `till_items.menu_item_id` at read time and never stored on a line. That is
    why re-mapping a till name corrects every past day at once, and why a
    mapping removed after a list was set reads as a named hole rather than as
    a nought. A name the owner marked "not a menu item" - a delivery charge, a
    discount line - is a portion of nothing, which is the rule
    `contribution.py` already holds the whole product to, and an unmapped name
    scores against no dish by the same rule.

    A branch with no target in this month gets no statement: a month's targets
    cover every branch that existed the day it was created (D3, D4), and a
    branch opened since was never given a figure to be measured against. The
    targets table above says "No target" for it in the same breath.
    """
    first, last = incentive.month_start(scheme.month), incentive.month_end(scheme.month)
    days = [
        incentive.LoadedDay(
            branch_id=row["branch_id"],
            business_date=row["business_date"],
            net_sales=row["net_sales"],
        )
        for row in await db.list_sales_days(tenant_id=tenant_id, date_from=first, date_to=last)
    ]
    items = [
        incentive.ItemDay(
            branch_id=row["branch_id"],
            business_date=row["business_date"],
            menu_item_id=row["menu_item_id"],
            qty_net=row["qty_sold"] - row["qty_refunded"],
            no_qty_lines=row["no_qty_lines"],
        )
        for row in await db.list_period_item_sales(
            tenant_id=tenant_id, date_from=first, date_to=last
        )
        if row["menu_item_id"] is not None and row["excluded_at"] is None
    ]
    approvals = {
        row["branch_id"]: incentive.Approval(
            approved_at=row["approved_at"],
            actor=row["actor"],
            reason=row["reason"],
            figures=row["figures"],
        )
        for row in await db.list_statement_approvals(scheme.scheme_month_id, tenant_id=tenant_id)
    }
    newest: dict[str, datetime.date] = {}
    for day in days:
        if day.business_date > newest.get(day.branch_id, datetime.date.min):
            newest[day.branch_id] = day.business_date
    return {
        branch["id"]: incentive.compose_statement(
            scheme,
            branch["id"],
            days=days,
            items=items,
            newest_loaded=newest.get(branch["id"]),
            approval=approvals.get(branch["id"]),
            currency=currency,
        )
        for branch in branches
        if branch["id"] in scheme.targets
    }


async def read_branch_statement(
    db: Database, tenant_id: str, branch_id: str, *, month: datetime.date, currency: str
) -> tuple[incentive.Statement, str] | None:
    """One branch's statement for one scheme month and the branch's name,
    through the same reads the screen makes (`_scheme_month`, `_statements`),
    so the scoreboard on the phone is the statement on the screen (C16).
    None when the branch is not this tenant's, when no scheme month covers
    `month`, or when the month set no target for the branch - the three
    cases in which there is no statement to draw and the morning sends
    nothing (issue #14)."""
    branches = await db.list_incentive_branches(tenant_id=tenant_id)
    branch = next((row for row in branches if row["id"] == branch_id), None)
    if branch is None:
        return None
    first = incentive.month_start(month)
    row = next(
        (m for m in await db.list_scheme_months(tenant_id=tenant_id) if m["month"] == first), None
    )
    if row is None:
        return None
    scheme = _scheme_month(
        row,
        await db.list_scheme_month_targets(row["id"], tenant_id=tenant_id),
        await db.list_push_weeks(row["id"], tenant_id=tenant_id),
        await db.list_push_items(row["id"], tenant_id=tenant_id),
        await db.list_push_item_targets(row["id"], tenant_id=tenant_id),
    )
    statements = await _statements(db, tenant_id, scheme, [branch], currency)
    statement = statements.get(branch_id)
    if statement is None:
        return None
    return statement, branch["name"]


def _statements_payload(
    statements: dict[str, incentive.Statement], branches: list[asyncpg.Record]
) -> list[dict]:
    return [
        incentive.statement_json(statements[branch["id"]], branch_name=branch["name"])
        for branch in branches
        if branch["id"] in statements
    ]


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
    menu = await _menu(db, tenant_id)

    row = next((m for m in months if m["month"] == month), None)
    scheme_month = None
    if row is not None:
        scheme = _scheme_month(
            row,
            await db.list_scheme_month_targets(row["id"], tenant_id=tenant_id),
            await db.list_push_weeks(row["id"], tenant_id=tenant_id),
            await db.list_push_items(row["id"], tenant_id=tenant_id),
            await db.list_push_item_targets(row["id"], tenant_id=tenant_id),
        )
        scheme_month = incentive.scheme_month_json(
            scheme,
            created_at=row["created_at"],
            today=today,
            kept=menu.kept,
            statements=_statements_payload(
                await _statements(db, tenant_id, scheme, branches, currency), branches
            ),
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
        "menu": menu.payload(currency),
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


class PortionTargetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: str
    # Optional for the same reason the month's targets are: an empty box is a
    # sentence the pure module owns, naming the dish and the branch.
    portion_target: str | None = None


class PushItemBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    menu_item_id: str
    rate_per_portion: str | None = None
    targets: list[PortionTargetBody] = []


class ApprovalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str


class PushListBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: The whole week's list, every time: the write replaces what the week
    #: held rather than merging into it, so what the owner sees on the screen
    #: is what the week ends up with, with no third state in between.
    items: list[PushItemBody] = []


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


@router.put("/incentive/weeks/{push_week_id}")
async def set_push_list(
    push_week_id: uuid.UUID, body: PushListBody, request: Request, ctx: Context
) -> dict:
    """The owner filled a push week's list: what the team is asked to push
    that week, what a portion above target earns, and how many portions each
    branch is held to (D6, D7).

    The whole list arrives in one request and replaces the week's in one
    transaction with one audit row, so a week is never half re-aimed. Three
    things are refused before anything is written:

    - a week already under way, in the pure module's own sentence naming it.
      The day it is measured against is the chain's own latest local date, not
      the server's, because staff push dishes on branch time (D5); and a week
      that has *ended* is refused by the same rule, so a list is never
      backdated onto a month the team has already been scored on.
    - a dish with no till name mapped to it, or one archived off the menu,
      named: either could only ever score zero, and a target that can only
      score zero is a promise to the team that cannot be kept (D7).
    - a rate or a branch target left blank, named: a missing target would be
      scored as a target of zero and pay the team for every portion sold.

    Returns the whole read for the week's month, so the screen renders what it
    saved from one shape.
    """
    db: Database = request.app.state.db
    week = await db.get_push_week(str(push_week_id), tenant_id=ctx.tenant_id)
    if week is None:
        raise HTTPException(status_code=404, detail="push week not found")

    branches = await db.list_incentive_branches(tenant_id=ctx.tenant_id)
    window = incentive.Window(week["start_date"], week["end_date"])
    frozen = incentive.frozen_week_sentence(window, _today(branches))
    if frozen is not None:
        raise HTTPException(status_code=422, detail=frozen)

    menu = await _menu(db, ctx.tenant_id)
    typed = [
        incentive.TypedPushItem(
            menu_item_id=item.menu_item_id,
            rate_per_portion=_typed(item.rate_per_portion, what="rate per portion", example="0.25"),
            targets=[
                incentive.TypedPortionTarget(
                    branch_id=target.branch_id,
                    portion_target=_typed(
                        target.portion_target, what="portion target", example="250"
                    ),
                )
                for target in item.targets
            ],
        )
        for item in body.items
    ]
    problem = incentive.push_list_problem(
        menu.facts, {row["id"]: row["name"] for row in branches}, typed
    )
    if problem is not None:
        raise HTTPException(status_code=422, detail=problem)

    await db.set_push_list(
        str(push_week_id),
        tenant_id=ctx.tenant_id,
        items=[
            {
                "menu_item_id": item.menu_item_id,
                "rate_per_portion": item.rate_per_portion,
                "targets": [
                    {"branch_id": target.branch_id, "portion_target": target.portion_target}
                    for target in item.targets
                ],
            }
            for item in typed
        ],
        actor=ctx.actor,
    )
    scheme = await db.get_scheme_month(week["scheme_month_id"], tenant_id=ctx.tenant_id)
    return await _read(db, ctx.tenant_id, incentive.month_key(scheme["month"]))


@router.post("/incentive/months/{scheme_month_id}/branches/{branch_id}/approve")
async def approve_statement(
    scheme_month_id: uuid.UUID,
    branch_id: uuid.UUID,
    body: ApprovalBody,
    request: Request,
    ctx: Context,
) -> dict:
    """The owner approved one branch's statement for the month: the only door
    to a final statement (D11, D12).

    The statement is composed exactly as the read composes it, and what is
    approved is that composition's figures, stored as a snapshot beside the
    actor, the reason and the time, with the audit row
    `incentive.statement_approved` in the same transaction (C8) - so a
    failure in either leaves neither. Three refusals, each the pure module's
    own sentence: a statement already final (named by whom and when), a month
    with a day not loaded for that branch (with the count), and a reason left
    blank. Two approvals racing for the same statement are decided by the
    database's unique row, and the loser is told the winner's sentence.

    A sales day inside an approved month stays replaceable through the
    sales-day door: the approved figures stand, and the read says the till
    now says otherwise with the recomputed figures beside them. Faida moves
    no money.

    A month or a branch that is not this tenant's is not found, never
    forbidden. Returns the whole read for the month, so the screen renders
    the final statement from one shape.
    """
    db: Database = request.app.state.db
    row = await db.get_scheme_month(str(scheme_month_id), tenant_id=ctx.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="scheme month not found")
    branches = await db.list_incentive_branches(tenant_id=ctx.tenant_id)
    scheme = _scheme_month(
        row,
        await db.list_scheme_month_targets(row["id"], tenant_id=ctx.tenant_id),
        await db.list_push_weeks(row["id"], tenant_id=ctx.tenant_id),
        await db.list_push_items(row["id"], tenant_id=ctx.tenant_id),
        await db.list_push_item_targets(row["id"], tenant_id=ctx.tenant_id),
    )
    currency = await db.tenant_currency(ctx.tenant_id) or ""
    statements = await _statements(db, ctx.tenant_id, scheme, branches, currency)
    statement = statements.get(str(branch_id))
    if statement is None:
        raise HTTPException(status_code=404, detail="statement not found")

    problem = incentive.approval_problem(statement, body.reason)
    if problem is not None:
        raise HTTPException(status_code=422, detail=problem)
    try:
        await db.approve_statement(
            row["id"],
            tenant_id=ctx.tenant_id,
            branch_id=str(branch_id),
            actor=ctx.actor,
            reason=body.reason.strip(),
            figures=incentive.figures_json(statement.figures),
        )
    except asyncpg.UniqueViolationError:
        # Two approvals at once: the database decided, and the loser is told
        # by whom and when the statement went final.
        approvals = await db.list_statement_approvals(row["id"], tenant_id=ctx.tenant_id)
        first = next(a for a in approvals if a["branch_id"] == str(branch_id))
        raise HTTPException(
            status_code=422,
            detail=incentive.already_final_sentence(
                incentive.Approval(
                    approved_at=first["approved_at"],
                    actor=first["actor"],
                    reason=first["reason"],
                    figures=first["figures"],
                )
            ),
        ) from None
    return await _read(db, ctx.tenant_id, incentive.month_key(scheme.month))
