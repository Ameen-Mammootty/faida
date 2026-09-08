"""M12 WP-120: what the period's sales needed of each material, against what
was bought (C14; Docs/M12_DECOMPOSITION.md §3, plan.md §7.2, §8 M12).

M6 costs a plate. M8 says how many plates each branch sold. M9 multiplied the
two into money. This module multiplies the same two into **quantities** and
asks the question one shelf down: the branch sold 1,400 karaks, so its recipes
needed 7.7 kg of tea dust; the confirmed papers say it bought 12 kg; what is
the difference, and what would it cost at the period's price.

**What the difference is not, said first, because every reader will ask.**
Bought minus used is not stock lost and it is not stock on hand. The
difference is on the shelf, in the bin, or unrecorded, and no count says
which - Faida asks no cafeteria to count anything. So the figure is a
*recorded difference*, `STANDING_SENTENCE` says what it can be, and a test
calls this module and pins that none of the words a reader would take as an
accusation appears in any sentence it can compose.

Pure module: no I/O, no database, `Decimal` everywhere, every sentence
composed here and none composed anywhere else (C14.6 - the screen shows the
words and divides nothing). One implementation (C14.11): the pack factor is
`costing.resolve_pack`'s, the unit conversion is `plates.to_base_qty`'s, the
portions are `contribution.item_rows`', the windows and the sales half of
every label are `ratio.period_row`'s, the display unit is
`costing.DISPLAY_UNITS`. A second copy of any of those is a contract breach.

Where the rounding happens (C14.1, D5), which is the whole of why every
invariant here is an exact equality rather than a tolerance:

    a dish's base quantity   portions x per-portion base quantity,
                             quantized ONCE to 0.001 base units
    a line's base quantity   line qty x the pack factor, quantized ONCE
    used, bought, the gap    exact sums and differences of those
    the chain's figures      exact sums of the branch figures they name
    money                    the gap x the as-of price, quantized once to a fil

`per_portion_base` travels at full precision (a yield of three makes it
non-terminating), so the drill's parts add up to the row to the digit.

The three holes, and why each is a hole and not a zero:

    used is null      a (branch, dish) pair whose till lines printed no
                      quantity, or a component whose unit does not convert -
                      for **every** material that dish's recipe names, because
                      a smaller used figure reads as a larger difference. The
                      partial sum is exposed as `used_measured`, never as
                      `used` (C14.2).
    bought is null    a line no pack resolver can read, or a material with no
                      supplier product mapped at all. `bought_measured`
                      carries the rest (C14.3, C14.8).
    both are null     a branch with purchases and no sales loaded keeps
                      purchase-only rows: `bought` present, the used side
                      null, the word `unavailable` (D12).

A branch that loaded sales and took no delivery inside its window bought
**zero**, which is a fact and not a hole: the row reads `under` by everything
its recipes needed and its purchase half says so.
"""

import datetime
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from . import contribution, costing, plates

# The words come from the shipped modules rather than being written again
# (C14.11): "25-31 Aug", "3 deliveries", "per kg" and the four quality words
# are composed in one place each, so `/sales`, the dashboard and this module
# can never say the same thing two ways.
from .contribution import (
    _long_date,
    _money_words,
    _names_words,
    _price_words,
    _qty_words,
)
from .ratio import (
    _QUALITY_RANK,
    FILS,
    PendingPaper,
    Quality,
    Window,
    _pending_sentences,
    _plural,
    window_words,
)
from .signals import _per_unit_words

#: A dish's and a line's base quantity round here, once, and nothing above
#: them rounds at all (C14.1, D5). Three decimals of a gram is far below the
#: precision of anything on a paper or a till roll; it exists so a repeating
#: division by a batch yield cannot make a row disagree with its own drill.
BASE_QUANTUM = Decimal("0.001")

#: Portions, as the till prints them (`sales_lines.qty` is numeric(12,3)).
QTY_QUANTUM = contribution.QTY_QUANTUM

#: One decimal in the unit a person says (C14.6): "5.7 kg", "27.5 L".
WORDS_QUANTUM = Decimal("0.1")

#: The sentence that stands beneath the panel, composed once, in Python, and
#: carried on the wire (C14.5). It is the whole honesty of the milestone: the
#: difference is a record, not a location, and nothing here counted anything.
STANDING_SENTENCE = (
    "The difference between bought and what the recipes needed is on the shelf, "
    "in the bin or unrecorded; no count says which."
)

#: The two things an `under` gap can mean, and there is no third (C14.5).
UNDER_CAUSES = (
    "either stock from before this window was used, or a recipe quantity or a pack size is wrong"
)

#: The unit a person says a quantity in, per base unit: the small one below
#: the boundary and the large one above it (C14.6). Money's display unit is
#: `costing.DISPLAY_UNITS` and is a different question - nobody buys a gram,
#: but 97 grams of cardamom is exactly how much cardamom that is.
_SCALE: dict[str, tuple[str, str, Decimal]] = {
    "g": ("g", "kg", Decimal("1000")),
    "ml": ("ml", "L", Decimal("1000")),
}

#: Directions, in the words the row uses.
OVER = "over"
UNDER = "under"
EVEN = "even"

#: Where a line's pack factor came from (C14.3, D2): the factor frozen on the
#: line when it was costed, or the resolver reading its printed cells now.
FROZEN = "frozen"
RESOLVED = "resolved"


def _worse(first: Quality, second: Quality) -> Quality:
    return first if _QUALITY_RANK[first] <= _QUALITY_RANK[second] else second


# --- inputs -----------------------------------------------------------------


@dataclass(frozen=True)
class PurchaseLine:
    """One confirmed stock line, exactly the columns
    `db.list_period_material_purchases` returns (C14.4).

    Three of the fields are nullable for three different reasons, and each
    sends the line somewhere different:

        supplier_item_id   the line reached no catalog product at all, which
                           the confirm path creates for neither a foreign
                           paper nor a line with no price (D3). An *orphan*:
                           counted, its paper named, in no row and no queue.
        ingredient_id      the line's product exists and nobody has approved a
                           material for it yet. An *unmapped pack*: its spend
                           reported beside the panel, in no row (D6, D21).
        branch_id          the paper named no branch. *Unassigned*: listed per
                           material, outside every row and every chain figure,
                           because it lies in the whole period while a branch
                           row lies in that branch's clipped window (C14.9).

    `frozen_factor` is `cost_basis.pack_base_quantity` - the amount one unit
    price bought, in base units, written when the line was costed. It is the
    fact; `costing.resolve_pack` over the printed cells is the fallback for
    the lines that were never costed (D2).
    """

    invoice_id: str
    invoice_no: str | None
    line_position: int
    branch_id: str | None
    purchased_on: datetime.date
    supplier_name: str | None
    raw_name: str
    #: The printed quantity, signed - a return prints a negative. Null where
    #: the camera read no quantity cell: the line delivered an unknown amount,
    #: so it is unmeasured with its own reason rather than counted as zero.
    qty: Decimal | None
    unit: str | None
    pack_size: str | None
    unit_price: Decimal | None
    line_total: Decimal | None
    currency: str
    frozen_factor: Decimal | None = None
    supplier_item_id: str | None = None
    ingredient_id: str | None = None
    pack_size_override: str | None = None
    canonical_name: str | None = None


@dataclass(frozen=True)
class MaterialPrice:
    """The price a material's gap is valued at: what `menu._menu_context`
    holds for the ingredient, costed as of the **period's end** for every
    branch (C14.7, C12.4's rule).

    That is a stated limit, not an oversight: a delivery dated between a
    branch's window end and the period's end reprices that branch's gap, and
    the row's own words name the date it was priced on so a reader can see it.
    """

    ingredient_id: str
    cost_per_base_unit: Decimal
    cost_base_unit: str
    priced_on: datetime.date | None = None
    quality: str | None = None
    invoice_id: str | None = None
    line_position: int | None = None


@dataclass(frozen=True)
class Material:
    """A material as this module needs it: its name, the unit it is measured
    in, and whether any supplier product is mapped to it at all.

    `db.list_current_recipe_components` carries all three per component, but
    `contribution.RecipeComponent` keeps only the name, so the caller lifts
    them out. `has_packs` false is the one case where a row has a used figure
    and **no bought figure at all** - not a zero, because nothing was ever
    pointed at this material for a purchase to land on (C14.8).
    """

    ingredient_id: str
    name: str
    base_unit: str
    has_packs: bool = True


@dataclass(frozen=True)
class BranchWindow:
    """What `ratio.BranchRow` already carries, lifted out so this module stays
    pure (P6, C14.8): the branch's clipped window, whether it loaded any sales
    at all, the papers still pending inside the window, and the **sales half**
    of its label with the sentences that made it - read and never re-worded.

    The ratio's *purchase* half is deliberately not here. It is about money -
    it excludes a paper billed in another currency and goes estimated on a
    typed total - and neither says anything about how many sacks arrived, so
    the purchase half of a material row is derived here, about quantities,
    from the window, the pending papers and this module's own read.
    """

    branch_id: str
    name: str
    window_from: datetime.date | None = None
    window_to: datetime.date | None = None
    sales_loaded: bool = False
    pending: tuple[PendingPaper, ...] = ()
    sales_quality: str = Quality.RELIABLE.value
    sales_notes: tuple[str, ...] = ()

    def window(self, date_from: datetime.date, date_to: datetime.date) -> Window:
        """The branch's clipped window, or the whole period when it loaded
        nothing - `ratio.period_row`'s own fallback."""
        return Window(self.window_from or date_from, self.window_to or date_to)


# --- outputs ----------------------------------------------------------------


@dataclass(frozen=True)
class LineEntry:
    """One purchase line in a row's drill, with the factor that measured it
    and where the factor came from, so `/invoices/<id>#line-<n>` reaches the
    paper and a reader can check the multiplication."""

    invoice_id: str
    invoice_no: str | None
    line_position: int
    purchased_on: datetime.date
    supplier_name: str | None
    product_name: str
    qty: Decimal | None
    pack: str | None
    pack_source: str | None
    factor: Decimal | None
    factor_source: str | None
    base_qty: Decimal | None
    base_words: str | None
    measured: bool
    currency: str
    blocked: str | None = None


@dataclass(frozen=True)
class DishEntry:
    """One dish that needed this material, in one branch (D18: its recipe is
    on `/menu#item-<id>` and its portions on `/sales#branch-<id>`).

    A recipe may draw one material twice - the real menu's lemon is 7 g in the
    marinade and 20 g as the wedge - and both draws are summed into **one**
    entry with the combined per-portion quantity, because it is one line on
    the shelf (C14.2).
    """

    menu_item_id: str
    menu_item_name: str
    branch_id: str
    portions: Decimal
    per_portion_base: Decimal
    usable_share: Decimal | None
    base_qty: Decimal


@dataclass(frozen=True)
class MaterialRow:
    """One (material, branch, period), or one (material, chain, period) when
    `branch_id` is None (C14.1, §3.1's wire shape).

    A hole never renders as a shelf that is exactly right: a null figure
    carries no number, the partial sum sits in `*_measured`, and the reason is
    a sentence in `notes`. `used_hole` and `bought_hole` are the short form of
    that reason, kept so the chain row can name the branch it left out and why
    without re-wording anything (C14.9).
    """

    ingredient_id: str
    ingredient_name: str
    base_unit: str
    branch_id: str | None
    window: Window
    used_base: Decimal | None
    bought_base: Decimal | None
    gap_base: Decimal | None
    used_measured: Decimal | None
    bought_measured: Decimal | None
    used_words: str | None
    bought_words: str | None
    gap_words: str | None
    used_measured_words: str | None
    bought_measured_words: str | None
    direction: str | None
    money: Decimal | None
    price_per_display_unit: Decimal | None
    display_unit: str | None
    priced_on: datetime.date | None
    price_quality: str | None
    purchases: int
    purchase_dates: int
    returns: int
    foreign_papers: int
    unmeasured_lines: int
    dishes_counted: int
    refunded_portions: Decimal | None
    recipe_after_period: bool
    quality: Quality
    notes: tuple[str, ...]
    lines: tuple[LineEntry, ...] = ()
    dishes: tuple[DishEntry, ...] = ()
    used_hole: str | None = None
    bought_hole: str | None = None


@dataclass(frozen=True)
class UnusedMaterial:
    """A material with purchases and no sold recipe naming it: gloves,
    cleaning fluid, a cup nobody has put in a recipe yet. Listed apart and out
    of the ranking, because there is nothing to compare it against (D11)."""

    ingredient_id: str
    ingredient_name: str
    base_unit: str
    branch_id: str | None
    bought_base: Decimal
    bought_words: str
    money: Decimal | None
    purchases: int
    sentence: str


@dataclass(frozen=True)
class UnmappedPacks:
    """Confirmed purchase lines on a product nobody has approved a material
    for. Never dropped, or mapped purchases would present as the whole of what
    was bought (D6, D21). The spend is the **printed line totals** in the
    tenant's currency; a foreign line is counted and named, never converted.
    """

    lines: int
    packs: int
    spend: Decimal
    foreign_lines: int
    sentence: str | None


@dataclass(frozen=True)
class OrphanPaper:
    invoice_id: str
    invoice_no: str | None
    supplier_name: str | None
    currency: str
    lines: int


@dataclass(frozen=True)
class Orphans:
    """Confirmed lines that reached no catalog product, so no material and no
    row (D3). The confirm door creates no product for a paper billed in
    another currency and none for a line with no price, so these are the lines
    those two rules leave behind. Named again on the coverage line (D20), so
    the rows above admit an unplaced purchase."""

    lines: int
    foreign: int
    no_price: int
    unmatched: int
    papers: tuple[OrphanPaper, ...]
    sentence: str | None


@dataclass(frozen=True)
class UnassignedRow:
    """A material bought on a paper with no branch. In no row and in no chain
    figure - a branch row lies in that branch's clipped window and these lie
    in the whole period, so a sum would add two spans (C14.9)."""

    ingredient_id: str
    ingredient_name: str
    base_unit: str
    bought_base: Decimal
    bought_words: str
    papers: int
    lines: tuple[LineEntry, ...]


@dataclass(frozen=True)
class Coverage:
    """*Recipes cover N%* - a third share with its own noun, and never on one
    row with the other two (P4).

    `ratio.coverage` asks what the menu can cost today and
    `contribution.costed_share_pct` what could be costed at the period's
    prices. Usage needs a recipe's **quantities** and not its price: the
    seeded Paratha's 2 kg of flour is real usage of a material nobody has
    bought yet, and a costed share would throw away exactly the row that sends
    a consultant to the mapping queue.
    """

    recipes_pct: Decimal | None
    covered_value: Decimal
    sales_value: Decimal
    dishes_without_recipe: int
    unmapped_names: int
    sentence: str


@dataclass(frozen=True)
class LeftOut:
    """What the panel could not count, in four numbers (§3.1)."""

    items_without_quantity: int
    items_without_recipe: int
    unmeasured_lines: int
    branches_without_sales: int


# --- words ------------------------------------------------------------------


def _trim(value: Decimal) -> str:
    """ "5.7", "100", "1,200" - thousands separated, and a trailing zero after
    the point dropped, because "100.0 kg" of sugar is a decimal place nobody
    asked for."""
    if value == value.to_integral_value():
        return f"{value.to_integral_value():,}"
    return f"{value:,}"


def quantity_words(base_qty: Decimal, base_unit: str) -> str:
    """A quantity in the unit a person says it in (C14.6).

    Grams under a kilo and kilos above; millilitres under a litre and litres
    above; pieces. One decimal above the small unit and none below, because
    "5.708 kg" of sugar claims a precision the pack size behind it cannot
    support, and "5,708 g" is not how anyone talks about a sack.

    The API composes this and the screen shows it: `format.quantity` on the
    web does string operations only and could not turn 0.097 kilos into 97 g
    without doing arithmetic, which is the rule this exists to keep.
    """
    if base_unit == "pc":
        rounded = base_qty.quantize(WORDS_QUANTUM, rounding=ROUND_HALF_UP)
        word = "piece" if abs(rounded) == 1 else "pieces"
        return f"{_trim(rounded)} {word}"
    scale = _SCALE.get(base_unit)
    if scale is None:
        return f"{_trim(base_qty.quantize(WORDS_QUANTUM, rounding=ROUND_HALF_UP))} {base_unit}"
    small, large, factor = scale
    whole = base_qty.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if abs(base_qty) >= factor or abs(whole) >= factor:
        big = (base_qty / factor).quantize(WORDS_QUANTUM, rounding=ROUND_HALF_UP)
        return f"{_trim(big)} {large}"
    return f"{whole:,} {small}"


def _direction_of(gap: Decimal) -> str:
    if gap > 0:
        return OVER
    if gap < 0:
        return UNDER
    return EVEN


def _gap_words(gap: Decimal, base_unit: str) -> str:
    """The cell beside the figure: "94.3 kg more bought", "3.2 kg more
    needed", "no difference"."""
    if gap > 0:
        return f"{quantity_words(gap, base_unit)} more bought"
    if gap < 0:
        return f"{quantity_words(-gap, base_unit)} more needed"
    return "no difference"


def _direction_sentence(gap: Decimal, base_unit: str) -> str:
    """Both ways, and an `under` gap says the two things it can mean and
    stops (C14.5). It is never worded as anything that locates money."""
    if gap > 0:
        return f"bought {quantity_words(gap, base_unit)} more than its sales needed"
    if gap < 0:
        return (
            f"its sales needed {quantity_words(-gap, base_unit)} more than was bought"
            f" - {UNDER_CAUSES}"
        )
    return "bought exactly what its sales needed"


def _price_sentence(
    price: MaterialPrice, *, estimated: bool, currency: str
) -> tuple[str, Decimal, str]:
    """ "at AED 2.30 per kg on 7 Aug 2026", and "at an estimated AED 2.30 per
    kg on 7 Aug 2026" when the price is estimated or the material's newest
    purchase could not be costed (C14.7, D17). The date is always named: it is
    the period's end for every branch, which is a stated limit."""
    per_display, display_unit = costing.per_display_unit(
        price.cost_per_base_unit, price.cost_base_unit
    )
    words = _price_words(per_display, currency)
    lead = "at an estimated" if estimated else "at"
    sentence = f"{lead} {words} {_per_unit_words(display_unit)}"
    if price.priced_on is not None:
        sentence = f"{sentence} on {_long_date(price.priced_on)}"
    return sentence, per_display, display_unit


def _recipe_sentence(versions: set[int | None]) -> str:
    """ "at the current recipe (version 1), at its purchased quantities"
    (C14.2). The quantities are what leaves the storeroom: a component with a
    usable share has already been divided by it, so cost and quantity describe
    the same purchased amount (D13)."""
    known = sorted(v for v in versions if v is not None)
    if len(versions) == 1 and len(known) == 1:
        return f"at the current recipe (version {known[0]}), at its purchased quantities"
    return "at the current recipes, at their purchased quantities"


# --- measuring a line (C14.3, D2) -------------------------------------------


@dataclass(frozen=True)
class _Measured:
    line: PurchaseLine
    base_qty: Decimal | None
    factor: Decimal | None
    factor_source: str | None
    pack: costing.Pack | None
    blocked: costing.Blocked | None

    @property
    def measured(self) -> bool:
        return self.base_qty is not None

    @property
    def overridden(self) -> bool:
        return self.pack is not None and self.pack.source is costing.PackSource.OVERRIDE


def measure(line: PurchaseLine) -> _Measured:
    """How much this line delivered, in base units.

    The frozen `cost_basis.pack_base_quantity` where the line has one, and
    `costing.resolve_pack` over its own printed cells and its pack's override
    where it has none (D2). The stored factor is the fact this product never
    rewrites; the reader is the fallback for the uncosted minority - a line on
    a paper billed in USD, or one whose camera missed the price, both of which
    the costing door returns before, and both of which delivered goods.

    The resolver runs either way, because the printed pack and where it was
    read are what the drill shows. On a costed line the two agree by
    construction, and a test pins that as a drift alarm; where they disagree
    the frozen one wins, and the row's quantity and its cost keep one factor
    for the life of the line.

    None means nothing on this line reads as an amount - `blocked_reason`'s
    three pack blockers and nothing else, independent of price and currency.
    """
    pack = costing.resolve_pack(
        pack_size=line.pack_size,
        raw_name=line.raw_name,
        unit=line.unit,
        override=line.pack_size_override,
    )
    if line.frozen_factor is not None:
        factor, source = line.frozen_factor, FROZEN
    elif pack is not None:
        factor, source = pack.base_quantity, RESOLVED
    else:
        return _Measured(
            line=line,
            base_qty=None,
            factor=None,
            factor_source=None,
            pack=None,
            blocked=costing.blocked_reason(pack_size=line.pack_size, unit=line.unit),
        )
    if line.qty is None:
        # The pack reads and the quantity does not, which is a different hole
        # from an unreadable pack and has its own shipped sentence. The line
        # is unmeasured; nothing is counted as zero, because a line whose
        # quantity nobody read is not a delivery of nothing. The confirm door
        # creates no catalog product for such a line, so it is normally an
        # orphan - but it is measured here before it is placed, and one that
        # extraction snapped to a known product must not crash the read.
        return _Measured(
            line=line,
            base_qty=None,
            factor=factor,
            factor_source=source,
            pack=pack,
            blocked=costing.Blocked.MISSING_QUANTITY,
        )
    return _Measured(
        line=line,
        base_qty=(line.qty * factor).quantize(BASE_QUANTUM, rounding=ROUND_HALF_UP),
        factor=factor,
        factor_source=source,
        pack=pack,
        blocked=None,
    )


def _entry(measured: _Measured, base_unit: str) -> LineEntry:
    line = measured.line
    return LineEntry(
        invoice_id=line.invoice_id,
        invoice_no=line.invoice_no,
        line_position=line.line_position,
        purchased_on=line.purchased_on,
        supplier_name=line.supplier_name,
        product_name=line.raw_name,
        qty=line.qty,
        pack=measured.pack.printed if measured.pack else None,
        pack_source=measured.pack.source.value if measured.pack else None,
        factor=measured.factor,
        factor_source=measured.factor_source,
        base_qty=measured.base_qty,
        base_words=(
            None if measured.base_qty is None else quantity_words(measured.base_qty, base_unit)
        ),
        measured=measured.measured,
        currency=line.currency,
        blocked=measured.blocked.value if measured.blocked else None,
    )


# --- placing a line (C14.3, C14.9, D3, D6) ----------------------------------

ORPHAN = "orphan"
UNMAPPED = "unmapped"
UNASSIGNED = "unassigned"
PLACED = "placed"


@dataclass(frozen=True)
class _Placed:
    measured: _Measured
    bucket: str

    @property
    def line(self) -> PurchaseLine:
        return self.measured.line


def _place(lines: Iterable[PurchaseLine]) -> list[_Placed]:
    """Where every line goes, in one pass and in one order, so no figure on
    the panel can count a line twice or drop one.

    A line with no catalog product is an orphan before anything else is asked
    of it - it reached no material by any route (D3). Then a product with no
    material is an unmapped pack, wherever it was delivered. Then a paper with
    no branch is unassigned. What is left is a branch's purchase of a material.
    """
    out: list[_Placed] = []
    for line in lines:
        measured = measure(line)
        if line.supplier_item_id is None:
            bucket = ORPHAN
        elif line.ingredient_id is None:
            bucket = UNMAPPED
        elif line.branch_id is None:
            bucket = UNASSIGNED
        else:
            bucket = PLACED
        out.append(_Placed(measured=measured, bucket=bucket))
    return out


# --- the used side (C14.2) --------------------------------------------------


@dataclass
class _Draw:
    """One material's draw on one dish, before the dish is counted."""

    per_portion_base: Decimal = Decimal(0)
    shares: set[Decimal | None] = field(default_factory=set)


def _material_for(
    ingredient_id: str,
    name: str,
    base_unit: str | None,
    materials: Mapping[str, Material],
) -> Material:
    """The material, or a stand-in built from the component when the caller's
    map does not hold it - a remap between two reads, never the normal path.
    A stand-in has no packs, so its row says so rather than reading zero."""
    known = materials.get(ingredient_id)
    if known is not None:
        return known
    return Material(
        ingredient_id=ingredient_id,
        name=name,
        base_unit=base_unit or "",
        has_packs=False,
    )


def _no_convert_sentence(*, position: int, qty: Decimal, unit: str, material: Material) -> str:
    """`plates.cost_component`'s own sentence for a component whose unit does
    not convert to how its material is measured, taken from the shipped
    function rather than written again (C14.2, C14.11). The probe price is a
    stand-in; only the sentence is used."""
    probe = plates.cost_component(
        position=position,
        qty=qty,
        unit=unit,
        ingredient_name=material.name,
        has_packs=True,
        price=plates.Priced(
            cost_per_base_unit=Decimal(1),
            base_unit=material.base_unit,
            quality=None,
        ),
    )
    return probe.missing or f"'{unit}' does not convert to how {material.name} is measured"


def _no_pack_sentence(material: Material) -> str:
    """ "no supplier product is mapped to Atta Flour yet" - `plates`' sentence,
    which names the next action and not the failure."""
    probe = plates.cost_component(
        position=0,
        qty=Decimal(1),
        unit=material.base_unit or "g",
        ingredient_name=material.name,
        has_packs=False,
        price=None,
    )
    return probe.missing or f"no supplier product is mapped to {material.name} yet"


@dataclass
class _UsedSide:
    dishes: dict[str, DishEntry] = field(default_factory=dict)
    total: Decimal = Decimal(0)
    hole: str | None = None
    hole_note: str | None = None
    refunded: Decimal = Decimal(0)
    versions: set[int | None] = field(default_factory=set)
    after_period: bool = False


def _used_by_material(
    rows: Sequence[contribution.ItemRow],
    menu: Mapping[str, contribution.MenuItem],
    materials: Mapping[str, Material],
    *,
    branch_id: str,
    date_to: datetime.date,
) -> dict[str, _UsedSide]:
    """Every material one branch's sold recipes needed, per material.

    used += portions x `plates.to_base_qty(component.qty, component.unit)` /
    usable share / yield portions, the dish's total quantized once (D5).
    Portions are as the till printed them, before refunds, with the refunded
    portions named on the row: a refunded karak was usually made and poured
    away, and neither answer is knowable from a till line (P9).

    A known hole names the material and makes its figure null for this
    branch - a pair whose lines printed no quantity, or a component whose unit
    does not convert - because a partial sum presented as the whole would read
    as a larger difference than there is (C14.2).
    """
    out: dict[str, _UsedSide] = {}
    for row in rows:
        item = menu.get(row.menu_item_id)
        if item is None or not item.components:
            continue
        draws: dict[str, _Draw] = {}
        holes: dict[str, str] = {}
        for position, component in enumerate(item.components):
            material = _material_for(
                component.ingredient_id, component.ingredient_name, None, materials
            )
            side = out.setdefault(material.ingredient_id, _UsedSide())
            converted = plates.to_base_qty(component.qty, component.unit)
            if converted is None or converted[1] != material.base_unit:
                holes[material.ingredient_id] = _no_convert_sentence(
                    position=position,
                    qty=component.qty,
                    unit=component.unit,
                    material=material,
                )
                continue
            base_qty, _ = converted
            share = component.usable_share
            if share is not None:
                base_qty = base_qty / share
            draw = draws.setdefault(material.ingredient_id, _Draw())
            draw.per_portion_base += base_qty / item.yield_portions
            draw.shares.add(share)

        for ingredient_id, sentence in holes.items():
            side = out[ingredient_id]
            if side.hole is None:
                side.hole = sentence
                side.hole_note = sentence

        if row.qty_sold is None:
            # C12.6 one shelf down: a pair that cannot be counted does not
            # merely leave an aggregate, it makes every material this dish's
            # recipe names unsummable for this branch.
            note = (
                f"{row.menu_item_name} has lines with no quantity, "
                "so what the recipes needed cannot be summed"
            )
            for ingredient_id in draws:
                side = out[ingredient_id]
                if side.hole is None:
                    side.hole = "lines with no quantity"
                    side.hole_note = note
            continue

        after_period = item.recipe_created_on is not None and item.recipe_created_on > date_to
        for ingredient_id, draw in draws.items():
            side = out[ingredient_id]
            base_qty = (row.qty_sold * draw.per_portion_base).quantize(
                BASE_QUANTUM, rounding=ROUND_HALF_UP
            )
            side.dishes[row.menu_item_id] = DishEntry(
                menu_item_id=row.menu_item_id,
                menu_item_name=row.menu_item_name,
                branch_id=branch_id,
                portions=row.qty_sold.quantize(QTY_QUANTUM),
                per_portion_base=draw.per_portion_base,
                usable_share=next(iter(draw.shares)) if len(draw.shares) == 1 else None,
                base_qty=base_qty,
            )
            side.total += base_qty
            side.refunded += row.qty_refunded or Decimal(0)
            side.versions.add(item.recipe_version)
            side.after_period = side.after_period or after_period
    return out


# --- the bought side (C14.3) ------------------------------------------------


@dataclass
class _BoughtSide:
    entries: list[LineEntry] = field(default_factory=list)
    measured_total: Decimal = Decimal(0)
    unmeasured: int = 0
    returns: int = 0
    overrides: int = 0
    papers: set[str] = field(default_factory=set)
    foreign: set[str] = field(default_factory=set)
    by_date: dict[datetime.date, Decimal] = field(default_factory=dict)

    @property
    def purchase_dates(self) -> int:
        """Dates whose net measured quantity was positive, so a credit note on
        a second day is not a second delivery and two papers on one morning
        are not two (D4, D15). The reason for the rule is time, so its unit is
        dates."""
        return sum(1 for total in self.by_date.values() if total > 0)


def _bought_by_material(
    placed: Sequence[_Placed],
    materials: Mapping[str, Material],
    *,
    branch_id: str,
    window: Window,
    currency: str,
) -> dict[str, _BoughtSide]:
    """Every material one branch bought inside its clipped window.

    Price and currency are not filters: a line with no unit price and a line
    on a paper billed in USD both delivered goods, both are measured, and the
    foreign paper is named on the row. A return nets out by its own sign.
    """
    out: dict[str, _BoughtSide] = {}
    for entry in placed:
        if entry.bucket != PLACED:
            continue
        line = entry.line
        if line.branch_id != branch_id:
            continue
        if not (window.start <= line.purchased_on <= window.end):
            continue
        assert line.ingredient_id is not None
        material = materials.get(line.ingredient_id)
        base_unit = material.base_unit if material else ""
        side = out.setdefault(line.ingredient_id, _BoughtSide())
        side.entries.append(_entry(entry.measured, base_unit))
        side.papers.add(line.invoice_id)
        if line.currency != currency:
            side.foreign.add(line.invoice_id)
        if line.qty is not None and line.qty < 0:
            # A line whose quantity cell was never read is neither a purchase
            # of a known amount nor a return; `measure` has already made it
            # unmeasured, and it is counted below with the rest of those.
            side.returns += 1
        if entry.measured.measured:
            assert entry.measured.base_qty is not None
            side.measured_total += entry.measured.base_qty
            side.by_date[line.purchased_on] = (
                side.by_date.get(line.purchased_on, Decimal(0)) + entry.measured.base_qty
            )
            if entry.measured.overridden:
                side.overrides += 1
        else:
            side.unmeasured += 1
    return out


# --- the row ----------------------------------------------------------------


def _foreign_sentences(placed: Sequence[LineEntry], currency: str) -> list[str]:
    by_currency: dict[str, set[str]] = {}
    for entry in placed:
        if entry.currency != currency:
            by_currency.setdefault(entry.currency, set()).add(entry.invoice_id)
    return [
        f"{_plural(len(papers), 'paper')} billed in {code}, counted by quantity"
        for code, papers in sorted(by_currency.items())
    ]


def _row(
    *,
    material: Material,
    branch: BranchWindow | None,
    window: Window,
    used: _UsedSide | None,
    bought: _BoughtSide | None,
    price: MaterialPrice | None,
    stale: bool,
    currency: str,
    branch_id: str | None,
) -> MaterialRow:
    """One material row: the two figures, the difference, what it costs, and
    the worse of three halves with every sentence that made it."""
    notes: list[str] = []
    sales_quality = Quality(branch.sales_quality) if branch is not None else Quality.RELIABLE
    purchase_quality = Quality.RELIABLE
    material_quality = Quality.RELIABLE

    # --- the used side
    used_base: Decimal | None = None
    used_measured: Decimal | None = None
    used_hole: str | None = None
    dishes: tuple[DishEntry, ...] = ()
    refunded: Decimal | None = None
    dishes_counted = 0
    after_period = False
    versions: set[int | None] = set()
    if branch is not None and not branch.sales_loaded:
        # D12: purchases and no sales loaded. The sales half is already
        # `unavailable` and already carries its sentence; nothing is re-worded.
        used_hole = "no sales loaded"
    elif used is not None:
        dishes = tuple(
            sorted(used.dishes.values(), key=lambda d: (d.menu_item_name, d.menu_item_id))
        )
        dishes_counted = len(dishes)
        refunded = used.refunded.quantize(QTY_QUANTUM)
        after_period = used.after_period
        versions = used.versions
        if used.hole is None:
            used_base = used.total
        else:
            used_hole = used.hole
            used_measured = used.total
    else:
        used_base = Decimal(0)

    # --- the bought side
    bought_base: Decimal | None = None
    bought_measured: Decimal | None = None
    bought_hole: str | None = None
    lines: tuple[LineEntry, ...] = ()
    purchases = purchase_dates = returns = foreign = unmeasured = 0
    if not material.has_packs:
        bought_hole = "no pack mapped"
        material_quality = Quality.INCOMPLETE
        notes.append(_no_pack_sentence(material))
    elif bought is None or not bought.entries:
        # Nothing delivered inside the window is a fact, not a hole: the row
        # reads `under` by everything its recipes needed and says so.
        bought_base = Decimal(0)
        purchase_quality = _worse(purchase_quality, Quality.INCOMPLETE)
    else:
        lines = tuple(
            sorted(bought.entries, key=lambda entry: (entry.purchased_on, entry.line_position))
        )
        purchases = len(bought.papers)
        purchase_dates = bought.purchase_dates
        returns = bought.returns
        foreign = len(bought.foreign)
        unmeasured = bought.unmeasured
        if unmeasured:
            bought_hole = f"{_plural(unmeasured, 'line')} could not be measured"
            bought_measured = bought.measured_total
            material_quality = _worse(material_quality, Quality.INCOMPLETE)
        else:
            bought_base = bought.measured_total
        if bought.overrides:
            purchase_quality = _worse(purchase_quality, Quality.ESTIMATED)

    # --- the difference, and what it costs
    gap: Decimal | None = None
    direction: str | None = None
    money: Decimal | None = None
    per_display: Decimal | None = None
    display_unit: str | None = None
    price_quality: str | None = None
    if used_base is not None and bought_base is not None:
        gap = bought_base - used_base
        direction = _direction_of(gap)
        notes.append(_direction_sentence(gap, material.base_unit))
    if purchase_dates == 1:
        notes.append("1 purchase date in this window; a single delivery is not a rate")
    usable_price = (
        price if price is not None and price.cost_base_unit == material.base_unit else None
    )
    if usable_price is None:
        if gap is not None:
            notes.append("no price to value it at")
    else:
        estimated_price = stale or usable_price.quality == Quality.ESTIMATED.value
        sentence, per_display, display_unit = _price_sentence(
            usable_price, estimated=estimated_price, currency=currency
        )
        notes.append(sentence)
        price_quality = Quality.ESTIMATED.value if estimated_price else Quality.RELIABLE.value
        if estimated_price:
            purchase_quality = _worse(purchase_quality, Quality.ESTIMATED)
        if gap is not None:
            money = (gap * usable_price.cost_per_base_unit).quantize(FILS, rounding=ROUND_HALF_UP)

    # --- the sentences the halves are made of
    if versions:
        notes.append(_recipe_sentence(versions))
    if after_period:
        material_quality = _worse(material_quality, Quality.ESTIMATED)
        notes.append("recipe written after this period")
    if refunded:
        word = "portion" if refunded == 1 else "portions"
        notes.append(f"{_qty_words(refunded)} {word} refunded, counted as made")
    if returns:
        notes.append(_plural(returns, "return"))
    notes.extend(_foreign_sentences(lines, currency))
    if bought is not None and bought.overrides:
        notes.append(f"a pack size you entered measures {_plural(bought.overrides, 'line')}")
    if unmeasured:
        notes.append(
            f"{_plural(unmeasured, 'line')} could not be measured - see Can't be costed yet"
        )
    if material.has_packs and (bought is None or not bought.entries):
        notes.append(f"no purchases in this window, {window_words(window)}")
    if branch is not None and branch.pending:
        purchase_quality = _worse(purchase_quality, Quality.ESTIMATED)
        notes.extend(_pending_sentences(list(branch.pending)))
    if used is not None and used.hole_note is not None:
        material_quality = _worse(material_quality, Quality.INCOMPLETE)
        notes.append(used.hole_note)
    if branch is not None:
        notes.extend(n for n in branch.sales_notes if n not in notes)

    quality = _worse(_worse(sales_quality, purchase_quality), material_quality)
    return MaterialRow(
        ingredient_id=material.ingredient_id,
        ingredient_name=material.name,
        base_unit=material.base_unit,
        branch_id=branch_id,
        window=window,
        used_base=used_base,
        bought_base=bought_base,
        gap_base=gap,
        used_measured=used_measured,
        bought_measured=bought_measured,
        used_words=None if used_base is None else quantity_words(used_base, material.base_unit),
        bought_words=(
            None if bought_base is None else quantity_words(bought_base, material.base_unit)
        ),
        gap_words=None if gap is None else _gap_words(gap, material.base_unit),
        used_measured_words=(
            None if used_measured is None else quantity_words(used_measured, material.base_unit)
        ),
        bought_measured_words=(
            None if bought_measured is None else quantity_words(bought_measured, material.base_unit)
        ),
        direction=direction,
        money=money,
        price_per_display_unit=per_display,
        display_unit=display_unit,
        priced_on=None if usable_price is None else usable_price.priced_on,
        price_quality=price_quality,
        purchases=purchases,
        purchase_dates=purchase_dates,
        returns=returns,
        foreign_papers=foreign,
        unmeasured_lines=unmeasured,
        dishes_counted=dishes_counted,
        refunded_portions=refunded,
        recipe_after_period=after_period,
        quality=quality,
        notes=tuple(notes),
        lines=lines,
        dishes=dishes,
        used_hole=used_hole,
        bought_hole=bought_hole,
    )


def rank(rows: Iterable[MaterialRow]) -> list[MaterialRow]:
    """Absolute money in the difference, largest first; rows with no price
    next by absolute quantity; rows with a hole last; ties by name (C14.10).

    Both directions, because the owner wants both first: a large positive
    difference is stock built or a delivery that outran the week, a negative
    one is a recipe or a pack size that is wrong, and the second is the most
    valuable thing the panel finds. The sentence carries the direction so the
    ranking does not have to.
    """
    return sorted(
        rows,
        key=lambda r: (
            0 if r.money is not None else (1 if r.gap_base is not None else 2),
            -abs(r.money) if r.money is not None else Decimal(0),
            -abs(r.gap_base) if r.money is None and r.gap_base is not None else Decimal(0),
            r.ingredient_name,
            r.ingredient_id,
            r.branch_id or "",
        ),
    )


def material_rows(
    item_rows: Iterable[contribution.ItemRow],
    menu: Mapping[str, contribution.MenuItem],
    lines: Iterable[PurchaseLine],
    windows: Iterable[BranchWindow],
    *,
    materials: Mapping[str, Material],
    prices: Mapping[str, MaterialPrice],
    stale_ingredient_ids: frozenset[str] = frozenset(),
    date_from: datetime.date,
    date_to: datetime.date,
    currency: str = contribution.DEFAULT_CURRENCY,
) -> list[MaterialRow]:
    """Every (material, branch) comparison row for the period, ranked (C14).

    A row exists for a material a **sold recipe names** - one bought outside
    every sold recipe is `unused_materials`, out of the ranking (D11) - and
    for a material a branch bought that some branch's sold recipe names, so a
    branch with purchases and no sales keeps its purchase-only rows (D12).
    """
    rows = list(item_rows)
    placed = _place(lines)
    named: set[str] = set()
    for row in rows:
        item = menu.get(row.menu_item_id)
        if item is None:
            continue
        for component in item.components:
            named.add(component.ingredient_id)

    out: list[MaterialRow] = []
    for branch in windows:
        window = branch.window(date_from, date_to)
        own_rows = [r for r in rows if r.branch_id == branch.branch_id]
        used = _used_by_material(
            own_rows, menu, materials, branch_id=branch.branch_id, date_to=date_to
        )
        bought = _bought_by_material(
            placed, materials, branch_id=branch.branch_id, window=window, currency=currency
        )
        wanted = {i for i in used if i in named} | {i for i in bought if i in named}
        for ingredient_id in wanted:
            material = _material_for(
                ingredient_id,
                _name_of(ingredient_id, menu, materials),
                None,
                materials,
            )
            out.append(
                _row(
                    material=material,
                    branch=branch,
                    window=window,
                    used=used.get(ingredient_id),
                    bought=bought.get(ingredient_id),
                    price=prices.get(ingredient_id),
                    stale=ingredient_id in stale_ingredient_ids,
                    currency=currency,
                    branch_id=branch.branch_id,
                )
            )
    return rank(out)


def _name_of(
    ingredient_id: str,
    menu: Mapping[str, contribution.MenuItem],
    materials: Mapping[str, Material],
) -> str:
    known = materials.get(ingredient_id)
    if known is not None:
        return known.name
    for item in menu.values():
        for component in item.components:
            if component.ingredient_id == ingredient_id:
                return component.ingredient_name
    return ingredient_id


# --- the chain (C14.9) ------------------------------------------------------


def chain_material_rows(
    rows: Iterable[MaterialRow],
    *,
    materials: Mapping[str, Material],
    prices: Mapping[str, MaterialPrice],
    branch_names: Mapping[str, str] | None = None,
    unassigned: Iterable[UnassignedRow] = (),
    stale_ingredient_ids: frozenset[str] = frozenset(),
    date_from: datetime.date,
    date_to: datetime.date,
    currency: str = contribution.DEFAULT_CURRENCY,
) -> list[MaterialRow]:
    """One row per material across the branches, summing exactly the branches
    it names and saying which it left out and why (C14.9).

    Pinned, and exact because of where the rounding happens: chain bought is
    the sum of branch bought over the branches it names, and chain used the
    sum of branch used over the branches it names. Papers with no branch are
    **not** in it - they lie in the whole period while branch rows lie in
    clipped windows, so a sum would add two spans - and the note says how much
    they hold instead.

    A chain row carries no drill (D10): unfiltered, the branch rows carry the
    lines and the dishes, so nothing on the wire is duplicated and a branch is
    always named beside its lines.
    """
    names = branch_names or {}
    period = Window(date_from, date_to)
    grouped: dict[str, list[MaterialRow]] = {}
    for row in rows:
        grouped.setdefault(row.ingredient_id, []).append(row)
    held: dict[str, UnassignedRow] = {u.ingredient_id: u for u in unassigned}

    out: list[MaterialRow] = []
    for ingredient_id, group in grouped.items():
        material = Material(
            ingredient_id=ingredient_id,
            name=group[0].ingredient_name,
            base_unit=group[0].base_unit,
            has_packs=any(r.bought_hole != "no pack mapped" for r in group),
        )
        with_used = [r for r in group if r.used_base is not None]
        with_bought = [r for r in group if r.bought_base is not None]
        used_base = (
            sum((r.used_base for r in with_used), Decimal(0)) if with_used else None  # type: ignore[misc]
        )
        bought_base = (
            sum((r.bought_base for r in with_bought), Decimal(0))  # type: ignore[misc]
            if with_bought
            else None
        )

        notes: list[str] = []
        quality = Quality.RELIABLE
        for row in group:
            quality = _worse(quality, row.quality)

        left_out: list[str] = []
        for row in group:
            branch = names.get(row.branch_id or "", row.branch_id or "a branch")
            if row.used_hole == "no sales loaded":
                left_out.append(f"{branch}: no sales loaded")
            elif row.used_base is None and row.used_hole:
                left_out.append(f"{branch} not included: {row.used_hole}")
            if row.bought_base is None and row.bought_hole:
                left_out.append(f"{branch} not included: {row.bought_hole}")
        if left_out:
            quality = _worse(quality, Quality.INCOMPLETE)

        gap: Decimal | None = None
        direction: str | None = None
        money: Decimal | None = None
        per_display: Decimal | None = None
        display_unit: str | None = None
        price_quality: str | None = None
        if used_base is not None and bought_base is not None:
            gap = bought_base - used_base
            direction = _direction_of(gap)
            notes.append(_direction_sentence(gap, material.base_unit))
        purchase_dates = sum(r.purchase_dates for r in group)
        if purchase_dates == 1:
            notes.append("1 purchase date in this window; a single delivery is not a rate")
        price = prices.get(ingredient_id)
        usable_price = (
            price if price is not None and price.cost_base_unit == material.base_unit else None
        )
        if usable_price is None:
            if gap is not None:
                notes.append("no price to value it at")
        else:
            estimated_price = (
                ingredient_id in stale_ingredient_ids
                or usable_price.quality == Quality.ESTIMATED.value
            )
            sentence, per_display, display_unit = _price_sentence(
                usable_price, estimated=estimated_price, currency=currency
            )
            notes.append(sentence)
            price_quality = Quality.ESTIMATED.value if estimated_price else Quality.RELIABLE.value
            if estimated_price:
                quality = _worse(quality, Quality.ESTIMATED)
            if gap is not None:
                money = (gap * usable_price.cost_per_base_unit).quantize(
                    FILS, rounding=ROUND_HALF_UP
                )

        counted = with_used or with_bought or group
        distinct = {(r.window.start, r.window.end) for r in counted}
        if len(distinct) > 1:
            spans = _names_words(
                [
                    f"{window_words(r.window)} at {names.get(r.branch_id or '', r.branch_id or '')}"
                    for r in sorted(counted, key=lambda r: (r.window.start, r.branch_id or ""))
                ]
            )
            notes.append(f"over {spans}")
        notes.extend(left_out)
        holding = held.get(ingredient_id)
        if holding is not None:
            verb = "holds" if holding.papers == 1 else "hold"
            notes.append(
                f"{_plural(holding.papers, 'paper')} with no branch "
                f"{verb} {holding.bought_words} of {material.name}, not counted here"
            )

        out.append(
            MaterialRow(
                ingredient_id=ingredient_id,
                ingredient_name=material.name,
                base_unit=material.base_unit,
                branch_id=None,
                window=period,
                used_base=used_base,
                bought_base=bought_base,
                gap_base=gap,
                used_measured=None,
                bought_measured=None,
                used_words=(
                    None if used_base is None else quantity_words(used_base, material.base_unit)
                ),
                bought_words=(
                    None if bought_base is None else quantity_words(bought_base, material.base_unit)
                ),
                gap_words=None if gap is None else _gap_words(gap, material.base_unit),
                used_measured_words=None,
                bought_measured_words=None,
                direction=direction,
                money=money,
                price_per_display_unit=per_display,
                display_unit=display_unit,
                priced_on=None if usable_price is None else usable_price.priced_on,
                price_quality=price_quality,
                purchases=sum(r.purchases for r in group),
                purchase_dates=purchase_dates,
                returns=sum(r.returns for r in group),
                foreign_papers=sum(r.foreign_papers for r in group),
                unmeasured_lines=sum(r.unmeasured_lines for r in group),
                dishes_counted=sum(r.dishes_counted for r in group),
                refunded_portions=sum(
                    (r.refunded_portions or Decimal(0) for r in group), Decimal(0)
                ).quantize(QTY_QUANTUM),
                recipe_after_period=any(r.recipe_after_period for r in group),
                quality=quality,
                notes=tuple(notes),
            )
        )
    return rank(out)


# --- the lists beside the panel ---------------------------------------------


def _printed_name(group: Sequence[_Placed]) -> str:
    """The catalog name of the product these lines were booked under, or the
    name the paper printed - a stand-in only where the caller's material map
    does not hold the material."""
    line = group[0].line
    return line.canonical_name or line.raw_name


def unassigned_rows(
    lines: Iterable[PurchaseLine],
    *,
    materials: Mapping[str, Material],
) -> list[UnassignedRow]:
    """Materials bought on papers that named no branch (C14.9). Listed per
    material with their lines, in no row and in no chain figure."""
    grouped: dict[str, list[_Placed]] = {}
    for entry in _place(lines):
        if entry.bucket != UNASSIGNED:
            continue
        assert entry.line.ingredient_id is not None
        grouped.setdefault(entry.line.ingredient_id, []).append(entry)

    out: list[UnassignedRow] = []
    for ingredient_id, group in grouped.items():
        material = _material_for(ingredient_id, _printed_name(group), None, materials)
        total = sum(
            (e.measured.base_qty for e in group if e.measured.base_qty is not None),
            Decimal(0),
        )
        out.append(
            UnassignedRow(
                ingredient_id=ingredient_id,
                ingredient_name=material.name,
                base_unit=material.base_unit,
                bought_base=total,
                bought_words=quantity_words(total, material.base_unit),
                papers=len({e.line.invoice_id for e in group}),
                lines=tuple(
                    _entry(e.measured, material.base_unit)
                    for e in sorted(
                        group, key=lambda e: (e.line.purchased_on, e.line.line_position)
                    )
                ),
            )
        )
    return sorted(out, key=lambda r: (r.ingredient_name, r.ingredient_id))


def unused_materials(
    lines: Iterable[PurchaseLine],
    named_ingredient_ids: Iterable[str],
    *,
    materials: Mapping[str, Material],
    prices: Mapping[str, MaterialPrice],
    windows: Iterable[BranchWindow] = (),
    branch_id: str | None = None,
    date_from: datetime.date,
    date_to: datetime.date,
) -> list[UnusedMaterial]:
    """Materials with purchases that no sold recipe names: gloves, cleaning
    fluid, a cup nobody has put in a recipe yet (D11).

    Listed apart and out of the ranking, because a comparison row needs
    something to compare against and there is nothing here - not a difference
    of the whole purchase, which would read as the largest one on the panel.
    """
    named = set(named_ingredient_ids)
    by_branch = {w.branch_id: w for w in windows}
    grouped: dict[str, list[_Placed]] = {}
    for entry in _place(lines):
        if entry.bucket != PLACED:
            continue
        line = entry.line
        assert line.ingredient_id is not None and line.branch_id is not None
        if line.ingredient_id in named:
            continue
        if branch_id is not None and line.branch_id != branch_id:
            continue
        window = (
            by_branch[line.branch_id].window(date_from, date_to)
            if (line.branch_id in by_branch)
            else Window(date_from, date_to)
        )
        if not (window.start <= line.purchased_on <= window.end):
            continue
        grouped.setdefault(line.ingredient_id, []).append(entry)

    out: list[UnusedMaterial] = []
    for ingredient_id, group in grouped.items():
        material = _material_for(ingredient_id, _printed_name(group), None, materials)
        total = sum(
            (e.measured.base_qty for e in group if e.measured.base_qty is not None),
            Decimal(0),
        )
        price = prices.get(ingredient_id)
        money = (
            (total * price.cost_per_base_unit).quantize(FILS, rounding=ROUND_HALF_UP)
            if price is not None and price.cost_base_unit == material.base_unit
            else None
        )
        out.append(
            UnusedMaterial(
                ingredient_id=ingredient_id,
                ingredient_name=material.name,
                base_unit=material.base_unit,
                branch_id=branch_id,
                bought_base=total,
                bought_words=quantity_words(total, material.base_unit),
                money=money,
                purchases=len({e.line.invoice_id for e in group}),
                sentence="bought, not in any sold recipe",
            )
        )
    return sorted(
        out,
        key=lambda u: (
            -abs(u.money) if u.money is not None else Decimal(0),
            u.money is None,
            u.ingredient_name,
        ),
    )


def unmapped_packs(
    lines: Iterable[PurchaseLine],
    *,
    currency: str = contribution.DEFAULT_CURRENCY,
) -> UnmappedPacks:
    """Confirmed purchase lines whose product has no material yet (D6, D21).

    The spend is the **printed line totals** in the tenant's currency and
    nothing is converted: a foreign line is counted and named on the sentence,
    because an exchange rate Faida does not hold would be a number nobody
    could check.
    """
    group = [e for e in _place(lines) if e.bucket == UNMAPPED]
    if not group:
        return UnmappedPacks(lines=0, packs=0, spend=Decimal(0), foreign_lines=0, sentence=None)
    spend = sum(
        (
            e.line.line_total
            for e in group
            if e.line.currency == currency and e.line.line_total is not None
        ),
        Decimal(0),
    ).quantize(FILS)
    foreign = sum(1 for e in group if e.line.currency != currency)
    packs = len({e.line.supplier_item_id for e in group})
    sentence = (
        f"{_plural(len(group), 'purchase line')} on {_plural(packs, 'product')} "
        f"{'has' if len(group) == 1 else 'have'} no material yet, "
        f"{_money_words(spend, currency)} on the printed line totals"
    )
    if foreign:
        codes = sorted({e.line.currency for e in group if e.line.currency != currency})
        sentence += f", {foreign} of them billed in {' and '.join(codes)}"
    return UnmappedPacks(
        lines=len(group),
        packs=packs,
        spend=spend,
        foreign_lines=foreign,
        sentence=sentence,
    )


def orphans(
    lines: Iterable[PurchaseLine],
    *,
    currency: str = contribution.DEFAULT_CURRENCY,
) -> Orphans:
    """Confirmed lines that reached no catalog product at all (D3).

    The confirm door creates no product for a paper billed in another currency
    and none for a line with no price, and a product is the only path to a
    material - so these lines are measured, counted and their papers named,
    and they are in no row and in no queue. The root fix is a product row for
    every stock line at confirm, and it is in `TODOS.md` with its trigger: the
    confirm transaction is the most sensitive code in the product.
    """
    group = [e for e in _place(lines) if e.bucket == ORPHAN]
    if not group:
        return Orphans(lines=0, foreign=0, no_price=0, unmatched=0, papers=(), sentence=None)
    foreign = [e for e in group if e.line.currency != currency]
    no_price = [e for e in group if e.line.currency == currency and e.line.unit_price is None]
    unmatched = [e for e in group if e.line.currency == currency and e.line.unit_price is not None]
    papers: dict[str, list[_Placed]] = {}
    for entry in group:
        papers.setdefault(entry.line.invoice_id, []).append(entry)
    reasons = []
    if foreign:
        codes = sorted({e.line.currency for e in foreign})
        reasons.append(f"{len(foreign)} billed in {' and '.join(codes)}")
    if no_price:
        reasons.append(f"{len(no_price)} with no price")
    if unmatched:
        reasons.append(f"{len(unmatched)} not matched to a product")
    sentence = f"{_plural(len(group), 'line')} reached no product: {', '.join(reasons)}"
    return Orphans(
        lines=len(group),
        foreign=len(foreign),
        no_price=len(no_price),
        unmatched=len(unmatched),
        papers=tuple(
            OrphanPaper(
                invoice_id=invoice_id,
                invoice_no=entries[0].line.invoice_no,
                supplier_name=entries[0].line.supplier_name,
                currency=entries[0].line.currency,
                lines=len(entries),
            )
            for invoice_id, entries in sorted(papers.items())
        ),
        sentence=sentence,
    )


def recipe_coverage(
    sales: Iterable[contribution.ItemSales],
    menu: Mapping[str, contribution.MenuItem],
    *,
    orphan_lines: int = 0,
    scope_words: str = "this branch's",
) -> Coverage:
    """*Recipes cover N% of this branch's sales value* (C14.2, P4).

    Computed from the **raw** item-sales rows and never from
    `contribution.item_rows`, because `item_rows` drops the unmapped and
    excluded names and the denominator needs the unmapped ones: a till name
    nobody has mapped is sales this panel could not follow to a material.

    `orphan_lines` is the count the caller counted with `orphans` - the lines
    that reached no catalog product - named on this line (D20), so the rows
    above admit an unplaced purchase as well as an unfollowed sale. The count
    comes from the caller; the words are composed here like every other.
    """
    rows = [row for row in sales if not row.excluded]
    sales_value = sum((row.positive_value for row in rows), Decimal(0))
    covered = Decimal(0)
    without_recipe: set[str] = set()
    unmapped: set[str] = set()
    for row in rows:
        item = menu.get(row.menu_item_id or "")
        if row.menu_item_id is None or item is None:
            unmapped.add(row.till_item_id)
            continue
        if item.components:
            covered += row.positive_value
        else:
            without_recipe.add(row.menu_item_id)
    pct = (
        (covered / sales_value * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if sales_value > 0
        else None
    )
    if pct is None:
        sentence = f"no sales value to measure {scope_words} recipe coverage on"
    else:
        sentence = (
            f"recipes cover {pct.quantize(Decimal('1'), rounding=ROUND_HALF_UP)}% "
            f"of {scope_words} sales value"
        )
        if without_recipe:
            sentence += (
                f"; {_plural(len(without_recipe), 'dish')} sold "
                f"{'has' if len(without_recipe) == 1 else 'have'} no recipe"
            )
        if unmapped:
            sentence += (
                f"; {_plural(len(unmapped), 'till name')} sold "
                f"{'is' if len(unmapped) == 1 else 'are'} not mapped to a dish"
            )
    if orphan_lines:
        sentence += f"; {_plural(orphan_lines, 'purchase line')} reached no product"
    return Coverage(
        recipes_pct=pct,
        covered_value=covered.quantize(FILS),
        sales_value=sales_value.quantize(FILS),
        dishes_without_recipe=len(without_recipe),
        unmapped_names=len(unmapped),
        sentence=sentence,
    )


def left_out(
    item_rows: Iterable[contribution.ItemRow],
    lines: Iterable[PurchaseLine],
    windows: Iterable[BranchWindow],
    menu: Mapping[str, contribution.MenuItem],
) -> LeftOut:
    """What the panel could not count, in four numbers (§3.1)."""
    rows = list(item_rows)
    return LeftOut(
        items_without_quantity=sum(1 for r in rows if r.qty_sold is None),
        items_without_recipe=len(
            {
                r.menu_item_id
                for r in rows
                if r.menu_item_id in menu and not menu[r.menu_item_id].components
            }
        ),
        unmeasured_lines=sum(
            1 for e in _place(lines) if e.bucket == PLACED and not e.measured.measured
        ),
        branches_without_sales=sum(1 for w in windows if not w.sales_loaded),
    )


def sentences(*blocks: object) -> list[str]:
    """Every sentence a set of results composed, for the forbidden-phrase test
    (C14.5) and for a printout that wants to read them all.

    The test that calls this is not a grep of code: it builds a stage that
    exercises every branch of this module and reads the words back.
    """
    out: list[str] = [STANDING_SENTENCE]
    for block in blocks:
        for name in (
            "notes",
            "used_words",
            "bought_words",
            "gap_words",
            "used_measured_words",
            "bought_measured_words",
            "sentence",
        ):
            value = getattr(block, name, None)
            if isinstance(value, str):
                out.append(value)
            elif isinstance(value, tuple):
                out.extend(v for v in value if isinstance(v, str))
    return out
