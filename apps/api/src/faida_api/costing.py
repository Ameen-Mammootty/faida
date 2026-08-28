"""Cost per base unit: what a raw material actually costs per gram (M5).

Price memory records what a supplier charges for one *purchase unit* exactly as
that unit was printed - AED 50.50 for a carton, AED 12.00 for a kilo, AED 4.25
for a tray. A recipe asks a different question: what does 180 g of milk powder
cost. Between the two sits one division, and getting it wrong is silent, so the
rules are written down here and nowhere else.

The reading order, most specific first:

1. **A human-stated conversion wins.** "1 carton = 10 kg chicken" is knowledge
   no dictionary has (`supplier_item_conversions`).
2. **A measure in the unit column means the price is per that measure.**
   `unit` 'kg' at 12.00 is 0.012 per gram. The pack size, if any, is
   descriptive and must not divide anything.
3. **Otherwise the price is per pack**, and the pack size says how big a pack
   is: 'ctn' of '2.5kg' at 50.50 is 0.0202 per gram.
4. **A pack size printed inside the item name counts** ("RICE BASM 5KG"), the
   same rule `matching.snap_item` already applies - a till receipt has no
   pack-size column and puts the pack in the name.
5. **Anything else is blocked, never guessed.** A price per carton with no
   stated contents has no cost per kilo, and inventing one would quietly move
   the cost of every menu item using it. Blocked items are work on a screen
   (PRD §24), each naming what it needs.

Two containers never cancel: an item priced per carton whose pack size is also
a container ('1 box') stays blocked, because `units.py` keeps containers in
their own dimension for exactly this reason.

Everything here is `Decimal` (C4). Division is the one place money math grows
digits without limit, so results are quantized to COST_QUANTUM - fine enough
that a spice at fractions of a fil per gram survives, and fixed so the same
inputs always produce the same cost.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from .extraction import units

# Cost per base unit is a small number by construction: AED per gram, per
# millilitre, per piece. Eight places keeps saffron at ~0.00000012 AED/g
# meaningful while staying exact under Decimal.
COST_QUANTUM = Decimal("0.00000001")


class Blocked(StrEnum):
    """Why an item has no cost per base unit. Each is a different sentence on
    the screen and a different fix, so they are not collapsed into one."""

    NO_PRICE = "no_price"  # never bought, or bought at no readable price
    UNKNOWN_PACK = "unknown_pack"  # priced per container; needs a conversion
    AMBIGUOUS_PACK = "ambiguous_pack"  # the name names two packs; needs a human


@dataclass(frozen=True)
class UnitCost:
    """A price reduced to one base unit, plus how we got there. `basis` is
    shown to the user: a cost derived from a human's conversion and a cost
    derived from a printed pack size are both correct and are not the same
    claim."""

    per_base: Decimal
    base_unit: str  # 'g' | 'ml' | 'pc'
    basis: str  # 'conversion' | 'unit' | 'pack_size' | 'item_name'
    pack_display: str  # "2.5 kg", "1 kg", "10 kg (stated)" - for the screen


@dataclass(frozen=True)
class Conversion:
    """A human's statement of what one purchase unit contains."""

    base_quantity: Decimal
    base_unit: str


def base_unit_for(unit: units.Unit) -> str | None:
    """The base unit a measure reduces to; None for containers, which reduce
    to nothing until someone states their contents."""
    return {
        units.Dimension.MASS: "g",
        units.Dimension.VOLUME: "ml",
        units.Dimension.COUNT: "pc",
    }.get(unit.dimension)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(COST_QUANTUM, rounding=ROUND_HALF_UP)


def _measure_packs(text: str | None) -> list[units.PackSize]:
    """Distinct measurable packs named in a string, containers excluded."""
    seen: dict[tuple[str, str, Decimal], units.PackSize] = {}
    for pack in units.find_all(text):
        if base_unit_for(pack.unit) is not None:
            seen.setdefault(pack.key, pack)
    return list(seen.values())


def unit_cost(
    price: Decimal | None,
    *,
    unit: str | None = None,
    pack_size: str | None = None,
    item_name: str | None = None,
    conversion: Conversion | None = None,
) -> UnitCost | Blocked:
    """The cost of one base unit at `price` per purchase unit, or the reason
    there isn't one. `price` is the ex-VAT unit price price memory already
    stores (C4 net-canonical), so the answer is ex-VAT too."""
    if price is None or price <= 0:
        return Blocked.NO_PRICE

    if conversion is not None:
        stated = units.PackSize(conversion.base_quantity, units.UNITS[conversion.base_unit])
        return UnitCost(
            per_base=_quantize(price / conversion.base_quantity),
            base_unit=conversion.base_unit,
            basis="conversion",
            pack_display=f"{stated} (stated)",
        )

    canonical = units.canonical_unit(unit)
    if canonical is not None:
        printed = units.UNITS[canonical]
        base = base_unit_for(printed)
        if base is not None:
            # Priced per kg / per litre / per piece: one purchase unit IS one
            # printed unit, so the pack size describes the goods and divides
            # nothing.
            return UnitCost(
                per_base=_quantize(price / printed.to_base),
                base_unit=base,
                basis="unit",
                pack_display=f"1 {printed.canonical}",
            )

    for source, basis in ((pack_size, "pack_size"), (item_name, "item_name")):
        packs = _measure_packs(source)
        if len(packs) > 1:
            return Blocked.AMBIGUOUS_PACK
        if len(packs) == 1:
            pack = packs[0]
            base = base_unit_for(pack.unit)
            assert base is not None  # _measure_packs filtered containers out
            return UnitCost(
                per_base=_quantize(price / pack.base_quantity),
                base_unit=base,
                basis=basis,
                pack_display=str(pack),
            )

    return Blocked.UNKNOWN_PACK
