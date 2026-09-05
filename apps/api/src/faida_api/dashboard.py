"""M9 WP-92: the one dashboard read - `GET /api/dashboard?from&to&branch_id`
(Docs/M9_DECOMPOSITION.md §3.1, C6 extended; plan.md §7.2).

The whole owner screen in one read, derived on every request and never
stored: the period and its freshness, the two answer sentences, the newest
loaded day (M10's first brief slot), the papers waiting, the branch league
with contribution beside the ratio, every item row, the signals ranked by
money, and the unmapped count. Every block shares one period, one set of
clipped windows and one costed menu, so nothing on the screen can disagree
with anything else on it (P9).

Nothing is computed here that a pure module already computes: the league
**calls** `ratio.period_row`, `unassigned_group` and `chain_total` (a second
ratio is a contract breach, C12.9), contribution comes from `contribution`,
the signals from `signals`, the price moves from `menu.price_moves`, and the
period rule from `ratio.resolve_period`, which `sales.py` calls too. This
module reads, adapts rows into those modules' inputs, composes the few
sentences that are about the whole screen (the answer, the freshness line),
and serialises - money as strings, percentages to a tenth as strings, dates
ISO (C4, C11).

A fixed number of queries whatever the menu's length or the branch count
(D10, D16): `test_dashboard.py` enumerates the reads and derives the maximum
from the list. The menu is costed twice - at the prices in force on the
period's last day, and today's - from one set of recipe and item rows, so a
row can carry today's cost beside its own when they differ (C12.4a, D20).
"""

import datetime
from collections.abc import Iterable, Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from . import contribution, plates, ratio, signals
from .api import _dec, _iso
from .auth import AuthContext, require_context
from .db import Database
from .menu import _menu_context, _plates_for, _pricing, price_moves
from .ratio import Quality
from .sales import _invoice_input, _sales_day_input
from .signals import _short_branch

# Declared twice like the other routers: at the router, so no route here can
# exist without the token check, and per handler, to receive the tenant.
router = APIRouter(prefix="/api", dependencies=[Depends(require_context)])
Context = Annotated[AuthContext, Depends(require_context)]

#: Past this many days since the newest loaded day the freshness line carries
#: the word *estimated* beside the sentence (P6): a chain that stops uploading
#: is told rather than quietly served stale figures.
FRESHNESS_STALE_DAYS = 7

#: The papers block lists this many and counts them all: the count is the
#: truth and the list a courtesy.
PAPERS_LISTED = 5

#: The item panel's two slices (§3.1): five best and five worst.
ITEMS_SLICE = 5

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_NUMBER_WORDS = {
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}


# --- adapters: rows into the pure modules' inputs ------------------------------


def _item_sales(row: asyncpg.Record) -> contribution.ItemSales:
    return contribution.ItemSales(
        branch_id=row["branch_id"],
        business_date=row["business_date"],
        till_item_id=row["till_item_id"],
        name=row["name"],
        code=row["code"],
        menu_item_id=row["menu_item_id"],
        excluded=row["excluded_at"] is not None,
        qty_sold=row["qty_sold"],
        qty_refunded=row["qty_refunded"],
        positive_value=row["positive_value"],
        refund_value=row["refund_value"],
        no_qty_lines=row["no_qty_lines"],
    )


def _menu_items(
    rows: Sequence[asyncpg.Record],
    components_by_item: Mapping[str, Sequence[asyncpg.Record]],
    plate_by_item: Mapping[str, plates.Plate],
    prices: Mapping[str, asyncpg.Record],
    vat_rate: Decimal | None,
) -> dict[str, contribution.MenuItem]:
    """The menu as `contribution` reads it: each item's as-of plate, its
    current recipe version, and every component with the invoice line behind
    the price that costed it (C12.4a). The batch cost is the same
    multiplication `plates.cost_component` makes - the quantity in base units
    times the price per base unit - and None when there is no price or the
    unit does not convert, so a hole is a hole here too."""
    menu: dict[str, contribution.MenuItem] = {}
    for row in rows:
        components: list[contribution.RecipeComponent] = []
        for component in components_by_item.get(row["id"], []):
            price = prices.get(component["ingredient_id"])
            batch_cost = invoice_id = position = purchased_on = None
            if price is not None:
                converted = plates.to_base_qty(component["qty"], component["unit"])
                if converted is not None and converted[1] == price["cost_base_unit"]:
                    batch_cost = converted[0] * price["cost_per_base_unit"]
                invoice_id = price["invoice_id"]
                position = price["position"]
                purchased_on = price["purchased_on"]
            components.append(
                contribution.RecipeComponent(
                    ingredient_id=component["ingredient_id"],
                    ingredient_name=component["ingredient_name"],
                    qty=component["qty"],
                    unit=component["unit"],
                    batch_cost=batch_cost,
                    invoice_id=invoice_id,
                    line_position=position,
                    purchased_on=purchased_on,
                )
            )
        archived_at = row["archived_at"]
        menu[row["id"]] = contribution.MenuItem(
            menu_item_id=row["id"],
            name=row["name"],
            plate=plate_by_item[row["id"]],
            selling_price=row["selling_price"],
            yield_portions=row["yield_portions"] or Decimal(1),
            vat_rate=vat_rate,
            category=row["category"],
            recipe_version=row["version"],
            components=tuple(components),
            archived=archived_at is not None,
            archived_on=None if archived_at is None else archived_at.date(),
        )
    return menu


# --- the sentences that are about the whole screen ------------------------------


def _weekday_date(day: datetime.date) -> str:
    return f"{_WEEKDAYS[day.weekday()]} {day.day} {day.strftime('%b')}"


def freshness_sentence(newest: datetime.date | None, today: datetime.date) -> str | None:
    """ "Sales loaded to Mon 31 Aug, 5 days ago." - the newest loaded day,
    named and aged (P6), M10's `freshness.sentence`. When the newest day is
    yesterday the sentence says so and reads exactly as the checklist meant."""
    if newest is None:
        return None
    ago = (today - newest).days
    when = "today" if ago <= 0 else "yesterday" if ago == 1 else f"{ago} days ago"
    return f"Sales loaded to {_weekday_date(newest)}, {when}."


def branch_answer(
    ranked: Sequence[contribution.Contribution], scope: signals.Scope
) -> tuple[str | None, contribution.Contribution | None]:
    """The branch to look at first, in the "of every 100" lens: the top row of
    `contribution.rank` (C12.9, D21), the least of however many carry a
    figure. Under a branch scope the sentence is about that branch alone. An
    incomplete top row says so in the same breath."""
    rated = [c for c in ranked if c.contribution_pct is not None]
    if not rated:
        return None, None
    top = rated[0]
    kept = top.contribution_pct.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    name = _short_branch(top.branch_name or "")
    if scope.branch_id is not None:
        sentence = f"{name} keeps about AED {kept} of every 100 it takes."
    elif len(rated) == 1:
        sentence = (
            f"Look at {name} first: it keeps about AED {kept} of every 100 it takes, "
            "the only branch with a figure."
        )
    else:
        count = _NUMBER_WORDS.get(len(rated), str(len(rated)))
        sentence = (
            f"Look at {name} first: it keeps about AED {kept} of every 100 it takes, "
            f"the least of the {count}."
        )
    if top.quality is Quality.INCOMPLETE:
        sentence += " Its figure is incomplete - its row says why."
    return sentence, top


def item_answer(
    rows: Sequence[contribution.ItemRow],
    chain: contribution.Contribution,
    scope: signals.Scope,
    currency: str,
) -> tuple[str | None, contribution.ItemRow | None]:
    """The dish that sells and does not earn: among the popular-and-low-margin
    candidates (C13.2), the one that sold the most - the wire example's
    sentence, composed here so the screen never words it a second way."""
    fired = signals.popular_low_margin(rows, chain, scope=scope, currency=currency)
    if not fired:
        return None, None
    by_id = {r.menu_item_id: r for r in rows if r.branch_id == scope.branch_id}
    best = max(fired, key=lambda s: by_id[s.menu_item_id].net_item_sales)
    where = "" if scope.branch_name is None else f" at {_short_branch(scope.branch_name)}"
    return (
        f"{best.menu_item_name} sells more than any item{where} that earns under "
        "the menu's average.",
        by_id[best.menu_item_id],
    )


def _worse(first: Quality, second: Quality) -> Quality:
    return (
        first if contribution._QUALITY_RANK[first] <= contribution._QUALITY_RANK[second] else second
    )


# --- serialisation --------------------------------------------------------------


def _item_row_json(row: contribution.ItemRow) -> dict:
    return {
        "menu_item_id": row.menu_item_id,
        "menu_item_name": row.menu_item_name,
        "category": row.category,
        "branch_id": row.branch_id,
        "qty_sold": _dec(row.qty_sold),
        "qty_refunded": _dec(row.qty_refunded),
        "net_item_sales": _dec(row.net_item_sales),
        "cost_per_portion": _dec(row.cost_per_portion),
        "cost": _dec(row.cost),
        "cost_per_portion_today": _dec(row.cost_per_portion_today),
        "contribution": _dec(row.contribution),
        "contribution_pct": _dec(row.contribution_pct),
        "avg_sold_at": _dec(row.avg_sold_at),
        "net_price": _dec(row.net_price),
        "plate_quality": row.plate_quality,
        "quality": row.quality.value,
        "notes": list(row.notes),
        "recipe_version": row.recipe_version,
        "till_items": [
            {"till_item_id": t.till_item_id, "name": t.name, "code": t.code} for t in row.till_items
        ],
        "components": [
            {
                "ingredient_id": c.ingredient_id,
                "ingredient_name": c.ingredient_name,
                "qty": _dec(c.qty),
                "unit": c.unit,
                "cost_per_portion": _dec(c.cost_per_portion),
                "invoice_id": c.invoice_id,
                "line_position": c.line_position,
                "purchased_on": _iso(c.purchased_on),
            }
            for c in row.components
        ],
        "archived": row.archived,
    }


def _league_row_json(row: ratio.BranchRow, figure: contribution.Contribution) -> dict:
    return {
        "branch_id": row.branch_id,
        "branch_name": row.branch_name,
        "window": {
            "from": _iso(row.window.start),
            "to": _iso(row.window.end),
            "days": row.window.days,
        },
        "net_sales": _dec(row.net_sales),
        "takings": _dec(row.takings),
        "purchases": _dec(row.purchases),
        "ratio_pct": _dec(row.ratio_pct),
        "contribution": _dec(figure.contribution),
        "contribution_pct": _dec(figure.contribution_pct),
        "costed_share_pct": _dec(figure.costed_share_pct),
        "ratio_quality": row.quality.value,
        "ratio_notes": list(row.notes),
        "contribution_quality": figure.quality.value,
        "contribution_notes": list(figure.notes),
        "days_loaded": row.days_loaded,
        "days_missing": row.days_missing,
        "deliveries": row.deliveries,
        "sales_through": _iso(row.sales_through),
        "last_purchase_on": _iso(row.last_purchase_on),
    }


def _signal_json(signal: signals.Signal) -> dict:
    return {
        "kind": signal.kind,
        "money_at_stake": _dec(signal.money_at_stake),
        "quality": signal.quality.value,
        "sentence": signal.sentence,
        "detail": signal.detail,
        "branch_id": signal.branch_id,
        "branch_name": signal.branch_name,
        "menu_item_id": signal.menu_item_id,
        "menu_item_name": signal.menu_item_name,
        "ingredient_id": signal.ingredient_id,
        "ingredient_name": signal.ingredient_name,
        "invoice_id": signal.invoice_id,
        "moved_on": _iso(signal.moved_on),
    }


def _paper_json(row: asyncpg.Record) -> dict:
    return {
        "invoice_id": str(row["id"]),
        "supplier_name": row["supplier_name"],
        "invoice_no": row["invoice_no"],
        "total": _dec(row["total"]),
        "invoice_date": _iso(row["invoice_date"]),
        "branch_name": row["branch_name"],
        "status": row["status"],
        "is_duplicate": row["duplicate_of_invoice_id"] is not None,
    }


def _group_pairs(lines: Iterable[asyncpg.Record]) -> dict[str, list[asyncpg.Record]]:
    pairs: dict[str, list[asyncpg.Record]] = {}
    for line in lines:
        pairs.setdefault(line["ingredient_id"], []).append(line)
    return pairs


# --- the route ------------------------------------------------------------------


@router.get("/dashboard")
async def dashboard(
    request: Request,
    ctx: Context,
    date_from: Annotated[datetime.date | None, Query(alias="from")] = None,
    date_to: Annotated[datetime.date | None, Query(alias="to")] = None,
    branch_id: str | None = None,
) -> dict:
    """The whole owner screen in one read (§3.1). `branch_id` filters the
    league, the item rows and the signals to that branch - the signals then
    about the branch against the chain's benchmark (C13.6), the papers
    narrowed to it - and `total` always stays the chain, so a branch is
    compared to the chain and never to itself. A branch outside the tenant
    is absent, not forbidden: 404."""
    db: Database = request.app.state.db
    tenant_id = ctx.tenant_id
    today = datetime.datetime.now(datetime.UTC).date()

    # The reads, in the enumerated order `test_dashboard.py` counts.
    newest_by_branch = await db.newest_sales_dates(tenant_id=tenant_id)
    newest = max(newest_by_branch.values()) if newest_by_branch else None
    months = await db.sales_months(tenant_id=tenant_id)
    try:
        period, default = ratio.resolve_period(newest, date_from, date_to, today=today)
    except ratio.PeriodError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    currency = await db.tenant_currency(tenant_id) or ""
    branches = await db.list_branches(tenant_id=tenant_id)
    names = {branch["id"]: branch["name"] for branch in branches}
    scope = signals.CHAIN
    if branch_id is not None:
        if branch_id not in names:
            raise HTTPException(status_code=404, detail="branch not found")
        scope = signals.Scope(branch_id, names[branch_id])

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
    ratio_rows = {
        branch["id"]: ratio.period_row(
            branch_id=branch["id"],
            branch_name=branch["name"],
            days=days,
            invoices=invoices,
            period=period,
            tenant_currency=currency,
            latest_sales_day=newest_by_branch.get(branch["id"]),
        )
        for branch in branches
    }
    unassigned = ratio.unassigned_group(invoices, period, currency)
    ratio_total = ratio.chain_total(list(ratio_rows.values()), unassigned)

    # The menu twice from one set of rows: the period's plates and today's.
    menu_rows, components_by_item, plate_by_item, vat_rate, prices = await _menu_context(
        db, tenant_id, as_of=period.end
    )
    prices_today, stale_today, _ = await _pricing(db, tenant_id)
    plates_today = _plates_for(menu_rows, components_by_item, prices_today, stale_today, vat_rate)
    menu = _menu_items(menu_rows, components_by_item, plate_by_item, prices, vat_rate)

    sales = [
        _item_sales(row)
        for row in await db.list_period_item_sales(
            tenant_id=tenant_id, date_from=period.start, date_to=period.end
        )
    ]
    pairs = _group_pairs(await db.list_price_move_pairs(tenant_id=tenant_id, as_of=period.end))
    moves = price_moves(pairs, menu_rows, components_by_item, plate_by_item)
    papers = await db.list_invoices(tenant_id=tenant_id, branch_id=branch_id)

    # Contribution: every branch's rows, the chain's, the figures, the order.
    branch_rows = contribution.item_rows(
        sales, menu, today_plates=plates_today, costed_at=period.end, currency=currency
    )
    chain_rows = contribution.chain_item_rows(
        branch_rows,
        menu,
        branch_names=names,
        today_plates=plates_today,
        costed_at=period.end,
        currency=currency,
    )
    all_rows = [*branch_rows, *chain_rows]
    figures = [
        contribution.branch_contribution(
            [r for r in branch_rows if r.branch_id == branch["id"]],
            branch_id=branch["id"],
            branch_name=branch["name"],
            sales_quality=ratio_rows[branch["id"]].sales_quality,
            sales_notes=ratio_rows[branch["id"]].sales_notes,
            unmapped=contribution.unmapped(sales, branch_id=branch["id"]),
        )
        for branch in branches
    ]
    chain = contribution.chain_contribution(figures, unmapped=contribution.unmapped(sales))
    ranked = contribution.rank(figures)
    league = [c for c in ranked if scope.branch_id is None or c.branch_id == scope.branch_id]

    fired = signals.compute(
        rows=all_rows,
        chain=chain,
        branches=[
            signals.BranchFigure(window=ratio_rows[c.branch_id].window, contribution=c)
            for c in ranked
            if c.branch_id is not None
        ],
        moves=moves,
        sales=sales,
        menu=menu,
        period=period,
        scope=scope,
        currency=currency,
    )

    # The answer: the branch first, then the dish, and the worse of their words.
    branch_sentence, top_branch = branch_answer(league, scope)
    item_sentence, top_item = item_answer(all_rows, chain, scope, currency)
    answer_quality = Quality.RELIABLE
    answer_notes: list[str] = []
    if top_branch is not None:
        answer_quality = _worse(answer_quality, top_branch.quality)
        answer_notes.extend(top_branch.notes)
    if top_item is not None:
        answer_quality = _worse(answer_quality, top_item.quality)
    if top_branch is None and top_item is None:
        answer_quality = Quality.UNAVAILABLE

    # Freshness and the newest day (P6, P8): derived from the days already read.
    age = None if newest is None else (today - newest).days
    last_purchase = max(
        (row.last_purchase_on for row in ratio_rows.values() if row.last_purchase_on is not None),
        default=None,
    )
    latest_day = None
    if newest is not None and period.start <= newest <= period.end:
        on_day = [d for d in days if d.business_date == newest]
        latest_day = {
            "date": _iso(newest),
            "net_sales": _dec(sum((d.net_sales for d in on_day), Decimal(0)).quantize(ratio.FILS)),
            "branches": [
                {
                    "branch_id": d.branch_id,
                    "branch_name": names.get(d.branch_id),
                    "date": _iso(d.business_date),
                    "net_sales": _dec(d.net_sales),
                }
                for d in on_day
            ],
        }

    # The papers waiting: two counts from the one read, five listed.
    held = [p for p in papers if p["status"] == "needs_review"]
    awaiting = sum(1 for p in papers if p["status"] == "awaiting_confirm")

    scope_rows = [r for r in all_rows if r.branch_id == scope.branch_id]
    costed = [r for r in scope_rows if r.costed]
    unmapped = contribution.unmapped(sales, branch_id=scope.branch_id)
    live = [row for row in menu_rows if row["archived_at"] is None]

    return {
        "period": {
            "from": _iso(period.start),
            "to": _iso(period.end),
            "days": period.days,
            "default": default,
            "sales_through": _iso(newest),
            "sales_age_days": age,
            "months": [month.strftime("%Y-%m") for month in months],
            "costed_at": _iso(period.end),
        },
        "answer": {
            "branch": branch_sentence,
            "item": item_sentence,
            "quality": answer_quality.value,
            "notes": answer_notes,
        },
        "freshness": {
            "sales_through": _iso(newest),
            "sales_age_days": age,
            "last_purchase_on": _iso(last_purchase),
            "branches_without_sales": sum(
                1 for row in ratio_rows.values() if row.net_sales is None
            ),
            "quality": (
                "estimated"
                if age is not None and age > FRESHNESS_STALE_DAYS
                else "reliable_with_limitations"
            ),
            "sentence": freshness_sentence(newest, today),
        },
        "latest_day": latest_day,
        "approvals": {
            "count": len(held),
            "duplicates": sum(1 for p in held if p["duplicate_of_invoice_id"] is not None),
            "awaiting_confirm": awaiting,
            "invoices": [_paper_json(p) for p in held[:PAPERS_LISTED]],
        },
        "league": [_league_row_json(ratio_rows[c.branch_id], c) for c in league],
        "unassigned": {"count": unassigned.count, "purchases": _dec(unassigned.purchases)},
        "scope": {"branch_id": scope.branch_id, "branch_name": scope.branch_name},
        "total": {
            "net_sales": _dec(ratio_total.net_sales),
            "purchases": _dec(ratio_total.purchases),
            "ratio_pct": _dec(ratio_total.ratio_pct),
            "contribution": _dec(chain.contribution),
            "contribution_pct": _dec(chain.contribution_pct),
            "costed_share_pct": _dec(chain.costed_share_pct),
            "ratio_quality": ratio_total.quality.value,
            "ratio_notes": list(ratio_total.notes),
            "contribution_quality": chain.quality.value,
            "contribution_notes": list(chain.notes),
        },
        "items": {
            "top": [_item_row_json(r) for r in costed[:ITEMS_SLICE]],
            "bottom": [_item_row_json(r) for r in costed[-ITEMS_SLICE:]]
            if len(costed) > ITEMS_SLICE
            else [],
            "all": [_item_row_json(r) for r in scope_rows],
            "count": len(costed),
        },
        "signals": [_signal_json(s) for s in fired],
        "unmapped": {"names": unmapped.names, "value": _dec(unmapped.value)},
        "menu": {
            "items": len(live),
            "costed": sum(
                1 for row in live if plates_today[row["id"]].cost_per_portion is not None
            ),
        },
    }
