"""M8 WP-81: purchases ÷ net sales, derived on every read and labelled by its
gaps (Docs/M8_DECOMPOSITION.md §3, C11.5-C11.8 and the C9 amendment).

Pure module: no I/O, `Decimal` only. `sales.py` feeds it the tenant's sales
days, the period's invoices and the coverage sums, and serialises what comes
back. Nothing here is stored - the ratio derives on every read, so confirming
a paper moves the branch table on the next screen load with no write to any
sales table (the WP-54 rule one layer up).

The figure is **purchases ÷ net sales, cash basis**: what the branch's
suppliers billed it (confirmed papers, the printed total less the printed
VAT, by printed date) against what its till took net of VAT, over the same
window. It is never labelled "food cost %" - purchases are what arrived, not
what was consumed, and no stock count corrects the difference (PRD §22 is
post-MVP).

Every row carries the quality of its inputs *and of its gaps* (C9 amended),
never `verified`, with precedence unavailable > incomplete > estimated >
reliable with limitations, and the sentences that made the label, so a screen
never shows a number without the reason to doubt it:

    unavailable   neither a sales day nor a counted purchase in the period
    incomplete    a day strictly inside the branch's window has no sales row;
                  or purchases and no sales (purchases shown, ratio withheld);
                  or sales and no counted purchase (net sales shown, ratio
                  withheld); or net sales not positive
    estimated     a paper still awaiting confirm or held for review sits
                  inside the window (placed by its printed date, or by the day
                  it arrived when it has none - "undated"); a confirmed paper
                  in another currency was left out; a counted paper's total or
                  VAT was typed by a person rather than read from the photo
    reliable with limitations   otherwise - a till's figures are its own word

A row's window is the period **clipped to the branch's own loaded sales
range**, and purchases are counted over that window, so two days of sales are
never set against seven days of deliveries. A branch with no sales in the
period keeps the whole period as its window, so its papers are never hidden by
a missing upload.

A confirmed paper with no branch is counted in no row and never dropped: it
sits in the unassigned group with its figure, and the chain total reconciles
the rows plus that group, so purchases cannot vanish between the papers and
the screen.
"""

import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

#: A ratio on a screen: one decimal place, "30.4".
PCT_QUANTUM = Decimal("0.1")

#: Money, to the fil.
FILS = Decimal("0.01")

#: The default period (C11.6): on a cash basis a week mostly ranks who took a
#: delivery; four weeks averages the lumpiness. Seven is the option.
DEFAULT_PERIOD_DAYS = 28

#: The longest period one read will compute (a quarter and a day).
MAX_PERIOD_DAYS = 92

#: The statuses a paper can be in and still be on its way to counting.
PENDING_STATUSES = frozenset({"awaiting_confirm", "needs_review"})


class Quality(StrEnum):
    """PRD §24's vocabulary for a period figure. `verified` is absent on
    purpose: nothing cross-checks a till's figures."""

    RELIABLE = "reliable_with_limitations"
    ESTIMATED = "estimated"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"


#: Precedence, worst first (C9 amended).
_QUALITY_RANK = {
    Quality.UNAVAILABLE: 0,
    Quality.INCOMPLETE: 1,
    Quality.ESTIMATED: 2,
    Quality.RELIABLE: 3,
}


# --- inputs -----------------------------------------------------------------


@dataclass(frozen=True)
class Period:
    start: datetime.date
    end: datetime.date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


@dataclass(frozen=True)
class SalesDay:
    """One loaded branch-day (WP-80's row, the fields the ratio reads)."""

    branch_id: str
    business_date: datetime.date
    net_sales: Decimal
    takings: Decimal
    granularity: str = "item"


@dataclass(frozen=True)
class Invoice:
    """One paper as the period read returns it. `purchased_on` is the costing
    rule - printed date, confirm date as the tie-breaker (`db.py`'s
    `coalesce`) - and `placed_on` is where a pending paper sits: its printed
    date, or the day it arrived when it printed none."""

    invoice_id: str
    branch_id: str | None
    status: str
    currency: str
    total: Decimal | None
    tax: Decimal | None
    invoice_date: datetime.date | None
    purchased_on: datetime.date | None
    placed_on: datetime.date
    supplier_name: str | None = None
    invoice_no: str | None = None
    #: Whether the total or the tax has an asserted origin (C9's read,
    #: `provenance.asserted_fields`): typed by a person, not read from a photo.
    asserted: bool = False

    @property
    def undated(self) -> bool:
        return self.invoice_date is None

    @property
    def net_purchase(self) -> Decimal:
        """C11.5: the printed total less the printed VAT - the whole paper,
        charges and discounts as billed."""
        return ((self.total or Decimal(0)) - (self.tax or Decimal(0))).quantize(FILS)


# --- outputs ----------------------------------------------------------------


@dataclass(frozen=True)
class InvoiceFigure:
    invoice_id: str
    supplier_name: str | None
    invoice_no: str | None
    purchased_on: datetime.date
    net_purchase: Decimal
    total: Decimal | None
    tax: Decimal | None
    quality: str  # reliable_with_limitations | estimated


@dataclass(frozen=True)
class PendingPaper:
    invoice_id: str
    supplier_name: str | None
    invoice_no: str | None
    status: str
    placed_on: datetime.date
    undated: bool


@dataclass(frozen=True)
class ExcludedPaper:
    invoice_id: str
    supplier_name: str | None
    invoice_no: str | None
    currency: str
    total: Decimal | None


@dataclass(frozen=True)
class DayFigure:
    business_date: datetime.date
    net_sales: Decimal | None
    granularity: str | None
    purchases: Decimal
    invoices: tuple[InvoiceFigure, ...]


@dataclass(frozen=True)
class Window:
    start: datetime.date
    end: datetime.date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


@dataclass(frozen=True)
class BranchRow:
    branch_id: str
    branch_name: str
    window: Window
    net_sales: Decimal | None
    takings: Decimal | None
    purchases: Decimal
    ratio_pct: Decimal | None
    quality: Quality
    notes: tuple[str, ...]
    days_loaded: int
    days_missing: int
    deliveries: int
    sales_through: datetime.date | None
    last_purchase_on: datetime.date | None
    days: tuple[DayFigure, ...]
    pending: tuple[PendingPaper, ...]
    excluded: tuple[ExcludedPaper, ...]


@dataclass(frozen=True)
class Unassigned:
    count: int
    purchases: Decimal
    invoices: tuple[InvoiceFigure, ...]


@dataclass(frozen=True)
class Total:
    net_sales: Decimal
    purchases: Decimal
    ratio_pct: Decimal | None
    quality: Quality
    notes: tuple[str, ...]


# --- helpers ----------------------------------------------------------------


def ratio_pct(purchases: Decimal, net_sales: Decimal | None) -> Decimal | None:
    """`purchases / net_sales`, to a tenth of a percent. Withheld - None,
    never 0% - when net sales are absent or not positive (C11.6)."""
    if net_sales is None or net_sales <= 0:
        return None
    return (purchases / net_sales * 100).quantize(PCT_QUANTUM, rounding=ROUND_HALF_UP)


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    word = singular if count == 1 else (plural or singular + "s")
    return f"{count} {word}"


def _short_date(day: datetime.date) -> str:
    return f"{day.day} {day.strftime('%b')}"


def window_words(window: Window) -> str:
    """ "25-31 Aug", or "28 Aug-3 Sep" across a month end, or "31 Aug" alone."""
    if window.start == window.end:
        return _short_date(window.start)
    if window.start.month == window.end.month and window.start.year == window.end.year:
        return f"{window.start.day}-{_short_date(window.end)}"
    return f"{_short_date(window.start)}-{_short_date(window.end)}"


def _invoice_quality(invoice: Invoice) -> str:
    return Quality.ESTIMATED.value if invoice.asserted else Quality.RELIABLE.value


def _figure(invoice: Invoice) -> InvoiceFigure:
    assert invoice.purchased_on is not None
    return InvoiceFigure(
        invoice_id=invoice.invoice_id,
        supplier_name=invoice.supplier_name,
        invoice_no=invoice.invoice_no,
        purchased_on=invoice.purchased_on,
        net_purchase=invoice.net_purchase,
        total=invoice.total,
        tax=invoice.tax,
        quality=_invoice_quality(invoice),
    )


def _within(day: datetime.date | None, window: Window) -> bool:
    return day is not None and window.start <= day <= window.end


def _currency_sentences(excluded: list[Invoice]) -> list[str]:
    by_currency: dict[str, int] = defaultdict(int)
    for invoice in excluded:
        by_currency[invoice.currency] += 1
    return [
        f"{_plural(count, 'invoice')} in {currency} not counted"
        for currency, count in sorted(by_currency.items())
    ]


def _pending_sentences(pending: list[Invoice]) -> list[str]:
    counts: dict[tuple[str, bool], int] = defaultdict(int)
    for invoice in pending:
        counts[(invoice.status, invoice.undated)] += 1
    words = {"awaiting_confirm": "awaiting confirm", "needs_review": "held for review"}
    sentences = []
    for (status, undated), count in sorted(counts.items()):
        noun = "undated invoice" if undated else "invoice"
        sentences.append(f"{_plural(count, noun)} {words.get(status, status)}")
    return sentences


# --- the branch row ---------------------------------------------------------


def period_row(
    *,
    branch_id: str,
    branch_name: str,
    days: list[SalesDay],
    invoices: list[Invoice],
    period: Period,
    tenant_currency: str,
    latest_sales_day: datetime.date | None = None,
) -> BranchRow:
    """One branch's row for the period (C11.5-C11.6, the C9 amendment).

    `days` and `invoices` may carry other branches' rows - they are filtered
    here, so the caller fetches the period once for every branch.
    `latest_sales_day` is the branch's newest loaded day ever, so a row with
    no sales in the period still says when it last had any.
    """
    own_days = sorted(
        (
            d
            for d in days
            if d.branch_id == branch_id and period.start <= d.business_date <= period.end
        ),
        key=lambda d: d.business_date,
    )
    own_invoices = [i for i in invoices if i.branch_id == branch_id]

    # The window: the period clipped to the branch's own loaded range, or the
    # whole period when the branch loaded nothing inside it.
    if own_days:
        window = Window(own_days[0].business_date, own_days[-1].business_date)
    else:
        window = Window(period.start, period.end)

    counted = sorted(
        (
            i
            for i in own_invoices
            if i.status == "confirmed"
            and i.currency == tenant_currency
            and _within(i.purchased_on, window)
        ),
        key=lambda i: (i.purchased_on, i.invoice_id),
    )
    excluded = sorted(
        (
            i
            for i in own_invoices
            if i.status == "confirmed"
            and i.currency != tenant_currency
            and _within(i.purchased_on, window)
        ),
        key=lambda i: (i.purchased_on, i.invoice_id),
    )
    pending = sorted(
        (i for i in own_invoices if i.status in PENDING_STATUSES and _within(i.placed_on, window)),
        key=lambda i: (i.placed_on, i.invoice_id),
    )

    net_sales = (
        sum((d.net_sales for d in own_days), Decimal(0)).quantize(FILS) if own_days else None
    )
    takings = sum((d.takings for d in own_days), Decimal(0)).quantize(FILS) if own_days else None
    purchases = sum((i.net_purchase for i in counted), Decimal(0)).quantize(FILS)
    loaded_dates = {d.business_date for d in own_days}
    days_missing = window.days - len(loaded_dates) if own_days else 0

    notes: list[str] = []
    quality: Quality
    if not own_days and not counted:
        quality = Quality.UNAVAILABLE
        notes.append(f"no sales loaded and no confirmed purchases {window_words(window)}")
    else:
        incomplete = False
        if days_missing > 0:
            incomplete = True
            notes.append(
                f"{days_missing} of {window.days} days "
                f"{'has' if days_missing == 1 else 'have'} no sales"
            )
        if counted and not own_days:
            incomplete = True
            notes.append(f"no sales loaded {window_words(window)}")
        if own_days and not counted:
            incomplete = True
            notes.append(f"no confirmed purchases {window_words(window)}")
        if own_days and net_sales is not None and net_sales <= 0:
            incomplete = True
            notes.append("net sales are not positive this period")
        estimated = bool(pending) or bool(excluded) or any(i.asserted for i in counted)
        if incomplete:
            quality = Quality.INCOMPLETE
        elif estimated:
            quality = Quality.ESTIMATED
        else:
            quality = Quality.RELIABLE
    notes.extend(_pending_sentences(pending))
    notes.extend(_currency_sentences(excluded))
    asserted_count = sum(1 for i in counted if i.asserted)
    if asserted_count:
        notes.append(f"{_plural(asserted_count, 'invoice')} with a total or VAT entered by hand")
    if counted:
        notes.append(f"{_plural(len(counted), 'delivery', 'deliveries')} in this window")

    ratio = ratio_pct(purchases, net_sales) if own_days and counted else None

    # The per-day breakdown: every loaded day, plus any date a counted paper
    # sits on with no sales row (its figure shown, its net absent).
    by_date: dict[datetime.date, list[Invoice]] = defaultdict(list)
    for invoice in counted:
        by_date[invoice.purchased_on].append(invoice)  # type: ignore[index]
    day_by_date = {d.business_date: d for d in own_days}
    figures: list[DayFigure] = []
    for date in sorted(set(day_by_date) | set(by_date)):
        day = day_by_date.get(date)
        papers = by_date.get(date, [])
        figures.append(
            DayFigure(
                business_date=date,
                net_sales=day.net_sales if day else None,
                granularity=day.granularity if day else None,
                purchases=sum((i.net_purchase for i in papers), Decimal(0)).quantize(FILS),
                invoices=tuple(_figure(i) for i in papers),
            )
        )

    sales_through = own_days[-1].business_date if own_days else latest_sales_day
    return BranchRow(
        branch_id=branch_id,
        branch_name=branch_name,
        window=window,
        net_sales=net_sales,
        takings=takings,
        purchases=purchases,
        ratio_pct=ratio,
        quality=quality,
        notes=tuple(notes),
        days_loaded=len(loaded_dates),
        days_missing=days_missing,
        deliveries=len(counted),
        sales_through=sales_through,
        last_purchase_on=counted[-1].purchased_on if counted else None,
        days=tuple(figures),
        pending=tuple(
            PendingPaper(
                invoice_id=i.invoice_id,
                supplier_name=i.supplier_name,
                invoice_no=i.invoice_no,
                status=i.status,
                placed_on=i.placed_on,
                undated=i.undated,
            )
            for i in pending
        ),
        excluded=tuple(
            ExcludedPaper(
                invoice_id=i.invoice_id,
                supplier_name=i.supplier_name,
                invoice_no=i.invoice_no,
                currency=i.currency,
                total=i.total,
            )
            for i in excluded
        ),
    )


def unassigned_group(invoices: list[Invoice], period: Period, tenant_currency: str) -> Unassigned:
    """Confirmed papers with no branch, inside the period, in the tenant's
    currency: counted in no row, never dropped (review finding 1)."""
    window = Window(period.start, period.end)
    papers = sorted(
        (
            i
            for i in invoices
            if i.branch_id is None
            and i.status == "confirmed"
            and i.currency == tenant_currency
            and _within(i.purchased_on, window)
        ),
        key=lambda i: (i.purchased_on, i.invoice_id),
    )
    return Unassigned(
        count=len(papers),
        purchases=sum((i.net_purchase for i in papers), Decimal(0)).quantize(FILS),
        invoices=tuple(_figure(i) for i in papers),
    )


def rank(rows: list[BranchRow]) -> list[BranchRow]:
    """Highest ratio first - the branch to look at first is on top - unrated
    rows last, ties by branch name."""
    return sorted(
        rows,
        key=lambda r: (
            r.ratio_pct is None,
            -(r.ratio_pct or Decimal(0)),
            r.branch_name,
            r.branch_id,
        ),
    )


def chain_total(rows: list[BranchRow], unassigned: Unassigned) -> Total:
    """The row that reconciles the table: every branch row plus the
    unassigned group. A test pins that it equals the sum of the rows."""
    net_sales = sum((r.net_sales or Decimal(0) for r in rows), Decimal(0)).quantize(FILS)
    purchases = (sum((r.purchases for r in rows), Decimal(0)) + unassigned.purchases).quantize(FILS)
    with_sales = [r for r in rows if r.net_sales is not None]
    ratio = ratio_pct(purchases, net_sales) if with_sales else None
    # The chain figure's own gaps: a branch with nothing loaded is a hole in
    # the total the way a missing day is a hole in a row, so one such branch
    # among others makes the total incomplete, never merely "unavailable".
    if not rows or all(r.quality is Quality.UNAVAILABLE for r in rows):
        quality = Quality.UNAVAILABLE
    elif any(r.quality in (Quality.UNAVAILABLE, Quality.INCOMPLETE) for r in rows):
        quality = Quality.INCOMPLETE
    else:
        quality = min((r.quality for r in rows), key=lambda q: _QUALITY_RANK[q])
    notes: list[str] = []
    unavailable = sum(1 for r in rows if r.quality is Quality.UNAVAILABLE)
    if unavailable and rows:
        notes.append(f"{unavailable} of {len(rows)} branches with nothing loaded")
    incomplete = sum(1 for r in rows if r.quality is Quality.INCOMPLETE)
    if incomplete:
        notes.append(f"{incomplete} of {len(rows)} branches incomplete")
    if unassigned.count:
        notes.append(f"{_plural(unassigned.count, 'invoice')} on no branch, counted in the total")
    if with_sales and net_sales <= 0:
        notes.append("net sales are not positive this period")
    return Total(
        net_sales=net_sales,
        purchases=purchases,
        ratio_pct=ratio,
        quality=quality,
        notes=tuple(notes),
    )


# --- coverage by sales value ------------------------------------------------


@dataclass(frozen=True)
class TillItemValue:
    """One till item's value in the period, summed in SQL (never over lines
    in Python): the positive net value and the refund value apart."""

    till_item_id: str
    name: str
    code: str | None
    menu_item_id: str | None
    excluded: bool
    positive_value: Decimal
    refund_value: Decimal


@dataclass(frozen=True)
class MenuPlate:
    menu_item_id: str
    name: str
    plate_quality: str  # plates.PlateQuality value
    archived: bool = False


@dataclass(frozen=True)
class CoverageItem:
    till_item_id: str
    name: str
    code: str | None
    value: Decimal
    menu_item_id: str | None = None
    menu_item_name: str | None = None
    plate_quality: str | None = None


@dataclass(frozen=True)
class Coverage:
    sales_value: Decimal
    costed_value: Decimal
    costed_pct: Decimal | None
    estimated_points: Decimal | None
    uncosted_incomplete_plate: Decimal
    uncosted_unmapped: Decimal
    refunds: Decimal
    not_menu_items: Decimal
    queue: tuple[CoverageItem, ...] = field(default_factory=tuple)
    mapped: tuple[CoverageItem, ...] = field(default_factory=tuple)
    excluded: tuple[CoverageItem, ...] = field(default_factory=tuple)


def coverage(values: list[TillItemValue], plates: dict[str, MenuPlate]) -> Coverage:
    """C11.8: the positive net value of lines whose till item maps to a menu
    item whose plate is not incomplete, over the positive net value of lines
    not marked "not a menu item". Refunds count in net sales and not here;
    a delivery charge is takings but not menu sales; so the figure is bounded
    0-100% and can reach it. The word is *costed*, never *complete*: an
    estimated plate counts as costed and is named as estimated."""
    sales_value = Decimal(0)
    costed_value = Decimal(0)
    estimated_value = Decimal(0)
    incomplete_value = Decimal(0)
    unmapped_value = Decimal(0)
    refunds = Decimal(0)
    not_menu = Decimal(0)
    queue: list[CoverageItem] = []
    mapped: list[CoverageItem] = []
    excluded: list[CoverageItem] = []

    for item in values:
        refunds += item.refund_value
        if item.excluded:
            not_menu += item.positive_value
            excluded.append(
                CoverageItem(item.till_item_id, item.name, item.code, item.positive_value)
            )
            continue
        sales_value += item.positive_value
        plate = plates.get(item.menu_item_id or "")
        if plate is None:
            unmapped_value += item.positive_value
            queue.append(CoverageItem(item.till_item_id, item.name, item.code, item.positive_value))
            continue
        mapped.append(
            CoverageItem(
                item.till_item_id,
                item.name,
                item.code,
                item.positive_value,
                menu_item_id=plate.menu_item_id,
                menu_item_name=plate.name,
                plate_quality=plate.plate_quality,
            )
        )
        if plate.plate_quality == "incomplete":
            incomplete_value += item.positive_value
        else:
            costed_value += item.positive_value
            if plate.plate_quality == "estimated":
                estimated_value += item.positive_value

    def pct(part: Decimal) -> Decimal | None:
        if sales_value <= 0:
            return None
        return (part / sales_value * 100).quantize(PCT_QUANTUM, rounding=ROUND_HALF_UP)

    queue.sort(key=lambda c: (-c.value, c.name, c.till_item_id))
    mapped.sort(key=lambda c: (-c.value, c.name, c.till_item_id))
    excluded.sort(key=lambda c: (-c.value, c.name, c.till_item_id))
    return Coverage(
        sales_value=sales_value.quantize(FILS),
        costed_value=costed_value.quantize(FILS),
        costed_pct=pct(costed_value),
        estimated_points=pct(estimated_value),
        uncosted_incomplete_plate=incomplete_value.quantize(FILS),
        uncosted_unmapped=unmapped_value.quantize(FILS),
        refunds=refunds.quantize(FILS),
        not_menu_items=not_menu.quantize(FILS),
        queue=tuple(queue),
        mapped=tuple(mapped),
        excluded=tuple(excluded),
    )
