"""M5 WP-53: what one gram of this actually cost.

The first number Faida shows that no photograph shows back. Every figure up to
here sat beside its image and a human could catch it; a cost per gram is two
divisions away from the page, and by M6 it is folded four sums deep into a
plate margin. So this module is written to two rules.

**One implementation of the money.** The price a cost divides is the same
ex-VAT, post-discount price that reaches supplier memory - C4's net-canonical
rule (plan.md §7.2). It is produced from the same two factors
`record_confirmed_prices` derives per invoice, not from a second copy of the
arithmetic. The one difference is where the rounding happens: price memory
quantizes to fils because that is what its column holds, and a cost quantizes
**once, at the division**, to eight decimal places. Flour at AED 43.50 per
25 kg is 0.00174 AED per gram; rounded to three places it is 0.002, a 15%
error on every plate of biryani and one nobody would ever see.

**No cost is ever verified.** C4's arithmetic proves `qty x unit_price =
line_total`, so two other numbers on the page corroborate the unit price. Pack
size appears in no identity at all. A supplier prints 25 kg, the model reads
2.5 kg, every check we have still passes, and the cost is ten times too high.
So a cost reads *reliable with limitations* at its best, and *estimated* when a
person supplied one of its inputs (C9, PRD §24's vocabulary). The vocabulary is
deliberately short of a green badge, because a green badge here would be a
claim nothing can support.

Pure module: no I/O, no database, no knowledge of how a line is stored. `db.py`
feeds it rows and writes what it returns.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from . import provenance
from .extraction import units

#: The column is `numeric(18,8)`, and this is the single point at which a cost
#: is rounded: once, at the division, half up.
COST_QUANTUM = Decimal("0.00000001")

#: Money rounds to fils on a screen. A cost per kilo is money.
DISPLAY_QUANTUM = Decimal("0.01")

#: What a person is quoted a price in, per base unit. Nobody buys a gram.
DISPLAY_UNITS: dict[str, tuple[str, Decimal]] = {
    "g": ("kg", Decimal("1000")),
    "ml": ("litre", Decimal("1000")),
    "pc": ("each", Decimal("1")),
}


class Quality(StrEnum):
    """PRD §24's report-quality vocabulary, minus the word we cannot earn.

    `verified` is absent on purpose and a test pins its absence: nothing
    anywhere corroborates a pack size, so a cost that claimed to be verified
    would be the old platform's dominant failure - a confidently wrong number
    nobody was invited to check - reappearing in the layer C9 exists to
    protect.
    """

    RELIABLE = "reliable_with_limitations"
    ESTIMATED = "estimated"


class PackSource(StrEnum):
    """Where the amount we divided by was read. In resolution order."""

    PACK_COLUMN = "pack_size"  # the invoice's own pack column
    ITEM_NAME = "raw_name"  # printed inside the product name ("RICE BASM 5KG")
    LINE_UNIT = "unit"  # the unit column is itself a measure ("KG"), so one of it
    OVERRIDE = "override"  # a person said what is inside the container (WP-55)


class Blocked(StrEnum):
    """Why a line has no cost. Each one is a different sentence to a human and
    a different thing to do about it, which is why they are not one flag."""

    FOREIGN_CURRENCY = "foreign_currency"
    MISSING_UNIT_PRICE = "missing_unit_price"
    MISSING_QUANTITY = "missing_quantity"
    ZERO_PACK = "zero_pack"
    BARE_CONTAINER = "bare_container"
    UNPARSEABLE_PACK = "unparseable_pack"


#: Plain English for each blocker, for the screen (WP-55). The no-jargon
#: display rule (plan.md §3) applies hardest here: these sentences are read by
#: a consultant deciding what to do next, so each says what is missing rather
#: than what failed.
BLOCKED_REASONS: dict[Blocked, str] = {
    Blocked.FOREIGN_CURRENCY: (
        "This invoice is billed in another currency, so its prices are held back."
    ),
    Blocked.MISSING_UNIT_PRICE: "The invoice does not show a price for this line.",
    Blocked.MISSING_QUANTITY: (
        "The invoice does not show how many were bought, so nothing checks the price."
    ),
    Blocked.ZERO_PACK: "The pack size names a unit but no amount to divide by.",
    Blocked.BARE_CONTAINER: "Nothing on the invoice says how much one of these holds.",
    Blocked.UNPARSEABLE_PACK: "Nothing on this line reads as a pack size.",
}

#: The blockers a pack-size override can clear (WP-55). The other two are
#: missing numbers on the paper, and no conversion supplies those.
OVERRIDABLE = frozenset({Blocked.ZERO_PACK, Blocked.BARE_CONTAINER, Blocked.UNPARSEABLE_PACK})


@dataclass(frozen=True)
class Pack:
    """The amount one unit price buys, and where we read it."""

    printed: str
    base_quantity: Decimal
    base_unit: str
    source: PackSource


@dataclass(frozen=True)
class LineCost:
    """A cost, or the reason there is not one. Never both."""

    cost: Decimal | None = None
    base_unit: str | None = None
    quality: Quality | None = None
    #: The field paths a person asserted that this cost leans on (C9). Empty
    #: when every input came off the photo.
    asserted: tuple[str, ...] = ()
    pack: Pack | None = None
    blocked: Blocked | None = None

    def basis(self) -> dict:
        """The C8-shaped record that travels with the number: what it was
        divided by, where that came from, how good it is and which of its
        inputs a person supplied. Stored as the line's `cost_basis`."""
        if self.pack is None:
            return {}
        return {
            "quality": self.quality.value,
            "asserted": list(self.asserted),
            "pack": self.pack.printed,
            "pack_base_quantity": str(self.pack.base_quantity),
            "pack_source": self.pack.source.value,
        }


def _measurable(pack: units.PackSize | None) -> str | None:
    """The base unit a parsed pack reduces to, or None when it is a bare
    container. A carton is not an amount until someone says what is in it."""
    if pack is None:
        return None
    return units.BASE_UNITS.get(pack.unit.dimension)


def _from_text(text: str | None, source: PackSource) -> Pack | None:
    parsed = units.parse(text)
    base_unit = _measurable(parsed)
    if base_unit is None:
        return None
    printed = units.first_printed(text) or str(parsed)
    return Pack(printed, parsed.base_quantity, base_unit, source)


def _from_unit_column(unit: str | None) -> Pack | None:
    """A unit column that is itself a measure prices one of that unit: 25 KG
    of tomatoes at AED 3.50 is AED 3.50 per kilo. Common on produce invoices,
    which have no pack column at all because the pack is the kilo."""
    canonical = units.canonical_unit(unit)
    if canonical is None:
        return None
    measure = units.UNITS[canonical]
    base_unit = units.BASE_UNITS.get(measure.dimension)
    if base_unit is None:
        return None
    return Pack(f"1 {canonical}", measure.to_base, base_unit, PackSource.LINE_UNIT)


def resolve_pack(
    *,
    pack_size: str | None,
    raw_name: str | None,
    unit: str | None,
    override: str | None = None,
) -> Pack | None:
    """How much one unit price buys, in grams, millilitres or pieces.

    In order: the invoice's own pack column; a pack printed inside the product
    name (a till receipt has no pack column and puts it there, which
    `matching.snap_item` already trusts); the unit column when it is itself a
    measure; and last a human's conversion for a container (WP-55), which is
    consulted only when the paper said nothing we could read - the photo
    outranks a standing note about what is usually in a box.

    A step that names a bare container does not end the search: "1 ctn" in the
    pack column beside "MILK PWDR 2.5KG" in the name means the name is right.
    None means nothing here is an amount, and `blocked_reason` says which kind
    of nothing it was.
    """
    return (
        _from_text(pack_size, PackSource.PACK_COLUMN)
        or _from_text(raw_name, PackSource.ITEM_NAME)
        or _from_unit_column(unit)
        or _from_text(override, PackSource.OVERRIDE)
    )


def blocked_reason(*, pack_size: str | None, unit: str | None) -> Blocked:
    """Which kind of unreadable a pack was, so the screen can say something a
    consultant can act on.

    Only the two short cells whose job is to name a unit are consulted. Run
    over a product name this would find units inside words - "MILK" ends in
    the K a thermal receipt truncates kilograms to - and a wrong reason on a
    screen is worse than a general one.
    """
    for cell in (pack_size, unit):
        named = units.named_unit(cell)
        if named is None:
            continue
        if units.UNITS[named].dimension is units.Dimension.PACKAGING:
            return Blocked.BARE_CONTAINER
        # A measure we understand, and still no amount: "0 KG", or a pack
        # column that printed the unit and lost the number.
        return Blocked.ZERO_PACK
    return Blocked.UNPARSEABLE_PACK


def cost_inputs(
    position: int,
    *,
    pack_source: PackSource,
    vat_inclusive: bool,
    discounted: bool,
    stock_positions: Iterable[int] = (),
) -> list[str]:
    """Every field this line's cost is computed from, as C8 field paths.

    C9 asks which of a derived number's inputs a person asserted rather than a
    camera saw, and this is the list it asks about. It mirrors the real
    dependency rather than the obvious one: on a VAT-inclusive invoice the
    ex-VAT factor comes from the printed `total` and `tax`, and on a
    discounted invoice the allocation is pro rata over the stock-line sum - so
    a corrected `line_total` three rows away moves this line's cost, and taints
    it.
    """
    keys = [
        provenance.line_key(position, "unit_price"),
        provenance.line_key(position, "pack_size"),
    ]
    if pack_source is PackSource.ITEM_NAME:
        keys.append(provenance.line_key(position, "raw_name"))
    elif pack_source is PackSource.LINE_UNIT:
        keys.append(provenance.line_key(position, "unit"))
    if vat_inclusive:
        keys.extend(("total", "tax"))
    if discounted:
        keys.append("discount_total")
        keys.extend(provenance.line_key(other, "line_total") for other in stock_positions)
    return keys


def cost_line(
    *,
    position: int,
    qty: Decimal | None,
    unit_price: Decimal | None,
    pack_size: str | None,
    raw_name: str | None,
    unit: str | None,
    net_factor: Decimal | None = None,
    discount_factor: Decimal | None = None,
    asserted: Iterable[str] = (),
    stock_positions: Iterable[int] = (),
    override: str | None = None,
) -> LineCost:
    """This line's cost per base unit, or the reason it has none.

    `net_factor` and `discount_factor` are the two `record_confirmed_prices`
    already derives for the invoice (C4): the ex-VAT multiplier and the pro
    rata discount allocation. They are applied to the printed unit price and
    the division is rounded once, so a cost never inherits the fils rounding
    price memory needs for its own column.

    `qty` is not in the arithmetic and is still required: `qty x unit_price =
    line_total` is the only thing that corroborates the unit price, so without
    it there is a number with nothing behind it, and this layer's whole job is
    to not build on those quietly. A *negative* quantity is fine - a credit
    line returning one box of avocados was still billed at that price per box.
    """
    if unit_price is None:
        return LineCost(blocked=Blocked.MISSING_UNIT_PRICE)
    if qty is None:
        return LineCost(blocked=Blocked.MISSING_QUANTITY)

    pack = resolve_pack(pack_size=pack_size, raw_name=raw_name, unit=unit, override=override)
    if pack is None:
        return LineCost(blocked=blocked_reason(pack_size=pack_size, unit=unit))

    net = unit_price
    if net_factor is not None:
        net *= net_factor
    if discount_factor is not None:
        net *= discount_factor
    cost = (net / pack.base_quantity).quantize(COST_QUANTUM, rounding=ROUND_HALF_UP)

    inputs = cost_inputs(
        position,
        pack_source=pack.source,
        vat_inclusive=net_factor is not None,
        discounted=discount_factor is not None,
        stock_positions=stock_positions,
    )
    leans_on = tuple(sorted(set(inputs) & set(asserted)))
    # A human conversion is an assertion like any other, and it is the one
    # input that never appeared on any invoice at all (WP-55).
    estimated = bool(leans_on) or pack.source is PackSource.OVERRIDE
    return LineCost(
        cost=cost,
        base_unit=pack.base_unit,
        quality=Quality.ESTIMATED if estimated else Quality.RELIABLE,
        asserted=leans_on,
        pack=pack,
    )


def blocked_reason_for(
    *,
    qty: Decimal | None,
    unit_price: Decimal | None,
    pack_size: str | None,
    raw_name: str | None,
    unit: str | None,
    override: str | None = None,
    foreign_currency: bool = False,
) -> Blocked | None:
    """Why this line has no cost, or None when nothing is stopping one.

    The same refusals `cost_line` makes, asked without computing anything -
    *whether* a line can be costed turns only on its price, its quantity and
    its pack, never on the invoice's VAT or discount factors. Both screens ask
    this of a line that came back uncosted, so the reason and the refusal can
    never drift apart.
    """
    if foreign_currency:
        return Blocked.FOREIGN_CURRENCY
    return cost_line(
        position=0,
        qty=qty,
        unit_price=unit_price,
        pack_size=pack_size,
        raw_name=raw_name,
        unit=unit,
        override=override,
    ).blocked


def per_display_unit(cost: Decimal, base_unit: str) -> tuple[Decimal, str]:
    """The same cost in the unit a person buys in: per kilo, per litre, each.

    Two decimals, because it is money on a screen. The exact per-base-unit
    figure stays on the line - this is the display of it, not a second stored
    number.
    """
    label, factor = DISPLAY_UNITS[base_unit]
    return (cost * factor).quantize(DISPLAY_QUANTUM, rounding=ROUND_HALF_UP), label
