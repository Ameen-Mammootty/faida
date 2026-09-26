"""A material's price in force, as one value (2026-09-24 spec 3).

Every material has one price at any moment: the newest delivery we could
cost (M5 WP-54 - latest, not cheapest and not averaged, by printed invoice
date). If a newer delivery arrived that could not be costed, the old price
still shows but reads *estimated*, and the price says why (WP-61 amendment
3, D11). Before this module that rule was worked out twice and raw database
rows were unpacked in four more places, and the web wrote the "estimated
because" sentence three times, three ways; now it is worked out here, once,
and every screen prints the sentence this module writes.

Invariants, pinned by `tests/test_price_in_force.py`:
- the quality is only ever reliable with limitations or estimated - nothing
  corroborates a pack size, so even a stored "verified" is capped;
- stale implies estimated;
- `why_estimated` is present exactly when the quality is estimated;
- a return line never wins (the reads filter it, `db.list_mapped_pack_costs`);
- `read(as_of=None)` is `read()`.

Pure apart from `read`, which makes the two reads and calls `from_rows`, the
test seam. The SQL stays in `db.py`; the rule "two reads, one date limit,
joined this way" lives here. Nothing is stored: the price derives on every
read, so unmapping a wrong merge corrects every figure above it.
"""

import datetime
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from . import costing, wire, words
from .extraction.currency import currency_differs
from .quality import Quality

#: A C8 field path's plain words, for the sentence naming what a person
#: supplied (ported from the web's `describeField`, which it replaces).
FIELD_WORDS: dict[str, str] = {
    "supplier_name": "the supplier name",
    "invoice_no": "the invoice number",
    "invoice_date": "the invoice date",
    "currency": "the currency",
    "payment_kind": "the payment terms",
    "subtotal": "the subtotal",
    "tax": "the VAT",
    "total": "the invoice total",
    "discount_total": "the discount",
    "rounding_amount": "the rounding",
    "qty": "quantity",
    "unit": "unit",
    "unit_price": "price",
    "line_total": "total",
    "pack_size": "pack size",
    "raw_name": "name",
}

#: The estimated word with no recorded cause. `costing.cost_line` never
#: stores one - an estimated cost always has an override or an asserted
#: field - but the word must never travel without a sentence.
SUPPLIED_BY_A_PERSON = "Estimated: one of its inputs was supplied by a person."

#: A confirmed purchase that nothing blocks on today's inputs and still has
#: no cost: only a line confirmed before M5 shipped. The next confirm of that
#: product fixes it.
NOT_COSTED_YET = "This purchase has not been costed yet."


def describe_field(path: str) -> str:
    """ "total" is "the invoice total"; "lines.2.unit_price" is "line 3's
    price" - 1-based for a person, 0-based on the wire."""
    parts = path.split(".")
    if len(parts) == 3 and parts[0] == "lines":
        return f"line {int(parts[1]) + 1}'s {FIELD_WORDS.get(parts[2], parts[2])}"
    return FIELD_WORDS.get(path, path)


def describe_fields(paths: Sequence[str]) -> str:
    """ "the invoice total", "the invoice total and line 3's price", and
    ", and 2 more" past two."""
    named = [describe_field(path) for path in paths[:2]]
    rest = len(paths) - len(named)
    listed = f"{named[0]} and {named[1]}" if len(named) == 2 else named[0]
    return f"{listed}, and {rest} more" if rest > 0 else listed


def capped(stored: str | None) -> Quality:
    """A stored cost quality onto the two words a price may use: estimated
    passes through, anything else - a hypothetical 'verified' included - is
    reliable with limitations at best."""
    return Quality.ESTIMATED if stored == Quality.ESTIMATED.value else Quality.RELIABLE


@dataclass(frozen=True)
class NewerUncosted:
    """The material's newest confirmed purchase, which could not be costed:
    which line, on which invoice, bought when, and the WP-55 reason."""

    invoice_line_id: str
    invoice_id: str
    position: int
    raw_name: str | None
    purchased_on: datetime.date | None
    reason: str


def why_estimated(
    quality: Quality,
    *,
    pack: str | None,
    pack_source: str | None,
    asserted: Sequence[str],
    newer_uncosted: NewerUncosted | None = None,
) -> str | None:
    """Why a price reads estimated, in the one set of words every screen
    prints, or None when it does not. Checked in order: a newer delivery with
    no cost, a pack a person entered, fields a person supplied."""
    if quality is not Quality.ESTIMATED:
        return None
    if newer_uncosted is not None:
        when = newer_uncosted.purchased_on
        on = "" if when is None else f" on {words.long_date(when)}"
        return f"Estimated: a newer delivery{on} has no cost yet - {newer_uncosted.reason}"
    if pack_source == costing.PackSource.OVERRIDE.value:
        return f"Estimated: divided by {pack}, which someone entered for this product."
    if asserted:
        return f"Estimated: leans on {describe_fields(asserted)}, supplied by a person."
    return SUPPLIED_BY_A_PERSON


@dataclass(frozen=True)
class PriceInForce:
    """One material's price: the figure per base unit and per the unit a
    person buys in, how much to trust it and why not more, and the invoice
    line it came from, down to the photo."""

    ingredient_id: str
    cost_per_base_unit: Decimal
    base_unit: str
    per_display_unit: Decimal
    display_unit: str
    unit_words: str
    quality: Quality
    pack: str | None
    pack_source: str | None
    asserted: tuple[str, ...]
    supplier_name: str
    supplier_item_id: str
    product_name: str
    invoice_id: str
    invoice_line_id: str
    position: int
    purchased_on: datetime.date | None
    invoice_date: datetime.date | None
    newer_uncosted: NewerUncosted | None
    why_estimated: str | None

    @property
    def stale(self) -> bool:
        """The newest purchase is not this line - it could not be costed."""
        return self.newer_uncosted is not None


def blocked_line_reason(line: Mapping) -> str:
    """Why a confirmed purchase line has no cost, in the WP-55 sentence the
    blocked-cost queue uses - one vocabulary, wherever the line surfaces."""
    blocked = costing.blocked_reason_for(
        qty=line["qty"],
        unit_price=line["unit_price"],
        pack_size=line["pack_size"],
        raw_name=line["raw_name"],
        unit=line["unit"],
        override=line["pack_size_override"],
        foreign_currency=currency_differs(line["currency"], line["tenant_currency"]),
    )
    return NOT_COSTED_YET if blocked is None else costing.BLOCKED_REASONS[blocked]


def _newer_uncosted(line: Mapping) -> NewerUncosted:
    return NewerUncosted(
        invoice_line_id=line["invoice_line_id"],
        invoice_id=line["invoice_id"],
        position=line["position"],
        raw_name=line["raw_name"],
        purchased_on=line["purchased_on"],
        reason=blocked_line_reason(line),
    )


def price_of(row: Mapping, newer_uncosted: NewerUncosted | None = None) -> PriceInForce:
    """One costed line (a `db.list_mapped_pack_costs` row) as a price. The
    material's price is its first row; a pack's own newest line, shown beside
    the other packs on the materials screen, is one of these too."""
    basis = row["cost_basis"] or {}
    base_unit = row["cost_base_unit"]
    per_display, display_unit = costing.per_display_unit(row["cost_per_base_unit"], base_unit)
    quality = Quality.ESTIMATED if newer_uncosted is not None else capped(basis.get("quality"))
    asserted = tuple(basis.get("asserted", []))
    return PriceInForce(
        ingredient_id=row["ingredient_id"],
        cost_per_base_unit=row["cost_per_base_unit"],
        base_unit=base_unit,
        per_display_unit=per_display,
        display_unit=display_unit,
        unit_words=words.per_unit(display_unit),
        quality=quality,
        pack=basis.get("pack"),
        pack_source=basis.get("pack_source"),
        asserted=asserted,
        supplier_name=row["supplier_name"],
        supplier_item_id=row["supplier_item_id"],
        product_name=row["canonical_name"],
        invoice_id=row["invoice_id"],
        invoice_line_id=row["invoice_line_id"],
        position=row["position"],
        purchased_on=row["purchased_on"],
        invoice_date=row["invoice_date"],
        newer_uncosted=newer_uncosted,
        why_estimated=why_estimated(
            quality,
            pack=basis.get("pack"),
            pack_source=basis.get("pack_source"),
            asserted=asserted,
            newer_uncosted=newer_uncosted,
        ),
    )


class PricesInForce(Mapping[str, PriceInForce]):
    """Every material's price in force, by material id, in the read's order,
    and the reason a material with no price at all has none when its newest
    purchase is known and blocked. A read-only mapping, so a pure module can
    take a plain dict of prices in its tests."""

    def __init__(self, prices: dict[str, PriceInForce], blocked: dict[str, str]) -> None:
        self._prices = prices
        self._blocked = blocked

    def __getitem__(self, ingredient_id: str) -> PriceInForce:
        return self._prices[ingredient_id]

    def __iter__(self) -> Iterator[str]:
        return iter(self._prices)

    def __len__(self) -> int:
        return len(self._prices)

    def blocked_reason(self, ingredient_id: str) -> str | None:
        """The WP-55 reason the newest purchase of a material with **no**
        price could not be costed, or None."""
        if ingredient_id in self._prices:
            return None
        return self._blocked.get(ingredient_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PricesInForce):
            return NotImplemented
        return self._prices == other._prices and self._blocked == other._blocked

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return f"PricesInForce({len(self._prices)} prices, {len(self._blocked)} blocked)"


def from_rows(costs: Sequence[Mapping], newest_purchases: Sequence[Mapping]) -> PricesInForce:
    """The prices from the two reads' rows: the first costed row per material
    (the read orders the newest first), and the newest purchase per material,
    which makes the price stale when it could not be costed."""
    uncosted = {line["ingredient_id"]: line for line in newest_purchases if not line["costed"]}
    prices: dict[str, PriceInForce] = {}
    for row in costs:
        ingredient_id = row["ingredient_id"]
        if ingredient_id in prices:
            continue
        stale = uncosted.get(ingredient_id)
        prices[ingredient_id] = price_of(row, None if stale is None else _newer_uncosted(stale))
    blocked = {
        ingredient_id: blocked_line_reason(line)
        for ingredient_id, line in uncosted.items()
        if ingredient_id not in prices
    }
    return PricesInForce(prices, blocked)


def payload(price: PriceInForce | None) -> dict | None:
    """A material's price in force, serialized (WP-54, spec 3): the figure,
    how much to trust it and the sentence saying why not more, and the
    purchase it came from.

    Not a stored number: it is the newest costed line among the packs mapped
    to this material **right now**, so unmapping a wrong merge corrects it with
    nothing to rebuild. It carries the invoice line it came from rather than a
    summary-table row, which is what lets the screen put the photo one click
    away from the figure. `newer_uncosted` names the delivery that made it
    stale (D11); `why_estimated` and `unit_words` are the words every screen
    prints, so no screen composes its own. None for a material with no price."""
    if price is None:
        return None
    newer = price.newer_uncosted
    return {
        "per_base_unit": wire.dec(price.cost_per_base_unit),
        "base_unit": price.base_unit,
        "per_display_unit": wire.dec(price.per_display_unit),
        "display_unit": price.display_unit,
        "unit_words": price.unit_words,
        "quality": price.quality.value,
        "asserted": list(price.asserted),
        "pack": price.pack,
        "pack_source": price.pack_source,
        "why_estimated": price.why_estimated,
        "supplier_name": price.supplier_name,
        "supplier_item_id": price.supplier_item_id,
        "product_name": price.product_name,
        "invoice_id": price.invoice_id,
        "invoice_line_id": price.invoice_line_id,
        # The printed line position, for the /invoices/<id>#line-<position>
        # anchor contract (design review): the drill lands on the row itself.
        "position": price.position,
        # The date we ranked by, and separately whether the invoice printed one:
        # "bought on 6 July" and "recorded on 29 August" are different claims.
        "purchased_on": wire.iso(price.purchased_on),
        "invoice_date": wire.iso(price.invoice_date),
        "newer_uncosted": None
        if newer is None
        else {
            "invoice_line_id": newer.invoice_line_id,
            "invoice_id": newer.invoice_id,
            "position": newer.position,
            "raw_name": newer.raw_name,
            "purchased_on": wire.iso(newer.purchased_on),
            "reason": newer.reason,
        },
    }


async def read(db, tenant_id: str, *, as_of: datetime.date | None = None) -> PricesInForce:
    """Every material's price in force for one tenant, today or on a date.

    `as_of` is M9 C12.4: the price in force **on a date**, so a period figure
    stops moving when an unrelated paper lands after the period it covers;
    both reads take the same limit, so a blocked purchase printed after the
    date cannot make the period's price stale either."""
    costs = await db.list_mapped_pack_costs(tenant_id=tenant_id, as_of=as_of)
    newest = await db.list_newest_purchases(tenant_id=tenant_id, as_of=as_of)
    return from_rows(costs, newest)
