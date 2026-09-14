"""The period read: the front door every period screen starts from
(2026-09-14, architecture review candidate 2; CONTEXT.md "Period read").

One tenant, one period, read once: the period the rule resolved, the
tenant's branches, the loaded days and the confirmed papers as the ratio
module reads them, every branch's clipped window (`ratio.period_row`, called
here and nowhere else - C11, C12.9), the papers no branch claimed and the
chain total that reconciles the table, the menu costed at the prices in
force on the period's last day (`menu.costed_menu`, M9 C12.4), and the
period's item sales as `contribution` reads them. The dashboard, the sales
screen and the usage printout each take a `PeriodRead` and derive their own
figures from it, so two screens over one period cannot disagree on a window
or a plate (P9): before this module each of them opened with its own copy of
these reads, and the windows on `/sales` were built a second time in a
second comprehension.

Nothing derived is computed here. Contribution, the signals, the price
moves and the usage rows differ per consumer (the dashboard costs the menu a
second time, today; the printout adds the material purchases), so they stay
where they are and read their inputs off the one value.

The reads are a fixed list whatever the menu's length or the branch count
(D10, D16): `READS` names them in order, as `db.py` names them, and a test
measures that `read_period` makes exactly that many. A consumer's own test
derives its maximum from this list plus its extras rather than typing the
number again.

`today` is the caller's date, never the machine's (C15.6): the routes pass
the UTC date, the brief job passes the recipient's local date, and the
usage printout passes the date it already resolved its period against.
"""

import datetime
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import NamedTuple

import asyncpg

from . import contribution, plates, ratio
from .db import Database
from .menu import CostedMenu, costed_menu
from .provenance import asserted_fields

#: The reads `read_period` makes, in order, as `db.py` names them. A new
#: read is added here, and one taken out leaves; the count tests derive
#: their maximum from the length.
READS: tuple[str, ...] = (
    "newest_sales_dates",
    "sales_months",
    "tenant_currency",
    "list_branches",
    "list_sales_days",
    "list_period_invoices",
    # `menu.costed_menu` as of the period's end: `pricing`'s three, then the
    # recipes and the items.
    "tenant_currency",
    "list_mapped_pack_costs",
    "list_newest_purchases",
    "list_current_recipe_components",
    "list_menu_items",
    "list_period_item_sales",
)


class ResolvedPeriod(NamedTuple):
    """The period a read covers and the two facts every period line states:
    the tenant's newest loaded day, per branch and overall (the freshness
    fact), and the months that hold sales (the picker's choices, WP-84
    review). `default` says the rule chose the period rather than the
    caller."""

    period: ratio.Period
    default: bool
    newest_by_branch: Mapping[str, datetime.date]
    newest: datetime.date | None
    months: tuple[datetime.date, ...]


async def resolve(
    db: Database,
    tenant_id: str,
    *,
    today: datetime.date,
    date_from: datetime.date | None,
    date_to: datetime.date | None,
) -> ResolvedPeriod:
    """The first two reads and the period rule (`ratio.resolve_period`, M9
    C6 extended). Raises `ratio.PeriodError` for a period the rule refuses;
    a route turns it into 422 with the rule's own sentence, and a caller
    without a request lets it through. `/sales/coverage` and `/sales/days`
    stop here: they are not period reads of the full kind."""
    newest_by_branch = await db.newest_sales_dates(tenant_id=tenant_id)
    newest = max(newest_by_branch.values()) if newest_by_branch else None
    months = await db.sales_months(tenant_id=tenant_id)
    period, default = ratio.resolve_period(newest, date_from, date_to, today=today)
    return ResolvedPeriod(period, default, newest_by_branch, newest, tuple(months))


@dataclass(frozen=True)
class PeriodRead:
    """Everything a period screen starts from. `ratio_rows` is every branch's
    clipped window keyed by branch id, in the branches' own order;
    `unassigned` and `ratio_total` are the two rows that reconcile the table;
    `menu` is the whole menu costed as of `period.end`; `items` is that same
    menu as `contribution` reads it, each component carrying the invoice
    line behind its price (C12.4a); `sales` is the period's item days."""

    tenant_id: str
    today: datetime.date
    resolved: ResolvedPeriod
    currency: str
    branches: tuple[asyncpg.Record, ...]
    days: tuple[ratio.SalesDay, ...]
    invoices: tuple[ratio.Invoice, ...]
    ratio_rows: Mapping[str, ratio.BranchRow]
    unassigned: ratio.Unassigned
    ratio_total: ratio.Total
    menu: CostedMenu
    items: Mapping[str, contribution.MenuItem]
    sales: tuple[contribution.ItemSales, ...]

    @property
    def period(self) -> ratio.Period:
        return self.resolved.period

    @property
    def default(self) -> bool:
        return self.resolved.default

    @property
    def newest(self) -> datetime.date | None:
        return self.resolved.newest

    @property
    def newest_by_branch(self) -> Mapping[str, datetime.date]:
        return self.resolved.newest_by_branch

    @property
    def months(self) -> tuple[datetime.date, ...]:
        return self.resolved.months

    @property
    def names(self) -> dict[str, str]:
        """Branch id to branch name, for every branch the tenant owns."""
        return {branch["id"]: branch["name"] for branch in self.branches}


async def read_period(
    db: Database,
    tenant_id: str,
    *,
    today: datetime.date,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
) -> PeriodRead:
    """The period read, in the order `READS` lists. Raises
    `ratio.PeriodError` the way `resolve` does; a branch filter is the
    consumer's to apply, because `total` always stays the chain (the
    dashboard's rule) and the printout's scope is a rendering choice."""
    resolved = await resolve(db, tenant_id, today=today, date_from=date_from, date_to=date_to)
    period = resolved.period
    currency = await db.tenant_currency(tenant_id) or ""
    branches = tuple(await db.list_branches(tenant_id=tenant_id))

    days = tuple(
        sales_day_input(row)
        for row in await db.list_sales_days(
            tenant_id=tenant_id, date_from=period.start, date_to=period.end
        )
    )
    invoices = tuple(
        invoice_input(row)
        for row in await db.list_period_invoices(
            tenant_id=tenant_id, date_from=period.start, date_to=period.end
        )
    )
    ratio_rows = {
        branch["id"]: ratio.period_row(
            branch_id=branch["id"],
            branch_name=branch["name"],
            days=list(days),
            invoices=list(invoices),
            period=period,
            tenant_currency=currency,
            latest_sales_day=resolved.newest_by_branch.get(branch["id"]),
        )
        for branch in branches
    }
    unassigned = ratio.unassigned_group(list(invoices), period, currency)
    ratio_total = ratio.chain_total(list(ratio_rows.values()), unassigned)

    menu = await costed_menu(db, tenant_id, as_of=period.end)
    items = menu_items(menu)

    sales = tuple(
        item_sales_input(row)
        for row in await db.list_period_item_sales(
            tenant_id=tenant_id, date_from=period.start, date_to=period.end
        )
    )
    return PeriodRead(
        tenant_id=tenant_id,
        today=today,
        resolved=resolved,
        currency=currency,
        branches=branches,
        days=days,
        invoices=invoices,
        ratio_rows=ratio_rows,
        unassigned=unassigned,
        ratio_total=ratio_total,
        menu=menu,
        items=items,
        sales=sales,
    )


# --- adapters: rows into the pure modules' inputs ------------------------------


def sales_day_input(row: asyncpg.Record) -> ratio.SalesDay:
    return ratio.SalesDay(
        branch_id=row["branch_id"],
        business_date=row["business_date"],
        net_sales=row["net_sales"],
        takings=row["takings"],
        granularity=row["granularity"],
    )


def invoice_input(row: asyncpg.Record) -> ratio.Invoice:
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


def item_sales_input(row: asyncpg.Record) -> contribution.ItemSales:
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


def menu_items(menu: CostedMenu) -> dict[str, contribution.MenuItem]:
    """The menu as `contribution` reads it: each item's as-of plate, its
    current recipe version, and every component with the invoice line behind
    the price that costed it (C12.4a). The batch cost is the same
    multiplication `plates.cost_component` makes - the quantity in base units,
    divided by the conversion yield when the line has one (M12 WP-119, D13),
    times the price per base unit - and None when there is no price or the
    unit does not convert, so a hole is a hole here too.

    The share rides along on the component too, so the dish's contribution and
    M12's usage figure divide by the same number this cost did."""
    items: dict[str, contribution.MenuItem] = {}
    for row in menu.rows:
        components: list[contribution.RecipeComponent] = []
        for component in menu.components_by_item.get(row["id"], []):
            price = menu.prices.get(component["ingredient_id"])
            batch_cost = invoice_id = position = purchased_on = None
            if price is not None:
                converted = plates.to_base_qty(component["qty"], component["unit"])
                if converted is not None and converted[1] == price["cost_base_unit"]:
                    bought = plates.bought_base_qty(converted[0], component["usable_share"])
                    batch_cost = bought * price["cost_per_base_unit"]
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
                    usable_share=component["usable_share"],
                )
            )
        archived_at = row["archived_at"]
        items[row["id"]] = contribution.MenuItem(
            menu_item_id=row["id"],
            name=row["name"],
            plate=menu.plate_by_item[row["id"]],
            selling_price=row["selling_price"],
            yield_portions=row["yield_portions"] or Decimal(1),
            vat_rate=menu.vat_rate,
            category=row["category"],
            recipe_version=row["version"],
            components=tuple(components),
            archived=archived_at is not None,
            archived_on=None if archived_at is None else archived_at.date(),
            recipe_created_on=(
                None if row["recipe_created_at"] is None else row["recipe_created_at"].date()
            ),
        )
    return items
