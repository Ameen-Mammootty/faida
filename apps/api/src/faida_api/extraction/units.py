"""Units and pack sizes: one dictionary, one way to compare (plan.md §5 layer 4).

Suppliers write the same pack a dozen ways. "2 kg", "2KG", "2000 g", "2.5K" on
a receipt too narrow for the second letter, "12 pcs", Arabic "كجم". Every one
of them has to land on the same shelf, because two things downstream depend on
it and both are money:

- **Item snapping.** "Tahina 2kg" and "Tahina 2000g" are one catalog item. Read
  as two, the catalog doubles, price history splits in half, and the price
  alert that is the demo's money moment fires on a supplier who changed nothing
  but their printing.
- **Price comparability.** A pack size that reads differently month to month
  makes a flat price look like a move, which is the same failure the net-canonical
  price memory decision (C4) exists to prevent.

So a pack size is parsed into a magnitude and a canonical unit, then reduced to
a base quantity in that unit's dimension: grams for mass, millilitres for
volume, pieces for count. Comparison happens on the base quantity, never on the
printed string.

Containers are deliberately their own dimension. A carton is not twelve of
anything until someone says what is in it, so "6 ctn" and "6 pc" must never
compare equal - guessing there would silently merge two real catalog items.

**Multiplier packs** (WP-51). GCC food supply prints cartons as "48x400ml":
forty-eight 400 ml tins, not a 400 ml tin. Reading only the tail is not a small
error - it is the whole carton divided by one of its parts, so a cost per base
unit built on it is 48x too high, and nothing downstream of M5 can see that.
The multiplier is arithmetic printed on the page, so it is read; what is inside
an unlabelled carton is not, so it is refused (that is the human's sentence to
say, M5 WP-55). A *nested* chain like "2x3x4kg" is refused outright rather than
read as one of its halves - the halves are both wrong numbers.

A quantity of zero is not a pack. `parse("0kg")` used to return a real pack
whose base quantity was 0, which divides.

This lived privately inside matching.py until WP-16, where the eval needed the
same answers and there was no way to ask for them without a second copy.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum


class Dimension(StrEnum):
    MASS = "mass"  # base: gram
    VOLUME = "volume"  # base: millilitre
    COUNT = "count"  # base: piece
    PACKAGING = "packaging"  # a container, comparable only to its own kind


@dataclass(frozen=True)
class Unit:
    canonical: str
    dimension: Dimension
    to_base: Decimal  # multiply a quantity by this to reach the dimension's base


def _u(canonical: str, dimension: Dimension, to_base: str = "1") -> Unit:
    return Unit(canonical, dimension, Decimal(to_base))


# The canonical units. Anything not here is not a unit we claim to understand,
# and an unparseable pack size is left alone rather than guessed at.
UNITS: dict[str, Unit] = {
    "kg": _u("kg", Dimension.MASS, "1000"),
    "g": _u("g", Dimension.MASS, "1"),
    "mg": _u("mg", Dimension.MASS, "0.001"),
    "lb": _u("lb", Dimension.MASS, "453.59237"),
    "oz": _u("oz", Dimension.MASS, "28.349523125"),
    "l": _u("l", Dimension.VOLUME, "1000"),
    "ml": _u("ml", Dimension.VOLUME, "1"),
    "cl": _u("cl", Dimension.VOLUME, "10"),
    "gal": _u("gal", Dimension.VOLUME, "3785.411784"),  # US gallon
    "pc": _u("pc", Dimension.COUNT, "1"),
    "dz": _u("dz", Dimension.COUNT, "12"),
    # Containers: each compares only with itself (see the module docstring).
    "ctn": _u("ctn", Dimension.PACKAGING),
    "pkt": _u("pkt", Dimension.PACKAGING),
    "box": _u("box", Dimension.PACKAGING),
    "bag": _u("bag", Dimension.PACKAGING),
    "can": _u("can", Dimension.PACKAGING),
    "tin": _u("tin", Dimension.PACKAGING),
    "tub": _u("tub", Dimension.PACKAGING),
    "jar": _u("jar", Dimension.PACKAGING),
    "btl": _u("btl", Dimension.PACKAGING),
    "case": _u("case", Dimension.PACKAGING),
    "tray": _u("tray", Dimension.PACKAGING),
    "sachet": _u("sachet", Dimension.PACKAGING),
    "roll": _u("roll", Dimension.PACKAGING),
    "bunch": _u("bunch", Dimension.PACKAGING),
    "block": _u("block", Dimension.PACKAGING),
    "loaf": _u("loaf", Dimension.PACKAGING),
    "pack": _u("pack", Dimension.PACKAGING),
    "bundle": _u("bundle", Dimension.PACKAGING),
    "service": _u("service", Dimension.PACKAGING),  # a charge line's "unit"
}

# Every spelling we have seen or expect, mapped to a canonical unit. Arabic is
# here because GCC invoices are mixed-script (plan.md §3) and an Arabic-only
# delivery note is a normal Tuesday, not an edge case.
ALIASES: dict[str, str] = {
    # mass
    "kgs": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "kilogramme": "kg",
    "kgm": "kg",
    # A thermal receipt truncates "5KG" to "5K" when the column runs out; in a
    # food supplier's paperwork a bare K after a number is kilograms, never
    # thousands. TH-01 prints exactly this ("TOM CRUSH 2.5K").
    "k": "kg",
    "gm": "g",
    "gms": "g",
    "gs": "g",
    "gr": "g",
    "gram": "g",
    "grams": "g",
    "gramme": "g",
    "grms": "g",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "ozs": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "كجم": "kg",
    "كغم": "kg",
    "كيلو": "kg",
    "كيلوجرام": "kg",
    "جم": "g",
    "جرام": "g",
    "غرام": "g",
    # volume
    "ltr": "l",
    "ltrs": "l",
    "litre": "l",
    "litres": "l",
    "liter": "l",
    "liters": "l",
    "lt": "l",
    "lts": "l",
    "mls": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "cc": "ml",
    "gallon": "gal",
    "gallons": "gal",
    "gals": "gal",
    "لتر": "l",
    "لترات": "l",
    "مل": "ml",
    # count
    "pcs": "pc",
    "pce": "pc",
    "pces": "pc",
    "piece": "pc",
    "pieces": "pc",
    "nos": "pc",
    "no": "pc",
    "each": "pc",
    "ea": "pc",
    "unit": "pc",
    "units": "pc",
    "dzn": "dz",
    "doz": "dz",
    "dozen": "dz",
    "dozens": "dz",
    "حبة": "pc",
    "حبات": "pc",
    "قطعة": "pc",
    "درزن": "dz",
    # containers
    "ctns": "ctn",
    "carton": "ctn",
    "cartons": "ctn",
    "pkts": "pkt",
    "packet": "pkt",
    "packets": "pkt",
    "boxes": "box",
    "bags": "bag",
    "cans": "can",
    "tins": "tin",
    "tubs": "tub",
    "jars": "jar",
    "bottle": "btl",
    "bottles": "btl",
    "btls": "btl",
    "cases": "case",
    "trays": "tray",
    "sachets": "sachet",
    "rolls": "roll",
    "bunches": "bunch",
    "blocks": "block",
    "loaves": "loaf",
    "loafs": "loaf",
    "packs": "pack",
    "bundles": "bundle",
    "علبة": "box",
    "علب": "box",
    "كيس": "bag",
    "أكياس": "bag",
    "صندوق": "ctn",
    "كرتون": "ctn",
    "زجاجة": "btl",
}


def canonical_unit(word: str | None) -> str | None:
    """The canonical name for a printed unit word, or None if we do not claim
    to know it. "cartons" -> "ctn", "KGS" -> "kg", "كجم" -> "kg"."""
    if not word:
        return None
    key = " ".join(word.split()).casefold().strip(".")
    if key in UNITS:
        return key
    return ALIASES.get(key)


def _unit_pattern() -> str:
    """Longest spelling first, so "kgs" never matches as "kg" with a stray s
    and "kilogram" never matches as "k"."""
    words = sorted(set(UNITS) | set(ALIASES), key=len, reverse=True)
    return "|".join(re.escape(w) for w in words)


# The symbols a supplier uses between a count and the pack it repeats:
# "48x400ml", "24 X 1L", "12*500g", "6×2kg". IGNORECASE covers the capital X.
_MULTIPLIER_CHARS = "xX*×"

# A number glued or spaced to a unit: "2.5kg", "50 KG", "30PCS", "2 كجم",
# optionally preceded by a multiplier: "48x400ml".
# Commas inside numbers are stripped before matching (see _quantity).
_PACK_RE = re.compile(
    rf"(?:(\d+(?:[.,]\d+)?)\s*[{_MULTIPLIER_CHARS}]\s*)?"
    rf"(\d+(?:[.,]\d+)?)\s*({_unit_pattern()})(?![\w])",
    re.IGNORECASE,
)


def _quantity(text: str) -> Decimal | None:
    """A printed magnitude, or None when it is not one we can divide by. Zero
    and below are refused here rather than downstream: a pack of nothing is not
    a pack, and the first thing M5 does with a pack size is divide by it."""
    try:
        value = Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None
    return value if value > 0 else None


def _is_nested(text: str, start: int) -> bool:
    """Is the pack we matched the tail of a longer multiplier chain?

    "2x3x4kg" matches as "3x4kg" from index 2, which would read 12 kg where the
    page says 24. Both halves are wrong numbers, so a chain is refused entirely
    rather than half-read - the same rule that keeps a carton's contents a
    human's sentence rather than a guess.
    """
    index = start - 1
    while index >= 0 and text[index].isspace():
        index -= 1
    return index >= 0 and text[index] in _MULTIPLIER_CHARS


@dataclass(frozen=True)
class PackSize:
    """A printed pack size, harmonized. `key` is what comparison uses: two pack
    sizes are the same pack when their keys match, whatever they printed."""

    quantity: Decimal
    unit: Unit

    @property
    def base_quantity(self) -> Decimal:
        return self.quantity * self.unit.to_base

    @property
    def key(self) -> tuple[str, str, Decimal]:
        # Containers keep their own name; measures collapse onto their base, so
        # 2 kg and 2000 g share a key and 6 ctn and 6 pc never do.
        name = self.unit.canonical if self.unit.dimension is Dimension.PACKAGING else ""
        return (self.unit.dimension.value, name, self.base_quantity)

    def __str__(self) -> str:
        quantity = self.quantity.normalize()
        return f"{quantity:f} {self.unit.canonical}"


def _pack_from(text: str, match: re.Match[str]) -> PackSize | None:
    """One regex hit turned into a pack, or None when it is not one we claim to
    understand: a nested multiplier chain, a zero quantity, or a unit word that
    is not in the dictionary."""
    if _is_nested(text, match.start()):
        return None
    quantity = _quantity(match.group(2))
    canonical = canonical_unit(match.group(3))
    if quantity is None or canonical is None:
        return None
    if match.group(1) is not None:
        multiplier = _quantity(match.group(1))
        if multiplier is None:
            return None
        quantity *= multiplier
    return PackSize(quantity, UNITS[canonical])


def parse(text: str | None) -> PackSize | None:
    """One pack size from a printed cell: "2 kg", "2.5K", "12 pcs",
    "48x400ml". None when the cell names no unit we know - an unknown pack size
    stays unknown rather than becoming a wrong one."""
    if not text:
        return None
    for match in _PACK_RE.finditer(text):
        pack = _pack_from(text, match)
        if pack is not None:
            return pack
    return None


def find_all(text: str | None) -> set[PackSize]:
    """Every pack size named anywhere in a string, for item names that carry
    theirs inline ("MILK PWDR 2.5KG NIDO")."""
    if not text:
        return set()
    found: set[PackSize] = set()
    for match in _PACK_RE.finditer(text):
        pack = _pack_from(text, match)
        if pack is not None:
            found.add(pack)
    return found


def first_printed(text: str | None) -> str | None:
    """The first pack size in a string, exactly as it was printed there:
    "RICE BASM 5KG" -> "5KG", "EVAP MILK 48x400ML" -> "48x400ML". A till
    receipt has no pack-size column and puts the pack in the item name instead,
    and the catalog already reads it there (matching.snap_item scans
    canonical_name), so it is a pack size wherever it is printed."""
    if not text:
        return None
    for match in _PACK_RE.finditer(text):
        if _pack_from(text, match) is not None:
            return match.group(0).strip()
    return None


def same_pack_size(left: str | None, right: str | None) -> bool:
    """Do two printed pack sizes describe the same pack? Unparseable on either
    side falls back to a normalized string comparison, so an unknown unit is
    still matched against itself."""
    left_pack, right_pack = parse(left), parse(right)
    if left_pack is not None and right_pack is not None:
        return left_pack.key == right_pack.key
    if left_pack is None and right_pack is None:
        return (
            " ".join((left or "").split()).casefold() == " ".join((right or "").split()).casefold()
        )
    return False
