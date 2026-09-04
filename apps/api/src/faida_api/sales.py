"""M8 WP-80: the sales tables' one write door and the reads beside it
(plan.md §7.3; Docs/M8_DECOMPOSITION.md §3 C11, §3.1 wire shapes).

Routes, all under /api behind the same auth context as the rest of the API
(`auth.py`, M7): every read and write carries the caller's tenant, every
write names the context's actor, and a row outside the tenant is 404:

    GET    /api/branches                    the tenant's branches with their till aliases
    POST   /api/branches/{id}/aliases       teach one till label for one branch
    POST   /api/sales/files                 keep the raw CSV under its server-computed hash
    GET    /api/sales/layouts               the saved column layouts, by till name
    POST   /api/sales/layouts               save or update a layout by name
    GET    /api/sales/days?from&to          the stored branch-days with their lines
    POST   /api/sales/days                  load up to 31 branch-days, one transaction each

The door is synchronous like the menu loader's (C2 untouched): a 21-day file
is one request of 21 small days, and a year of history is a few dozen
requests of one branch-month each, never a job. It takes a list of days and
answers an outcome per day - `loaded`, `unchanged` or `replaced` - because
the loader's grid restamps its rows from what actually happened and not from
what it predicted (WP-64's rule). A retry of a request that already landed is
`unchanged` for every day, so a refresh mid-run costs nothing.

Money arrives as signed decimal strings and leaves as strings (C4/C6): a
refund is a negative row that reduces the day, and nothing here is a float.
Net sales is the one division in M8 - `takings.net_amount`, per line, to the
fil - and the browser never computes it: the day's net in the loader's grid
is what this door answered.

Item-wise exports only (the founder's call, 2026-09-04): a day is its item
rows, and a `summary` day is a closed day and nothing else - amount 0, no
lines - which the loader sends for a day inside the file's own range with no
rows, or for a row the till printed with no item and 0 (C11.4). A summary
day with money is a day-totals export, and that arrives with the pilot
(M11); until then it is refused with a sentence rather than stored as a day
the coverage figure could never see inside.

The refusal set, each with its own plain sentence:

    more than 31 days                  one branch-month per request
    a closed day with money in it      item-wise exports only for now; a
                                       day-totals export comes with the
                                       pilot (M11)
    one branch-day named twice         a file says one thing about a day
    a business date after tomorrow     a swapped day and month
    a business date before 2020        a swapped year
    an amount with more than 2 decimals, a quantity with more than 3
    an item day with no lines, a closed day with lines
    a branch or layout the tenant does not have   404, never 403
"""

import datetime
import hashlib
import re
import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict

from . import ratio, takings
from .api import _clean, _dec, _iso
from .auth import AuthContext, require_context
from .confirm import _parse_number
from .db import Database
from .extraction.constants import VAT_RATE_BY_CURRENCY
from .menu import _menu_context
from .provenance import asserted_fields

# Declared twice like api.py: at the router, so no route here can exist
# without the token check, and per handler, to receive the tenant and actor.
router = APIRouter(prefix="/api", dependencies=[Depends(require_context)])
Context = Annotated[AuthContext, Depends(require_context)]

#: A year of item-wise rows for a large chain is a few megabytes; this is
#: the ceiling on one file, not a target.
SALES_FILE_MAX_BYTES = 20 * 1024 * 1024

_SIGNED_RE = re.compile(r"-?\d+(?:\.\d+)?")


# --- request bodies ---------------------------------------------------------


class BranchAliasIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str


class SalesLayoutIn(BaseModel):
    """A till's column layout: logical name to header *name*, never to a
    position (C11.1). `header_key` is derived here from the mapped names and
    is never sent."""

    model_config = ConfigDict(extra="forbid")

    name: str
    columns: dict[str, str]
    amount_basis: Literal["inclusive", "exclusive"]
    date_order: Literal["dmy", "ymd"]


class SalesSourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha256: str
    filename: str | None = None


class SalesLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int
    name: str
    code: str | None = None
    qty: str | None = None
    amount: str


class SalesDayIn(BaseModel):
    """One branch-day as the loader grouped it: an `item` day carries lines
    and no amount; a `summary` day is a closed day - amount 0 and no lines -
    for a day inside the file's own range with no rows, or a row the till
    printed with no item and 0. A summary day with money is refused until
    the pilot's day-totals export (M11)."""

    model_config = ConfigDict(extra="forbid")

    branch_id: uuid.UUID
    business_date: datetime.date
    granularity: Literal["item", "summary"]
    amount_basis: Literal["inclusive", "exclusive"]
    layout_id: uuid.UUID | None = None
    source: SalesSourceIn | None = None
    lines: list[SalesLineIn] | None = None
    amount: str | None = None


class SalesDaysIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: list[SalesDayIn]


# --- the refusal set --------------------------------------------------------


def _signed_number(value: str, *, what: str, places: int, example: str) -> Decimal:
    """The by-hand door's decimal-string rule with a sign in front of it: a
    refund is a negative row (C11.2). Decimal places are capped at what the
    column stores, because "as printed" means the stored bytes are the
    printed ones and a quantized 490.005 would not be."""
    text = value.strip()
    negative = text.startswith("-")
    number = _parse_number(text[1:] if negative else text)
    if number is None or _SIGNED_RE.fullmatch(text.rstrip(".!?")) is None:
        raise HTTPException(
            status_code=422,
            detail=f"'{value}' is not a valid {what}: send a decimal string like \"{example}\"",
        )
    if -number.as_tuple().exponent > places:
        raise HTTPException(
            status_code=422,
            detail=f"'{value}' has more than {places} decimals: a {what} is stored as printed, "
            f"to {places}",
        )
    return -number if negative else number


def _rate(value: Decimal | None) -> str | None:
    """A VAT rate as a plain string ("0.05"), never a float and never
    numeric(6,4)'s trailing zeros."""
    return None if value is None else format(value.normalize(), "f")


def _day_json(row) -> dict:
    return {
        "id": row["id"],
        "branch_id": row["branch_id"],
        "business_date": _iso(row["business_date"]),
        "granularity": row["granularity"],
        "amount_basis": row["amount_basis"],
        "vat_rate": _rate(row["vat_rate"]),
        "takings": _dec(row["takings"]),
        "net_sales": _dec(row["net_sales"]),
        "line_count": row["line_count"],
        "layout_id": row["layout_id"],
        "source_sha256": row["source_sha256"],
        "source_filename": row["source_filename"],
        "loaded_by": row["loaded_by"],
        "loaded_at": _iso(row["loaded_at"]),
    }


def _line_json(row) -> dict:
    return {
        "position": row["position"],
        "name": row["name"],
        "code": row["code"],
        "qty": _dec(row["qty"]),
        "amount": _dec(row["amount"]),
        "net_amount": _dec(row["net_amount"]),
        "till_item_id": row["till_item_id"],
    }


def _layout_json(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "header_key": row["header_key"],
        "columns": row["columns"],
        "amount_basis": row["amount_basis"],
        "date_order": row["date_order"],
        "updated_at": _iso(row["updated_at"]),
    }


def _alias_json(row) -> dict:
    return {
        "id": row["id"],
        "branch_id": row["branch_id"],
        "alias": row["alias"],
        "alias_key": row["alias_key"],
    }


# --- branches ---------------------------------------------------------------


@router.get("/branches")
async def list_branches(request: Request, ctx: Context) -> dict:
    """The tenant's branches with the till labels taught for each (C6
    extended): the loader's branch picker and the branch column's resolver."""
    db: Database = request.app.state.db
    aliases: dict[str, list[str]] = defaultdict(list)
    for row in await db.list_branch_aliases(tenant_id=ctx.tenant_id):
        aliases[row["branch_id"]].append(row["alias"])
    return {
        "branches": [
            {
                "id": row["id"],
                "name": row["name"],
                "timezone": row["timezone"],
                "aliases": aliases.get(row["id"], []),
            }
            for row in await db.list_branches(tenant_id=ctx.tenant_id)
        ]
    }


@router.post("/branches/{branch_id}/aliases")
async def save_branch_alias(
    branch_id: uuid.UUID, body: BranchAliasIn, request: Request, ctx: Context, response: Response
) -> dict:
    """Teach the chain that a till's label means this branch (C11.1). The
    same label again is 200 with the existing row; a label that already
    names another branch is 409 with its name, because an alias is the
    chain's fact and two branches cannot share one."""
    db: Database = request.app.state.db
    branch = await db.get_branch(str(branch_id), tenant_id=ctx.tenant_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="branch not found")
    alias = _clean(body.alias)
    alias_key = takings.name_key(alias) if alias is not None else ""
    if not alias_key:
        raise HTTPException(status_code=422, detail="an alias needs some text")
    result = await db.save_branch_alias(
        str(branch_id),
        tenant_id=ctx.tenant_id,
        alias=alias,
        alias_key=alias_key,
        actor=ctx.actor,
    )
    if result["other_branch_id"] is not None:
        other = await db.get_branch(result["other_branch_id"], tenant_id=ctx.tenant_id)
        raise HTTPException(
            status_code=409,
            detail=f"'{alias}' already names {other['name'] if other else 'another branch'}",
        )
    response.status_code = 201 if result["created"] else 200
    return {"alias": _alias_json(result["alias"])}


# --- the raw file -------------------------------------------------------------


def _already_stored(error: httpx.HTTPStatusError) -> bool:
    """Storage refusing an upsert (`x-upsert: false`) is the answer we want
    for a file already kept: the mock answers 409, Supabase's own API answers
    400 with a Duplicate body."""
    status = error.response.status_code
    if status == 409:
        return True
    text = error.response.text.lower()
    return status == 400 and ("duplicate" in text or "already exists" in text)


@router.post("/sales/files")
async def store_sales_file(
    request: Request, ctx: Context, file: UploadFile, response: Response
) -> dict:
    """Keep the exact bytes a sales day will come from (C11.1, PRD §12). The
    hash is computed here, never taken from the client, and the object is
    immutable under it: the same bytes posted again answer 200 with the same
    hash and store nothing."""
    data = await file.read(SALES_FILE_MAX_BYTES + 1)
    if len(data) > SALES_FILE_MAX_BYTES:
        raise HTTPException(
            status_code=413, detail=f"file too large: the limit is {SALES_FILE_MAX_BYTES} bytes"
        )
    if not data:
        raise HTTPException(status_code=422, detail="empty file")
    sha256 = hashlib.sha256(data).hexdigest()
    path = f"{ctx.tenant_id}/sales/{sha256}.csv"
    try:
        await request.app.state.storage.put(path, data, "text/csv")
        response.status_code = 201
    except httpx.HTTPStatusError as error:
        if not _already_stored(error):
            raise
        response.status_code = 200
    return {"sha256": sha256, "filename": file.filename, "bytes": len(data)}


# --- layouts ----------------------------------------------------------------


@router.get("/sales/layouts")
async def list_sales_layouts(request: Request, ctx: Context) -> dict:
    db: Database = request.app.state.db
    rows = await db.list_sales_layouts(tenant_id=ctx.tenant_id)
    return {"layouts": [_layout_json(row) for row in rows]}


@router.post("/sales/layouts")
async def save_sales_layout(
    body: SalesLayoutIn, request: Request, ctx: Context, response: Response
) -> dict:
    """Save a till's layout by name (C11.1): 201 when the name is new, 200
    when it updated the layout the consultant re-mapped. The header key is
    derived from the mapped header names, sorted, so a reordered export
    still matches."""
    db: Database = request.app.state.db
    name = _clean(body.name)
    if name is None:
        raise HTTPException(status_code=422, detail="a layout needs a name: the till it belongs to")
    columns: dict[str, str] = {}
    for logical, header in body.columns.items():
        if logical not in takings.LAYOUT_COLUMNS:
            raise HTTPException(
                status_code=422,
                detail=f"'{logical}' is not a column this loader knows: "
                f"{', '.join(takings.LAYOUT_COLUMNS)}",
            )
        header_name = _clean(header)
        if header_name is None:
            raise HTTPException(status_code=422, detail=f"the {logical} column needs a header name")
        columns[logical] = header_name
    for required in takings.LAYOUT_REQUIRED:
        if required not in columns:
            raise HTTPException(
                status_code=422, detail=f"a layout needs a {required} column: which header is it?"
            )
    keys = [takings.name_key(header) for header in columns.values()]
    if len(set(keys)) != len(keys):
        raise HTTPException(
            status_code=422, detail="two columns are mapped to the same header name"
        )
    result = await db.save_sales_layout(
        tenant_id=ctx.tenant_id,
        name=name,
        header_key=takings.header_key(columns.values()),
        columns=columns,
        amount_basis=body.amount_basis,
        date_order=body.date_order,
        actor=ctx.actor,
    )
    response.status_code = 201 if result["created"] else 200
    return {"layout": _layout_json(result["layout"])}


# --- the ratio and coverage (WP-81) -----------------------------------------
#
# Two reads, both derived on every request and never stored (`ratio.py`):
#
#     GET /api/sales/branches?from&to    purchases ÷ net sales per branch, ranked,
#                                        every row labelled by its gaps, the
#                                        unassigned papers and the chain total
#     GET /api/sales/coverage?from&to    costed share of sales value, the two
#                                        uncosted buckets and the mapping queue
#
# The period defaults to the 28 days ending on the tenant's newest loaded day
# (C11.6), so it is never empty while any sales exist; `from` and `to` given
# together are honoured, reversed or longer than 92 days is refused.


def _proposals_for(till_item: dict, menu_items: list[dict]) -> list[dict]:
    """The queue's proposals for one unmapped till name (§3.1 `queue[].proposals`).
    WP-82 wires `matching.propose_menu_items` here; until it lands the queue
    carries none, and the screen offers pick-from-menu alone."""
    return []


async def _period(
    db: Database, tenant_id: str, date_from: datetime.date | None, date_to: datetime.date | None
) -> tuple[ratio.Period, bool, datetime.date | None]:
    """The period a read covers, its `default` flag, and the tenant's newest
    loaded day (the freshness fact every period line states)."""
    newest_by_branch = await db.newest_sales_dates(tenant_id=tenant_id)
    newest = max(newest_by_branch.values()) if newest_by_branch else None
    if (date_from is None) != (date_to is None):
        raise HTTPException(status_code=422, detail="send both 'from' and 'to', or neither")
    if date_from is None or date_to is None:
        end = newest or datetime.datetime.now(datetime.UTC).date()
        start = end - datetime.timedelta(days=ratio.DEFAULT_PERIOD_DAYS - 1)
        return ratio.Period(start, end), True, newest
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="'from' is after 'to'")
    period = ratio.Period(date_from, date_to)
    if period.days > ratio.MAX_PERIOD_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"{period.days} days is longer than one read covers: "
            f"at most {ratio.MAX_PERIOD_DAYS}",
        )
    return period, False, newest


def _period_json(period: ratio.Period, default: bool, newest: datetime.date | None) -> dict:
    return {
        "from": period.start.isoformat(),
        "to": period.end.isoformat(),
        "days": period.days,
        "default": default,
        "sales_through": _iso(newest),
    }


def _sales_day_input(row) -> ratio.SalesDay:
    return ratio.SalesDay(
        branch_id=row["branch_id"],
        business_date=row["business_date"],
        net_sales=row["net_sales"],
        takings=row["takings"],
        granularity=row["granularity"],
    )


def _invoice_input(row) -> ratio.Invoice:
    provenance = row["provenance"] or {}
    asserted = any(key in ("total", "tax") for key in asserted_fields(provenance))
    return ratio.Invoice(
        invoice_id=row["id"],
        branch_id=row["branch_id"],
        status=row["status"],
        currency=row["currency"],
        total=row["total"],
        tax=row["tax"],
        invoice_date=row["invoice_date"],
        purchased_on=row["purchased_on"],
        placed_on=row["placed_on"],
        supplier_name=row["supplier_name"],
        invoice_no=row["invoice_no"],
        asserted=asserted,
    )


def _invoice_figure_json(figure: ratio.InvoiceFigure) -> dict:
    return {
        "invoice_id": figure.invoice_id,
        "supplier_name": figure.supplier_name,
        "invoice_no": figure.invoice_no,
        "purchased_on": _iso(figure.purchased_on),
        "net_purchase": _dec(figure.net_purchase),
        "total": _dec(figure.total),
        "tax": _dec(figure.tax),
        "quality": figure.quality,
    }


def _branch_row_json(row: ratio.BranchRow) -> dict:
    return {
        "branch_id": row.branch_id,
        "branch_name": row.branch_name,
        "window": {
            "from": row.window.start.isoformat(),
            "to": row.window.end.isoformat(),
            "days": row.window.days,
        },
        "net_sales": _dec(row.net_sales),
        "takings": _dec(row.takings),
        "purchases": _dec(row.purchases),
        "ratio_pct": _dec(row.ratio_pct),
        "quality": row.quality.value,
        "notes": list(row.notes),
        "days_loaded": row.days_loaded,
        "days_missing": row.days_missing,
        "deliveries": row.deliveries,
        "sales_through": _iso(row.sales_through),
        "last_purchase_on": _iso(row.last_purchase_on),
        "days": [
            {
                "business_date": _iso(day.business_date),
                "net_sales": _dec(day.net_sales),
                "granularity": day.granularity,
                "purchases": _dec(day.purchases),
                "invoices": [_invoice_figure_json(i) for i in day.invoices],
            }
            for day in row.days
        ],
        "pending": [
            {
                "invoice_id": p.invoice_id,
                "supplier_name": p.supplier_name,
                "invoice_no": p.invoice_no,
                "status": p.status,
                "placed_on": _iso(p.placed_on),
                "undated": p.undated,
            }
            for p in row.pending
        ],
        "excluded": [
            {
                "invoice_id": e.invoice_id,
                "supplier_name": e.supplier_name,
                "invoice_no": e.invoice_no,
                "currency": e.currency,
                "total": _dec(e.total),
            }
            for e in row.excluded
        ],
    }


@router.get("/sales/branches")
async def sales_by_branch(
    request: Request,
    ctx: Context,
    date_from: Annotated[datetime.date | None, Query(alias="from")] = None,
    date_to: Annotated[datetime.date | None, Query(alias="to")] = None,
) -> dict:
    """Purchases ÷ net sales (cash basis) per branch for the period, ranked
    highest first, every row labelled by its gaps with the sentences that made
    the label, the drill to each day's papers, the papers the ranking could
    not place, and the chain total that reconciles the table (C11.5-C11.6,
    the C9 amendment)."""
    db: Database = request.app.state.db
    tenant_id = ctx.tenant_id
    period, default, newest = await _period(db, tenant_id, date_from, date_to)
    currency = await db.tenant_currency(tenant_id) or ""
    branches = await db.list_branches(tenant_id=tenant_id)
    newest_by_branch = await db.newest_sales_dates(tenant_id=tenant_id)
    days = [
        _sales_day_input(row)
        for row in await db.list_sales_days(
            tenant_id=tenant_id, date_from=period.start, date_to=period.end
        )
    ]
    invoices = [
        _invoice_input(row)
        for row in await db.list_period_invoices(
            tenant_id=tenant_id, date_from=period.start, date_to=period.end
        )
    ]
    rows = ratio.rank(
        [
            ratio.period_row(
                branch_id=branch["id"],
                branch_name=branch["name"],
                days=days,
                invoices=invoices,
                period=period,
                tenant_currency=currency,
                latest_sales_day=newest_by_branch.get(branch["id"]),
            )
            for branch in branches
        ]
    )
    unassigned = ratio.unassigned_group(invoices, period, currency)
    total = ratio.chain_total(rows, unassigned)
    return {
        "period": _period_json(period, default, newest),
        "rows": [_branch_row_json(row) for row in rows],
        "unassigned": {
            "count": unassigned.count,
            "purchases": _dec(unassigned.purchases),
            "invoices": [_invoice_figure_json(i) for i in unassigned.invoices],
        },
        "total": {
            "net_sales": _dec(total.net_sales),
            "purchases": _dec(total.purchases),
            "ratio_pct": _dec(total.ratio_pct),
            "quality": total.quality.value,
            "notes": list(total.notes),
        },
    }


def _coverage_item_json(item: ratio.CoverageItem) -> dict:
    return {
        "till_item_id": item.till_item_id,
        "name": item.name,
        "code": item.code,
        "value": _dec(item.value),
    }


@router.get("/sales/coverage")
async def sales_coverage(
    request: Request,
    ctx: Context,
    date_from: Annotated[datetime.date | None, Query(alias="from")] = None,
    date_to: Annotated[datetime.date | None, Query(alias="to")] = None,
) -> dict:
    """Recipe coverage by sales value (C11.8): the share of the period's menu
    sales whose till item maps to a plate that can be costed - *costed*, never
    *complete* - with the estimated points named, the two uncosted buckets,
    what sits beside the figure, and the mapping queue ranked by value. A
    plate's quality comes from `menu._menu_context`, so it is computed by
    exactly one function on every screen."""
    db: Database = request.app.state.db
    tenant_id = ctx.tenant_id
    period, default, newest = await _period(db, tenant_id, date_from, date_to)
    values = [
        ratio.TillItemValue(
            till_item_id=row["till_item_id"],
            name=row["name"],
            code=row["code"],
            menu_item_id=row["menu_item_id"],
            excluded=row["excluded_at"] is not None,
            positive_value=row["positive_value"],
            refund_value=row["refund_value"],
        )
        for row in await db.list_period_sales_lines(
            tenant_id=tenant_id, date_from=period.start, date_to=period.end
        )
    ]
    menu_rows, _, plate_by_item, _ = await _menu_context(db, tenant_id)
    plates = {
        row["id"]: ratio.MenuPlate(
            menu_item_id=row["id"],
            name=row["name"],
            plate_quality=plate_by_item[row["id"]].quality.value,
            archived=row["archived_at"] is not None,
        )
        for row in menu_rows
    }
    live_items = [
        {"id": row["id"], "name": row["name"]} for row in menu_rows if row["archived_at"] is None
    ]
    result = ratio.coverage(values, plates)
    return {
        "period": _period_json(period, default, newest),
        "sales_value": _dec(result.sales_value),
        "costed_value": _dec(result.costed_value),
        "costed_pct": _dec(result.costed_pct),
        "estimated_points": _dec(result.estimated_points),
        "uncosted": {
            "incomplete_plate": _dec(result.uncosted_incomplete_plate),
            "unmapped": _dec(result.uncosted_unmapped),
        },
        "beside": {
            "refunds": _dec(result.refunds),
            "not_menu_items": _dec(result.not_menu_items),
        },
        "queue": [
            {
                **_coverage_item_json(item),
                "proposals": _proposals_for(
                    {"till_item_id": item.till_item_id, "name": item.name, "code": item.code},
                    live_items,
                ),
            }
            for item in result.queue
        ],
        "mapped": [
            {
                **_coverage_item_json(item),
                "menu_item_id": item.menu_item_id,
                "menu_item_name": item.menu_item_name,
                "plate_quality": item.plate_quality,
            }
            for item in result.mapped
        ],
        "excluded": [_coverage_item_json(item) for item in result.excluded],
    }


# --- days -------------------------------------------------------------------


@router.get("/sales/days")
async def list_sales_days(
    request: Request,
    ctx: Context,
    date_from: Annotated[datetime.date, Query(alias="from")],
    date_to: Annotated[datetime.date, Query(alias="to")],
) -> dict:
    """The stored days in a range with their lines, every branch, so the
    loader can predict `unchanged` and `replaced` before it commits and show
    a shrinking day as before and after (C11.4)."""
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="'from' is after 'to'")
    db: Database = request.app.state.db
    days = await db.list_sales_days(tenant_id=ctx.tenant_id, date_from=date_from, date_to=date_to)
    lines: dict[str, list[dict]] = defaultdict(list)
    for row in await db.list_sales_lines(
        tenant_id=ctx.tenant_id, day_ids=[day["id"] for day in days]
    ):
        lines[row["sales_day_id"]].append(_line_json(row))
    return {"days": [{**_day_json(day), "lines": lines.get(day["id"], [])} for day in days]}


@router.post("/sales/days")
async def load_sales_days(body: SalesDaysIn, request: Request, ctx: Context) -> dict:
    """The one write door for sales (C11.4): a list of branch-days, at most
    31, validated whole before anything is written, then one transaction
    and one outcome per day. A refused request writes nothing; a refused
    day names itself and its row."""
    db: Database = request.app.state.db
    tenant_id = ctx.tenant_id
    days = body.days
    if not days:
        raise HTTPException(status_code=422, detail="send at least one day")
    if len(days) > takings.MAX_DAYS_PER_REQUEST:
        raise HTTPException(
            status_code=422,
            detail=f"{len(days)} days in one request: send at most "
            f"{takings.MAX_DAYS_PER_REQUEST}, one branch-month at a time",
        )
    repeated = takings.duplicate_days((str(day.branch_id), day.business_date) for day in days)
    if repeated:
        branch_id, business_date = repeated[0]
        raise HTTPException(
            status_code=422,
            detail=f"{business_date.isoformat()} appears twice for one branch: a file says one "
            "thing about a day",
        )

    today = datetime.datetime.now(datetime.UTC).date()
    currency = await db.tenant_currency(tenant_id)
    vat_rate = VAT_RATE_BY_CURRENCY.get(currency or "")

    # Everything the tenant must own, checked before any write (C10): a
    # branch or layout of another tenant does not exist here, and Postgres'
    # composite keys refuse it regardless of what this missed.
    for branch_id in {str(day.branch_id) for day in days}:
        if await db.get_branch(branch_id, tenant_id=tenant_id) is None:
            raise HTTPException(status_code=404, detail="branch not found")
    for layout_id in {str(day.layout_id) for day in days if day.layout_id is not None}:
        if await db.get_sales_layout(layout_id, tenant_id=tenant_id) is None:
            raise HTTPException(status_code=404, detail="layout not found")

    prepared: list[dict] = []
    for index, day in enumerate(days):
        label = f"day {index + 1} ({day.business_date.isoformat()})"
        problem = takings.date_problem(day.business_date, today)
        if problem is not None:
            raise HTTPException(status_code=422, detail=f"{label}: {problem}")
        lines: list[dict] = []
        amount: Decimal | None = None
        net: Decimal | None = None
        if day.granularity == "item":
            if day.amount is not None:
                raise HTTPException(
                    status_code=422, detail=f"{label}: an item day carries lines, not an amount"
                )
            if not day.lines:
                raise HTTPException(
                    status_code=422, detail=f"{label}: an item day needs at least one line"
                )
            positions: set[int] = set()
            for line in day.lines:
                row = f"{label} row {line.position}"
                if line.position in positions:
                    raise HTTPException(status_code=422, detail=f"{row}: position repeated")
                positions.add(line.position)
                name = _clean(line.name)
                if name is None:
                    raise HTTPException(status_code=422, detail=f"{row}: a line needs a name")
                line_amount = _signed_number(
                    line.amount, what=f"amount ({row})", places=2, example="490.00"
                )
                qty = (
                    None
                    if _clean(line.qty) is None
                    else _signed_number(line.qty, what=f"quantity ({row})", places=3, example="14")
                )
                lines.append(
                    {
                        "position": line.position,
                        "name": name,
                        "code": _clean(line.code),
                        "qty": qty,
                        "amount": line_amount,
                        "net_amount": takings.net_amount(
                            line_amount, amount_basis=day.amount_basis, vat_rate=vat_rate
                        ),
                    }
                )
        else:
            if day.lines:
                raise HTTPException(
                    status_code=422,
                    detail=f"{label}: a closed day carries an amount of 0, not lines",
                )
            if day.amount is None:
                raise HTTPException(
                    status_code=422, detail=f"{label}: a closed day needs an amount of 0"
                )
            amount = _signed_number(day.amount, what=f"amount ({label})", places=2, example="0.00")
            if amount != 0:
                raise HTTPException(
                    status_code=422,
                    detail=f"{label}: Faida loads item-wise exports for now, so a day without "
                    "item rows can only be a closed day (amount 0); a day-totals export comes "
                    "with the pilot (M11)",
                )
            net = takings.net_amount(amount, amount_basis=day.amount_basis, vat_rate=vat_rate)
        prepared.append(
            {
                "branch_id": str(day.branch_id),
                "business_date": day.business_date,
                "granularity": day.granularity,
                "amount_basis": day.amount_basis,
                "layout_id": None if day.layout_id is None else str(day.layout_id),
                "source_sha256": None if day.source is None else day.source.sha256,
                "source_filename": None if day.source is None else _clean(day.source.filename),
                "lines": lines,
                "amount": amount,
                "net": net,
            }
        )

    outcomes: list[dict] = []
    for day in prepared:
        result = await db.load_sales_day(
            tenant_id=tenant_id, vat_rate=vat_rate, actor=ctx.actor, **day
        )
        outcomes.append(
            {
                "branch_id": day["branch_id"],
                "business_date": day["business_date"].isoformat(),
                "outcome": result["outcome"],
                "previous": result["previous"],
                "day": _day_json(result["day"]),
            }
        )
    return {"days": outcomes}
