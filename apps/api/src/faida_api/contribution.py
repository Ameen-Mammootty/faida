"""M9 WP-90: item and branch contribution, derived on every read
(Docs/M9_DECOMPOSITION.md §3, C12 and the C9 extension; plan.md §7.2).

M6 costs a plate. M8 says how many plates were sold, in which branch, and
what the branch took. Neither multiplies. This module multiplies: a karak
that earns AED 8.77 a cup is a fact about one cup; a karak that sold 1,400
cups and earned AED 12,280 is a fact about the business, and it is the second
one an owner acts on.

Pure module: no I/O, `Decimal` only, every sentence composed here. The route
feeds it the period's item days (`db.list_period_item_sales`), the menu costed
at the prices in force on the period's last day, and - optionally - today's
plates; it serialises what comes back (C4: money is `Decimal` here and a
string on the wire). Nothing is stored. A contribution figure derives on every
read, so confirming a cheaper milk invoice moves every karak on the next
screen load with no write anywhere (the WP-54 rule, three layers up).

The arithmetic, and where each rounding happens (C12.2, C12.6a):

    portions        sum(qty) on lines that took money
                    - sum(abs(qty)) on lines that gave it back, so a till
                      that prints a refund as `qty 1, amount -20` and one
                      that prints `qty -1` give the same answer
    cost            portions x plate.cost_per_portion, quantized to the fil
    contribution    net item sales - cost, exact from there
    margin %        contribution / net item sales, to a tenth, withheld
                    (None, never 0) when net item sales are not positive

Rounding the cost once and subtracting exactly means the three figures on a
row reconcile when a reader subtracts them, and a branch's contribution is
the exact sum of its rows' - which is what makes C12.8's chain invariant hold
to the fil rather than to a fil or two.

What is missing never reads as a zero. A mapped item whose plate is
`incomplete` produces one row with every cost number null and the plate's own
`missing` sentences (`/menu`'s rule verbatim, `plates.py:218-219`); a counted
line with no quantity cannot be multiplied, so its item's row carries no
quantity and no contribution and says how many lines had none. Both kinds of
row are listed, both leave every aggregate, both lower the costed share, and
- C9 extended, as pinned at the second review - **neither downgrades the
label**: an aggregate carries the worse of its own sales-side window label
(from `ratio.period_row`, read here and never re-worded) and the worst plate
label among the rows that did produce numbers, with the share as a fact
beside the figure. One till line with no quantity must not mark a whole chain
*incomplete* until the till fixes its export; that is the unearned pessimism
that teaches an owner to ignore a label.

The cost side is one number, not two: packaging is a recipe component with a
piece dimension (`plan.md` §7.3 row 61), so `plates.plate().cost_per_portion`
already contains it and every surface says "ingredients and packaging" in
words. Faida cannot tell whether a recipe's cup was loaded, which is why
every row carries its components by name with the invoice line behind each
price - that is where a missing cup is visible.

Never "profit" and never "food cost %" (§3's display rules): a branch figure
is *contribution before overheads*, an estimate, and it covers only the
costed share of that branch's sales.
"""

import datetime
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from . import plates

# `_plural` and `_short_date` come from `ratio.py` rather than being written
# again here on purpose: "2 of 7 days", "3 deliveries" and "25-31 Aug" are
# worded by one function, so `/sales` and the dashboard can never say the same
# thing two ways. The quanta and the vocabulary come from there for the same
# reason - a percentage is a tenth on both screens or on neither.
from .ratio import (
    FILS,
    PCT_QUANTUM,
    Period,
    Quality,
    Window,
    _plural,
    _short_date,
)

#: Portions, as the till prints them (`sales_lines.qty` is numeric(12,3)).
QTY_QUANTUM = Decimal("0.001")

#: A whole percent, for the sentences that carry a share in words. The field
#: beside them stays at `PCT_QUANTUM`.
WHOLE_PCT = Decimal("1")

#: The currency the sentences name when the caller does not say. Follows
#: `replies.DEFAULT_CURRENCY`, which does the same for the WhatsApp replies.
DEFAULT_CURRENCY = "AED"

#: How far an item's average selling price may sit from today's menu price
#: before the row says so (C12.2). Net amounts are stored to the fil per line
#: (0019:193), so an item sold at exactly the menu price all week lands a fil
#: either side of it once the lines are summed; more than that is a real
#: difference - a discount, or a menu price that has moved since. This is not
#: a tuned threshold: it is the precision the numbers are stored at, which is
#: the only honest place to put the line.
SOLD_AT_TOLERANCE = FILS

#: Precedence, worst first - `ratio._QUALITY_RANK`'s order, one layer up.
_QUALITY_RANK = {
    Quality.UNAVAILABLE: 0,
    Quality.INCOMPLETE: 1,
    Quality.ESTIMATED: 2,
    Quality.RELIABLE: 3,
}

#: A plate's vocabulary onto a period figure's (C9 extended). `verified` is
#: absent from both, and `unavailable` is a fact about a branch's sales, never
#: about a plate.
_PLATE_QUALITY = {
    plates.PlateQuality.RELIABLE: Quality.RELIABLE,
    plates.PlateQuality.ESTIMATED: Quality.ESTIMATED,
    plates.PlateQuality.INCOMPLETE: Quality.INCOMPLETE,
}


def _worse(first: Quality, second: Quality) -> Quality:
    return first if _QUALITY_RANK[first] <= _QUALITY_RANK[second] else second


# --- inputs -----------------------------------------------------------------


@dataclass(frozen=True)
class ItemSales:
    """One branch-item-day, as `db.list_period_item_sales` returns it: summed
    in SQL and never over lines in Python (C11.8's rule, C12.1).

    The day is the grain because two of M9's rules need it - the portions
    sold since a price move, and a chain benchmark over one branch's own
    clipped window - and neither can be recovered from a period total. The
    wire carries no day array; only this read has one.

    The quantity filters take a line's *amount* sign, not its quantity's, so
    both ways a till prints a refund land in the same place (C12.6a).
    """

    branch_id: str
    business_date: datetime.date
    till_item_id: str
    name: str
    code: str | None
    menu_item_id: str | None
    excluded: bool
    #: sum(qty) over lines whose net amount is >= 0.
    qty_sold: Decimal
    #: sum(abs(qty)) over lines whose net amount is < 0.
    qty_refunded: Decimal
    #: sum(net_amount) over lines whose net amount is > 0 - C11.8's own
    #: denominator, the half a costed share is measured on.
    positive_value: Decimal
    #: sum(net_amount) over lines whose net amount is < 0. Negative.
    refund_value: Decimal
    #: How many of the day's lines printed no quantity at all (C12.6).
    no_qty_lines: int

    @property
    def net_item_sales(self) -> Decimal:
        return self.positive_value + self.refund_value


@dataclass(frozen=True)
class RecipeComponent:
    """One component of the as-of plate: what the recipe asks for, its share
    of the batch cost, and the invoice line whose price costed it (C12.4a).

    `batch_cost` is `plates.ComponentCost.cost` at full precision - the cost
    of the whole batch, not of one portion - because the division by the
    batch yield belongs where every other division does, here, once.
    """

    ingredient_id: str
    ingredient_name: str
    qty: Decimal
    unit: str
    batch_cost: Decimal | None = None
    invoice_id: str | None = None
    line_position: int | None = None
    purchased_on: datetime.date | None = None


@dataclass(frozen=True)
class MenuItem:
    """One menu item costed at the prices in force on the period's last day:
    the plate `plates.plate()` returned, the recipe version behind it, and the
    components with their lineage.

    The recipe is the **current** version, by decision (C12.4): recipes are
    loaded at onboarding after the sales they cost, so an as-of recipe read
    would mark every onboarding month incomplete. Editing a recipe therefore
    moves every period the dish appears in, and the row says *recipe version
    N* so a reader can see which.
    """

    menu_item_id: str
    name: str
    plate: plates.Plate
    selling_price: Decimal
    yield_portions: Decimal
    vat_rate: Decimal | None = None
    category: str | None = None
    recipe_version: int | None = None
    components: tuple[RecipeComponent, ...] = ()
    archived: bool = False
    archived_on: datetime.date | None = None


# --- outputs ----------------------------------------------------------------


@dataclass(frozen=True)
class TillItem:
    """One name the till printed for this dish. Two names mapped to one menu
    item make one row, both listed - a rename is not two dishes (C12.1)."""

    till_item_id: str
    name: str
    code: str | None


@dataclass(frozen=True)
class Component:
    """One component's share of what a portion cost, and the invoice line the
    price came from, so "every number traces to source" needs no second read:
    the drill links `/invoices/<invoice_id>#line-<line_position>`."""

    ingredient_id: str
    ingredient_name: str
    qty: Decimal
    unit: str
    cost_per_portion: Decimal | None
    invoice_id: str | None = None
    line_position: int | None = None
    purchased_on: datetime.date | None = None


@dataclass(frozen=True)
class ItemRow:
    """One (menu item, branch, period), or one (menu item, chain, period) when
    `branch_id` is None (§3.1's `ItemRow`).

    A row with no contribution carries `cost_per_portion`, `cost`,
    `contribution` and `contribution_pct` as None and its reasons in `notes`,
    exactly as `plates.Plate` does: a hole never renders as a fat margin. When
    the hole is a missing quantity the portions go with it, because a partial
    count of a week is not a count of a week; when it is an incomplete plate
    the quantities and the money stay, because what a dish sold is exactly the
    fact that makes an uncosted dish worth mapping.
    """

    menu_item_id: str
    menu_item_name: str
    category: str | None
    branch_id: str | None
    qty_sold: Decimal | None
    qty_refunded: Decimal | None
    net_item_sales: Decimal
    cost_per_portion: Decimal | None
    cost: Decimal | None
    contribution: Decimal | None
    contribution_pct: Decimal | None
    cost_per_portion_today: Decimal | None
    avg_sold_at: Decimal | None
    net_price: Decimal | None
    plate_quality: str
    quality: Quality
    notes: tuple[str, ...]
    recipe_version: int | None
    till_items: tuple[TillItem, ...]
    components: tuple[Component, ...]
    archived: bool
    #: The positive half of this row's net item sales: the numerator and the
    #: denominator of a costed share are both measured on it (C12.7a), never
    #: on net sales, or a refund-heavy week would push the share past 100%.
    positive_value: Decimal
    #: How many counted lines printed no quantity (C12.6). Kept on the row so
    #: a chain row can say how many there were across the branches.
    no_qty_lines: int = 0

    @property
    def costed(self) -> bool:
        """Whether this row produced numbers - the one test for whether it
        enters an aggregate, lowers a costed share, or does both."""
        return self.contribution is not None


@dataclass(frozen=True)
class Unmapped:
    """Till names with sales in the window that nobody has mapped and nobody
    has marked "not a menu item". A note beside the figure and a link to the
    queue that owns it, never a label (C9 extended)."""

    names: int
    value: Decimal


@dataclass(frozen=True)
class Contribution:
    """A branch's - or the chain's - contribution before overheads.

    **Never net profit** (PRD §23, `plan.md` §8 M9): it subtracts ingredients
    and packaging and nothing else, and it covers only the share of sales
    whose dish could be costed. Both facts are sentences on the row.
    """

    branch_id: str | None
    branch_name: str | None
    contribution: Decimal | None
    contribution_pct: Decimal | None
    #: The net item sales of the rows that produced numbers - the percentage's
    #: own denominator, never the branch's whole net sales (C12.7).
    net_item_sales: Decimal
    cost: Decimal | None
    costed_value: Decimal
    sales_value: Decimal
    costed_share_pct: Decimal | None
    quality: Quality
    notes: tuple[str, ...]
    #: The two halves the label is made of, kept so the chain rolls them up
    #: the same way and a test can see which half moved.
    sales_quality: Quality
    cost_quality: Quality | None
    items: int
    items_without_numbers: int
    unmapped: Unmapped


# --- words ------------------------------------------------------------------


def _money_words(amount: Decimal, currency: str) -> str:
    """A headline figure in words: rounded dirhams, thousands separated
    (§3's display rule). Exact figures belong in the invoice detail."""
    return f"{currency} {amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP):,}"


def _price_words(amount: Decimal, currency: str) -> str:
    """A per-plate figure in words: fils-precise, because a plate margin
    rounded to whole dirhams carries no information at karak prices (the
    2026-08-30 design review)."""
    return f"{currency} {amount.quantize(FILS, rounding=ROUND_HALF_UP):,}"


def _pct_words(pct: Decimal) -> str:
    return f"{pct.quantize(WHOLE_PCT, rounding=ROUND_HALF_UP)}%"


def _qty_words(qty: Decimal) -> str:
    """ "2" for 2.000, "2.5" for 2.500 - the till's trailing zeros are its
    own, not information."""
    normalized = qty.normalize()
    if normalized == normalized.to_integral_value():
        normalized = normalized.to_integral_value()
    return f"{normalized:f}"


def _long_date(day: datetime.date) -> str:
    """ "31 Aug 2026" - the year included, because a contribution figure is
    read months after the period it covers."""
    return f"{day.day} {day.strftime('%b')} {day.year}"


def _names_words(names: Sequence[str]) -> str:
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _pct(part: Decimal, whole: Decimal) -> Decimal | None:
    """A percentage to a tenth, withheld - None, never 0 - when the
    denominator is not positive (C11.6's rule, one layer up)."""
    if whole <= 0:
        return None
    return (part / whole * 100).quantize(PCT_QUANTUM, rounding=ROUND_HALF_UP)


# --- rolling the days up (C12.1) --------------------------------------------
#
# The read is one query whatever the period (D10) and returns one row per
# branch, till item and business day. Every scope this milestone needs is a
# filter over those rows in Python, the way `ratio.period_row` rolls up
# `db.list_sales_days`' `SalesDay` rows: C11.8's "sum in SQL, never over lines
# in Python" is a rule about *lines*, not about day sums (second review, D4).


def days_between(
    sales: Iterable[ItemSales],
    start: datetime.date,
    end: datetime.date,
    *,
    branch_id: str | None = None,
) -> list[ItemSales]:
    """The item days inside a date range, inclusive, optionally one branch's."""
    return [
        row
        for row in sales
        if start <= row.business_date <= end and (branch_id is None or row.branch_id == branch_id)
    ]


def days_in_period(
    sales: Iterable[ItemSales], period: Period, *, branch_id: str | None = None
) -> list[ItemSales]:
    """The whole period - what the item table and the chain figure read."""
    return days_between(sales, period.start, period.end, branch_id=branch_id)


def days_in_window(
    sales: Iterable[ItemSales], window: Window, *, branch_id: str | None = None
) -> list[ItemSales]:
    """One branch's clipped window (`ratio.BranchRow.window`) - what a chain
    benchmark is recomputed over, so a branch that loaded three days is never
    compared against siblings who loaded seven (C13.2's branch gap).

    Over that branch's own rows this returns exactly what `days_in_period`
    does, because a day outside the loaded range has no sales rows at all
    (C12.6b); a test pins it, so the league and the item table cannot drift
    apart by a day.
    """
    return days_between(sales, window.start, window.end, branch_id=branch_id)


def days_since(
    sales: Iterable[ItemSales], on_or_after: datetime.date, *, branch_id: str | None = None
) -> list[ItemSales]:
    """The days on or after a date - what a price move is weighted by (C13.2):
    the portions sold since the delivery landed, never the whole window, which
    would charge the owner for plates sold at the old price."""
    return [
        row
        for row in sales
        if row.business_date >= on_or_after and (branch_id is None or row.branch_id == branch_id)
    ]


def unmapped(sales: Iterable[ItemSales], *, branch_id: str | None = None) -> Unmapped:
    """The till names with sales here that have no menu item and no exclusion
    - the honest count beside a contribution figure, and the link to the
    mapping queue that owns them (C12.7a). Never `ratio.coverage`: that asks
    what the menu can cost *today*, and this asks what could be costed at the
    period's prices, so computing one from the other would put two numbers on
    one screen that quietly mean different things."""
    names: dict[str, Decimal] = {}
    for row in sales:
        if row.excluded or row.menu_item_id is not None:
            continue
        if branch_id is not None and row.branch_id != branch_id:
            continue
        names[row.till_item_id] = names.get(row.till_item_id, Decimal(0)) + row.positive_value
    return Unmapped(names=len(names), value=sum(names.values(), Decimal(0)).quantize(FILS))


# --- the item row -----------------------------------------------------------


def _components(item: MenuItem) -> tuple[Component, ...]:
    """Each component's share of one portion: the batch share divided by the
    yield, once, at plate precision - and the invoice line behind the price
    carried straight through."""
    out: list[Component] = []
    for component in item.components:
        share: Decimal | None = None
        if component.batch_cost is not None and item.yield_portions:
            share = (component.batch_cost / item.yield_portions).quantize(
                plates.PLATE_QUANTUM, rounding=ROUND_HALF_UP
            )
        out.append(
            Component(
                ingredient_id=component.ingredient_id,
                ingredient_name=component.ingredient_name,
                qty=component.qty,
                unit=component.unit,
                cost_per_portion=share,
                invoice_id=component.invoice_id,
                line_position=component.line_position,
                purchased_on=component.purchased_on,
            )
        )
    return tuple(out)


def _row(
    item: MenuItem,
    *,
    branch_id: str | None,
    till_items: tuple[TillItem, ...],
    qty_sold: Decimal,
    qty_refunded: Decimal,
    positive_value: Decimal,
    refund_value: Decimal,
    no_qty_lines: int,
    today_plate: plates.Plate | None,
    costed_at: datetime.date | None,
    currency: str,
    extra_notes: Sequence[str] = (),
) -> ItemRow:
    """One row from summed facts, whatever grain summed them."""
    net_item_sales = (positive_value + refund_value).quantize(FILS)
    plate = item.plate
    counted = no_qty_lines == 0

    portions: Decimal | None = None
    cost: Decimal | None = None
    contribution: Decimal | None = None
    contribution_pct: Decimal | None = None
    cost_per_portion: Decimal | None = None
    avg_sold_at: Decimal | None = None
    if counted:
        portions = (qty_sold - qty_refunded).quantize(QTY_QUANTUM)
        if portions > 0 and net_item_sales > 0:
            avg_sold_at = (net_item_sales / portions).quantize(
                plates.PLATE_QUANTUM, rounding=ROUND_HALF_UP
            )
        if plate.cost_per_portion is not None:
            cost_per_portion = plate.cost_per_portion
            # Quantized once here, and the subtraction exact from there, so
            # the three figures on the row reconcile when a reader subtracts
            # them and a branch total is the exact sum of its rows.
            cost = (portions * cost_per_portion).quantize(FILS, rounding=ROUND_HALF_UP)
            contribution = net_item_sales - cost
            contribution_pct = _pct(contribution, net_item_sales)

    net_price = plates.net_of_vat(item.selling_price, item.vat_rate)
    today_cost: Decimal | None = None
    if (
        cost_per_portion is not None
        and today_plate is not None
        and today_plate.cost_per_portion is not None
        and today_plate.cost_per_portion != cost_per_portion
    ):
        today_cost = today_plate.cost_per_portion

    quality = _worse(
        _PLATE_QUALITY[plate.quality],
        Quality.RELIABLE if counted else Quality.INCOMPLETE,
    )

    notes: list[str] = []
    notes.extend(plate.missing)
    if not counted:
        notes.append(
            f"{_plural(no_qty_lines, 'sales line')} "
            f"{'has' if no_qty_lines == 1 else 'have'} no quantity"
        )
    if counted and qty_refunded > 0:
        word = "portion" if qty_refunded == 1 else "portions"
        notes.append(f"{_qty_words(qty_refunded)} {word} refunded")
    if net_item_sales <= 0:
        notes.append("net sales are not positive for this item this period")
    if contribution is not None and contribution < 0:
        notes.append("this item costs more than it sells for")
    if avg_sold_at is not None and abs(avg_sold_at - net_price) > SOLD_AT_TOLERANCE:
        # The word *today's* is not decoration (C12.2): there is no price
        # history, so a menu price raised since a closed period would
        # otherwise read as a discount the branch never gave.
        notes.append(
            f"sold at an average {_price_words(avg_sold_at, currency)} against "
            f"today's menu price of {_price_words(net_price, currency)}"
        )
    if cost_per_portion is not None and costed_at is not None:
        notes.append(f"costed at the prices in force on {_long_date(costed_at)}")
    if today_cost is not None:
        notes.append(f"today's plate is {_price_words(today_cost, currency)}")
    if item.recipe_version is not None:
        notes.append(f"recipe version {item.recipe_version}")
    if item.archived:
        notes.append(
            "archived" if item.archived_on is None else f"archived {_short_date(item.archived_on)}"
        )
    notes.extend(extra_notes)

    return ItemRow(
        menu_item_id=item.menu_item_id,
        menu_item_name=item.name,
        category=item.category,
        branch_id=branch_id,
        qty_sold=qty_sold.quantize(QTY_QUANTUM) if counted else None,
        qty_refunded=qty_refunded.quantize(QTY_QUANTUM) if counted else None,
        net_item_sales=net_item_sales,
        cost_per_portion=cost_per_portion,
        cost=cost,
        contribution=contribution,
        contribution_pct=contribution_pct,
        cost_per_portion_today=today_cost,
        avg_sold_at=avg_sold_at,
        net_price=net_price,
        plate_quality=plate.quality.value,
        quality=quality,
        notes=tuple(notes),
        recipe_version=item.recipe_version,
        till_items=till_items,
        components=_components(item),
        archived=item.archived,
        positive_value=positive_value.quantize(FILS),
        no_qty_lines=no_qty_lines,
    )


def _order(rows: list[ItemRow]) -> list[ItemRow]:
    """Most contributed first, rows with no contribution last, ties by name.
    The item panel's top five and bottom five are slices of this one list, so
    the two panels can never disagree about what is in the middle."""
    return sorted(
        rows,
        key=lambda r: (
            r.contribution is None,
            -(r.contribution or Decimal(0)),
            r.menu_item_name,
            r.menu_item_id,
            r.branch_id or "",
        ),
    )


def item_rows(
    sales: Iterable[ItemSales],
    menu: Mapping[str, MenuItem],
    *,
    today_plates: Mapping[str, plates.Plate] | None = None,
    costed_at: datetime.date | None = None,
    currency: str = DEFAULT_CURRENCY,
) -> list[ItemRow]:
    """One row per (branch, menu item) over the days given (C12.1).

    `menu` is the tenant's items costed at the prices in force on the period's
    last day; `today_plates` is the same menu costed at today's, and a row
    carries `cost_per_portion_today` only when the two differ - which they
    routinely will, because invoices arrive daily by WhatsApp and sales by CSV
    days later, so a paper dated after the newest loaded sales day is the
    ordinary state and not the exception (C12.4, second review D5). A reader
    is never shown two costs without being told which is which.

    A line on an unmapped or excluded till name produces no row: the excluded
    ones are not menu sales at all, and the unmapped ones are `unmapped()`'s
    count beside the figures.
    """
    grouped: dict[tuple[str, str], list[ItemSales]] = {}
    for row in sales:
        if row.excluded or row.menu_item_id is None or row.menu_item_id not in menu:
            # Excluded is "not a menu item"; unmapped is the queue's job. A
            # mapped id the menu does not hold cannot happen through the
            # shipped door (menu items archive, they never delete) and is
            # left out rather than guessed at.
            continue
        grouped.setdefault((row.branch_id, row.menu_item_id), []).append(row)

    out: list[ItemRow] = []
    for (branch_id, menu_item_id), days in grouped.items():
        item = menu[menu_item_id]
        seen: dict[str, TillItem] = {}
        for day in days:
            seen.setdefault(day.till_item_id, TillItem(day.till_item_id, day.name, day.code))
        out.append(
            _row(
                item,
                branch_id=branch_id,
                till_items=tuple(sorted(seen.values(), key=lambda t: (t.name, t.till_item_id))),
                qty_sold=sum((d.qty_sold for d in days), Decimal(0)),
                qty_refunded=sum((d.qty_refunded for d in days), Decimal(0)),
                positive_value=sum((d.positive_value for d in days), Decimal(0)),
                refund_value=sum((d.refund_value for d in days), Decimal(0)),
                no_qty_lines=sum(d.no_qty_lines for d in days),
                today_plate=None if today_plates is None else today_plates.get(menu_item_id),
                costed_at=costed_at,
                currency=currency,
            )
        )
    return _order(out)


def chain_item_rows(
    rows: Iterable[ItemRow],
    menu: Mapping[str, MenuItem],
    *,
    branch_names: Mapping[str, str] | None = None,
    today_plates: Mapping[str, plates.Plate] | None = None,
    costed_at: datetime.date | None = None,
    currency: str = DEFAULT_CURRENCY,
) -> list[ItemRow]:
    """The same items across every branch, summed (C12.8).

    Completeness is per branch-item, not per item: a plate is a tenant-level
    fact and is the same everywhere, but a null quantity is a fact about one
    branch's file, so the same dish can carry numbers in Al Qusais and none in
    Rolla. A chain row therefore sums **only the branch-item pairs that
    produced numbers**, names the branches it left out and the sales value
    they hold, and takes the worse label among the pairs it summed. That is
    what makes the pinned invariant hold - chain contribution equals the sum
    of the branch contributions and equals the sum of these rows' - where a
    naive "every pair appears in the chain row" would be false the first time
    a till exports a line with no quantity.
    """
    names = branch_names or {}
    grouped: dict[str, list[ItemRow]] = {}
    for row in rows:
        grouped.setdefault(row.menu_item_id, []).append(row)

    out: list[ItemRow] = []
    for menu_item_id, group in grouped.items():
        item = menu[menu_item_id]
        counted = [r for r in group if r.costed]
        summed = counted or group
        left_out = [r for r in group if not r.costed] if counted else []

        seen: dict[str, TillItem] = {}
        for row in summed:
            for till_item in row.till_items:
                seen.setdefault(till_item.till_item_id, till_item)

        extra: list[str] = []
        if left_out:
            held = sum((r.net_item_sales for r in left_out), Decimal(0))
            known = [names.get(r.branch_id or "") for r in left_out]
            subject = (
                _names_words([name for name in known if name])
                if all(known)
                else _plural(len(left_out), "branch", "branches")
            )
            extra.append(
                f"{subject} not included in this row, "
                f"holding {_money_words(held, currency)} of sales"
            )

        out.append(
            _row(
                item,
                branch_id=None,
                till_items=tuple(sorted(seen.values(), key=lambda t: (t.name, t.till_item_id))),
                qty_sold=sum((r.qty_sold or Decimal(0) for r in summed), Decimal(0)),
                qty_refunded=sum((r.qty_refunded or Decimal(0) for r in summed), Decimal(0)),
                positive_value=sum((r.positive_value for r in summed), Decimal(0)),
                refund_value=sum((r.net_item_sales - r.positive_value for r in summed), Decimal(0)),
                no_qty_lines=0 if counted else sum(r.no_qty_lines for r in group),
                today_plate=None if today_plates is None else today_plates.get(menu_item_id),
                costed_at=costed_at,
                currency=currency,
                extra_notes=extra,
            )
        )
    return _order(out)


# --- the branch and the chain (C12.7, C12.8, C9 extended) -------------------


#: The one thing PRD §23 asks for that the schema cannot answer, said once,
#: in words, beneath the chain figure rather than on every branch row.
OVERHEADS_NOTE = "waste and variable fees are not recorded anywhere, so they are not subtracted"


def _left_out_notes(rows: Sequence[ItemRow]) -> list[str]:
    """Every kind of row that left the aggregate, named. Named, never folded
    into the label (C9 extended): the share is a fact beside the figure."""
    notes: list[str] = []
    no_quantity = sum(1 for r in rows if not r.costed and r.no_qty_lines)
    if no_quantity:
        notes.append(
            f"{_plural(no_quantity, 'item')} "
            f"{'has' if no_quantity == 1 else 'have'} lines with no quantity"
        )
    uncosted = sum(1 for r in rows if not r.costed and not r.no_qty_lines)
    if uncosted:
        notes.append(f"{_plural(uncosted, 'item')} cannot be costed yet")
    return notes


def _unmapped_note(count: int) -> list[str]:
    if not count:
        return []
    return [
        f"{_plural(count, 'till name')} with sales "
        f"{'is' if count == 1 else 'are'} not mapped to a menu item"
    ]


def branch_contribution(
    rows: Sequence[ItemRow],
    *,
    branch_id: str | None,
    branch_name: str | None,
    sales_quality: Quality,
    sales_notes: Sequence[str] = (),
    unmapped: Unmapped | None = None,
) -> Contribution:
    """One branch's contribution before overheads (C12.7).

    The figure is the **sum of that branch's item contributions**, so it is
    exact against the rows a reader can open, and the percentage is over the
    net item sales that produced it - never over the branch's whole net sales,
    which would silently divide by money no plate was costed against. It is
    never grossed up: it covers the costed share, and the share is a sentence
    beside it.

    `sales_quality` and `sales_notes` come from `ratio.period_row`, which
    derives them once on its way to the merged word (C9 extended); nothing
    here re-words a gap sentence. The **purchase** side of the ratio is not an
    input at all: a pending paper, a foreign-currency paper and an asserted
    total are facts about the ratio, and letting them in would label a fully
    loaded, fully costed week *incomplete* because the branch happened to take
    no delivery in it.
    """
    unmapped_here = unmapped or Unmapped(names=0, value=Decimal(0))
    counted = [r for r in rows if r.costed]

    contribution: Decimal | None = None
    cost: Decimal | None = None
    net_item_sales = sum((r.net_item_sales for r in counted), Decimal(0)).quantize(FILS)
    if counted:
        contribution = sum((r.contribution or Decimal(0) for r in counted), Decimal(0)).quantize(
            FILS
        )
        cost = sum((r.cost or Decimal(0) for r in counted), Decimal(0)).quantize(FILS)

    costed_value = sum((r.positive_value for r in counted), Decimal(0)).quantize(FILS)
    mapped_value = sum((r.positive_value for r in rows), Decimal(0))
    sales_value = (mapped_value + unmapped_here.value).quantize(FILS)
    costed_share_pct = _pct(costed_value, sales_value)

    cost_quality = (
        min((r.quality for r in counted), key=lambda q: _QUALITY_RANK[q]) if counted else None
    )
    quality = sales_quality if cost_quality is None else _worse(sales_quality, cost_quality)

    notes = list(sales_notes)
    if costed_share_pct is not None:
        subject = "this branch's" if branch_id is not None else "the chain's"
        notes.append(f"covers {_pct_words(costed_share_pct)} of {subject} sales value")
    notes.extend(_left_out_notes(rows))
    notes.extend(_unmapped_note(unmapped_here.names))

    return Contribution(
        branch_id=branch_id,
        branch_name=branch_name,
        contribution=contribution,
        contribution_pct=_pct(contribution, net_item_sales) if contribution is not None else None,
        net_item_sales=net_item_sales,
        cost=cost,
        costed_value=costed_value,
        sales_value=sales_value,
        costed_share_pct=costed_share_pct,
        quality=quality,
        notes=tuple(notes),
        sales_quality=sales_quality,
        cost_quality=cost_quality,
        items=len(counted),
        items_without_numbers=len(rows) - len(counted),
        unmapped=unmapped_here,
    )


def chain_contribution(
    rows: Sequence[Contribution], *, unmapped: Unmapped | None = None
) -> Contribution:
    """The chain figure: the sum of the branch contributions, always (C12.8).

    Its sales-side label follows `ratio.chain_total`'s rule on the sales half
    only - a branch with nothing loaded is a hole in the total the way a
    missing day is a hole in a row - and its cost side is the worst plate
    label among the branches that produced numbers.

    `unmapped` should be the chain-wide `unmapped(sales)`: a till name selling
    in two branches is one name, and summing the branch counts would count it
    twice. Summing is the fallback when a caller holds only the branch rows,
    and it is exact for the value either way.
    """
    counted = [c for c in rows if c.contribution is not None]
    contribution: Decimal | None = None
    cost: Decimal | None = None
    if counted:
        contribution = sum((c.contribution or Decimal(0) for c in counted), Decimal(0)).quantize(
            FILS
        )
        cost = sum((c.cost or Decimal(0) for c in counted), Decimal(0)).quantize(FILS)
    net_item_sales = sum((c.net_item_sales for c in counted), Decimal(0)).quantize(FILS)
    costed_value = sum((c.costed_value for c in rows), Decimal(0)).quantize(FILS)
    sales_value = sum((c.sales_value for c in rows), Decimal(0)).quantize(FILS)
    costed_share_pct = _pct(costed_value, sales_value)

    if not rows or all(c.sales_quality is Quality.UNAVAILABLE for c in rows):
        sales_quality = Quality.UNAVAILABLE
    elif any(c.sales_quality in (Quality.UNAVAILABLE, Quality.INCOMPLETE) for c in rows):
        sales_quality = Quality.INCOMPLETE
    else:
        sales_quality = min((c.sales_quality for c in rows), key=lambda q: _QUALITY_RANK[q])

    cost_qualities = [c.cost_quality for c in rows if c.cost_quality is not None]
    cost_quality = min(cost_qualities, key=lambda q: _QUALITY_RANK[q]) if cost_qualities else None
    quality = sales_quality if cost_quality is None else _worse(sales_quality, cost_quality)

    unmapped_here = unmapped or Unmapped(
        names=sum(c.unmapped.names for c in rows),
        value=sum((c.unmapped.value for c in rows), Decimal(0)).quantize(FILS),
    )
    left_out = sum(c.items_without_numbers for c in rows)

    notes: list[str] = []
    unavailable = sum(1 for c in rows if c.sales_quality is Quality.UNAVAILABLE)
    if unavailable and rows:
        notes.append(f"{unavailable} of {len(rows)} branches with nothing loaded")
    incomplete = sum(1 for c in rows if c.sales_quality is Quality.INCOMPLETE)
    if incomplete:
        notes.append(f"{incomplete} of {len(rows)} branches incomplete")
    if costed_share_pct is not None:
        notes.append(f"covers {_pct_words(costed_share_pct)} of the chain's sales value")
    if left_out:
        notes.append(f"{_plural(left_out, 'branch item', 'branch items')} left out of the figure")
    notes.extend(_unmapped_note(unmapped_here.names))
    if contribution is not None:
        notes.append(OVERHEADS_NOTE)

    return Contribution(
        branch_id=None,
        branch_name=None,
        contribution=contribution,
        contribution_pct=_pct(contribution, net_item_sales) if contribution is not None else None,
        net_item_sales=net_item_sales,
        cost=cost,
        costed_value=costed_value,
        sales_value=sales_value,
        costed_share_pct=costed_share_pct,
        quality=quality,
        notes=tuple(notes),
        sales_quality=sales_quality,
        cost_quality=cost_quality,
        items=sum(c.items for c in rows),
        items_without_numbers=left_out,
        unmapped=unmapped_here,
    )


def rank(rows: Sequence[Contribution]) -> list[Contribution]:
    """**Kept percentage, lowest first** - the branch to look at first is on
    top, the ratio's own convention - rows with no contribution last, ties by
    branch name then id.

    Deliberately not `ratio.rank`, which orders by purchases ÷ net sales
    (C12.9). The two keys disagree, and they are meant to: a branch can spend
    the least per dirham of sales and still keep the least of it, and a screen
    whose figure is contribution must rank by contribution. The answer
    sentence names the top row, so the wrong key here names the wrong branch.
    """
    return sorted(
        rows,
        key=lambda r: (
            r.contribution_pct is None,
            r.contribution_pct or Decimal(0),
            r.branch_name or "",
            r.branch_id or "",
        ),
    )
