"""M6 WP-61: plate cost and margin - deterministic, labelled, naming its inputs.

M6 invents no new numbers. Every price here is M5's derivation read as-is
(the newest costed invoice line among the packs mapped to a material), every
quantity was typed by a named consultant, and the only new arithmetic is
multiplication, one sum, and one division by the batch yield. So a wrong
margin is always a wrong *input* wearing a recipe, and this module's second
job is to say which input: a plate that cannot be costed gets a list of what
is missing, in plain words, and **no cost number at all** - an incomplete
item must never read as a cheap one (D4).

C9 one layer up, mirroring WP-53: the plate's quality is the worst label
among its inputs. Any missing piece makes it *incomplete*; any *estimated*
input makes it *estimated*; otherwise it is *reliable with limitations*.
**No plate ever reads *verified*** - the vocabulary here cannot express it,
and a test pins that even a line claiming otherwise is clamped - because
nothing anywhere corroborates a pack size, and a green badge on a number
four sums deep from the page is the old platform's dominant failure
reappearing where no photo can catch it.

Margin is computed against the selling price **net of VAT**: GCC menu prices
are displayed VAT-inclusive, so a 10.00 karak margins against 9.524, and
margining against the gross would overstate every plate by the VAT rate
(the single commonest costing error in menu work; founder call 2026-08-30).
The rate comes from `VAT_RATE_BY_CURRENCY` keyed by the tenant's own
currency; an unlisted currency margins against the gross and carries a null
rate rather than a guessed one.

Pure module: no I/O, no database. `menu.py` feeds it rows and serializes
what it returns. Nothing here is ever stored - a plate cost derives on every
read, so confirming a cheaper milk invoice moves every karak on the next
screen load with zero writes to any menu table (the WP-54 rule one layer up).
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from .costing import Quality
from .extraction import units

#: A plate cost and a margin are money at fils precision, quantized **once,
#: at the end** (WP-53's rounding rule one layer up): components sum at full
#: precision and only the final figures round.
PLATE_QUANTUM = Decimal("0.001")

#: A margin percentage on a screen: one decimal place, e.g. "64.1".
PCT_QUANTUM = Decimal("0.1")


class PlateQuality(StrEnum):
    """The plate vocabulary: WP-53's two labels plus the one that means "no
    number at all". `verified` is absent on purpose, and `component_quality`
    clamps any input claiming it."""

    RELIABLE = "reliable_with_limitations"
    ESTIMATED = "estimated"
    INCOMPLETE = "incomplete"


#: The missing-piece sentence for an item with no recipe: incomplete by
#: definition (D4) - the empty set must not read as a perfect margin.
NO_RECIPE = "no recipe yet"

#: A version with zero components. The WP-60 door refuses these, so only a
#: row that predates the door can carry one - still incomplete, same rule.
EMPTY_RECIPE = "the recipe has no components"


def component_quality(price_quality: str | None) -> Quality:
    """Clamp a line's stored quality onto the two words a plate may use.

    *Estimated* passes through; everything else - including a hypothetical
    'verified' written by some future bug - reads *reliable with limitations*
    at best, because no arithmetic anywhere supports more."""
    return Quality.ESTIMATED if price_quality == Quality.ESTIMATED.value else Quality.RELIABLE


def to_base_qty(qty: Decimal, unit: str) -> tuple[Decimal, str] | None:
    """A typed quantity in its ingredient's base units: (2, "kg") -> (2000,
    "g"). None when the unit is not a measure or has no base (a container) -
    the WP-60 door refuses those at write time, so this is the defensive
    second ask, not the rule."""
    canonical = units.canonical_unit(unit)
    if canonical is None:
        return None
    base = units.BASE_UNITS.get(units.UNITS[canonical].dimension)
    if base is None:
        return None
    return qty * units.UNITS[canonical].to_base, base


@dataclass(frozen=True)
class Priced:
    """A material's current price, as WP-54 derives it: the newest costed
    line among the packs mapped to it right now.

    `stale` is amendment 3 (D11): the material's newest confirmed *purchase*
    is not this line - it could not be costed - so the figure is real but not
    current, and everything built on it caps at *estimated*."""

    cost_per_base_unit: Decimal
    base_unit: str
    quality: str | None
    stale: bool = False


@dataclass(frozen=True)
class ComponentCost:
    """One component's share of the batch cost, or the plain-words reason
    there is none. Never both."""

    position: int
    cost: Decimal | None = None  # full precision; quantize only at display
    quality: Quality | None = None
    missing: str | None = None


def cost_component(
    *,
    position: int,
    qty: Decimal,
    unit: str,
    ingredient_name: str,
    has_packs: bool,
    price: Priced | None,
    no_price_reason: str | None = None,
) -> ComponentCost:
    """One component costed against its material's current price.

    The missing sentences name the *next action*, not the failure: an
    unmapped material sends the consultant to the mapping screen, an uncosted
    one to the blocked-cost queue (`no_price_reason` carries that queue's own
    WP-55 sentence when the newest purchase is known and blocked)."""
    if price is None:
        if not has_packs:
            return ComponentCost(
                position, missing=f"no supplier product is mapped to {ingredient_name} yet"
            )
        sentence = f"{ingredient_name} has no costed purchase yet"
        if no_price_reason:
            sentence = f"{sentence}: {no_price_reason}"
        return ComponentCost(position, missing=sentence)

    converted = to_base_qty(qty, unit)
    if converted is None or converted[1] != price.base_unit:
        # Unreachable through the WP-60 door; a remap or old data could still
        # produce it, and a wrong-dimension multiplication must never run.
        return ComponentCost(
            position,
            missing=f"'{unit}' does not convert to how {ingredient_name} is measured",
        )
    base_qty, _ = converted
    quality = component_quality(price.quality)
    if price.stale:
        quality = Quality.ESTIMATED
    return ComponentCost(position, cost=base_qty * price.cost_per_base_unit, quality=quality)


def margin_impact(
    delta_per_base_unit: Decimal, base_qty: Decimal, yield_portions: Decimal
) -> Decimal:
    """What one material's price move does to one plate's margin (WP-63): the
    delta times the recipe's quantity in base units, divided by the batch
    yield, quantized once. Positive when the price rose - the margin fell by
    this much - because the sign belongs to the cost, not the feeling."""
    return (delta_per_base_unit * base_qty / yield_portions).quantize(
        PLATE_QUANTUM, rounding=ROUND_HALF_UP
    )


def net_of_vat(price: Decimal, vat_rate: Decimal | None) -> Decimal:
    """What the till keeps of a displayed price: 10.00 at 5%% is 9.524. A
    null rate (unlisted currency) leaves the price as-is - gross, and said so
    by the payload carrying no rate."""
    if vat_rate is None or vat_rate == 0:
        return price.quantize(PLATE_QUANTUM)
    return (price / (1 + vat_rate)).quantize(PLATE_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Plate:
    """The whole answer for one menu item. Incomplete means every number is
    None and `missing` says why, piece by piece - never a cost of zero, which
    would read as the menu's best margin."""

    quality: PlateQuality
    missing: tuple[str, ...] = ()
    cost_per_portion: Decimal | None = None
    net_price: Decimal | None = None
    vat_rate: Decimal | None = None
    margin: Decimal | None = None
    margin_pct: Decimal | None = None


def no_recipe_plate() -> Plate:
    return Plate(quality=PlateQuality.INCOMPLETE, missing=(NO_RECIPE,))


def plate(
    components: list[ComponentCost],
    *,
    yield_portions: Decimal,
    selling_price: Decimal,
    vat_rate: Decimal | None,
) -> Plate:
    """Sum the components, divide once by the batch yield, margin against the
    net price. Quantized once, at the end."""
    if not components:
        return Plate(quality=PlateQuality.INCOMPLETE, missing=(EMPTY_RECIPE,))
    missing = tuple(c.missing for c in components if c.missing is not None)
    if missing:
        return Plate(quality=PlateQuality.INCOMPLETE, missing=missing)

    batch_cost = sum((c.cost for c in components), Decimal(0))
    cost_per_portion = (batch_cost / yield_portions).quantize(PLATE_QUANTUM, rounding=ROUND_HALF_UP)
    net = net_of_vat(selling_price, vat_rate)
    margin = net - cost_per_portion
    margin_pct = (margin / net * 100).quantize(PCT_QUANTUM, rounding=ROUND_HALF_UP)
    quality = (
        PlateQuality.ESTIMATED
        if any(c.quality is Quality.ESTIMATED for c in components)
        else PlateQuality.RELIABLE
    )
    return Plate(
        quality=quality,
        cost_per_portion=cost_per_portion,
        net_price=net,
        vat_rate=vat_rate,
        margin=margin,
        margin_pct=margin_pct,
    )
