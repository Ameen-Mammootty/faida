"""A material's price in force, as one value (2026-09-24 spec 3).

Pure: every input is a row built by hand in the shape the two reads return
(`db.list_mapped_pack_costs`, `db.list_newest_purchases`), so each rule is
pinned without a database. The read itself is exercised by every screen's
own tests, which must come out unchanged.
"""

import datetime
from decimal import Decimal

from faida_api import price_in_force
from faida_api.quality import Quality

MILK = "ing-milk"
TEA = "ing-tea"
WRAP = "ing-wrap"


def _cost(
    ingredient_id: str = MILK,
    *,
    line: str = "line-1",
    purchased_on: datetime.date = datetime.date(2026, 7, 6),
    invoice_date: datetime.date | None = datetime.date(2026, 7, 6),
    confirmed_at: datetime.datetime = datetime.datetime(2026, 7, 7, 9, tzinfo=datetime.UTC),
    cost: str = "0.02020000",
    base_unit: str = "g",
    basis: dict | None = None,
    position: int = 0,
) -> dict:
    return {
        "supplier_item_id": f"pack-{line}",
        "ingredient_id": ingredient_id,
        "canonical_name": "EVAP MILK 410G",
        "catalog_pack_size": "410 g",
        "supplier_name": "Al Madina",
        "invoice_line_id": line,
        "position": position,
        "raw_name": "EVAP MILK 410G",
        "pack_size": "410 g",
        "cost_per_base_unit": Decimal(cost),
        "cost_base_unit": base_unit,
        "cost_basis": {
            "quality": "reliable_with_limitations",
            "asserted": [],
            "pack": "410 g",
            "pack_source": "pack_size",
        }
        if basis is None
        else basis,
        "invoice_id": f"inv-{line}",
        "invoice_date": invoice_date,
        "confirmed_at": confirmed_at,
        "purchased_on": purchased_on,
    }


def _purchase(
    ingredient_id: str = MILK,
    *,
    costed: bool = False,
    purchased_on: datetime.date = datetime.date(2026, 8, 1),
    pack_size: str | None = "1 ctn",
) -> dict:
    return {
        "ingredient_id": ingredient_id,
        "invoice_line_id": "line-blocked",
        "position": 2,
        "raw_name": "EVAP MILK CTN",
        "qty": Decimal("1"),
        "unit": "ctn",
        "pack_size": pack_size,
        "unit_price": Decimal("95.00"),
        "costed": costed,
        "pack_size_override": None,
        "invoice_id": "inv-blocked",
        "invoice_date": purchased_on,
        "currency": "AED",
        "tenant_currency": "AED",
        "purchased_on": purchased_on,
    }


def test_the_first_row_per_material_is_its_price():
    """The read orders each material's newest line first (the date, then the
    confirm time as the tie-break, in SQL); the first row wins and a later
    row for the same material never overwrites it."""
    newest = _cost(line="newest", cost="0.03000000")
    older = _cost(line="older", purchased_on=datetime.date(2026, 6, 1))
    prices = price_in_force.from_rows([newest, older], [])
    price = prices.get(MILK)
    assert price is not None
    assert price.invoice_line_id == "newest"
    assert price.cost_per_base_unit == Decimal("0.03000000")


def test_a_price_carries_its_display_figure_and_its_unit_words():
    prices = price_in_force.from_rows(
        [
            _cost(MILK),
            _cost(TEA, line="tea", cost="0.00468750", base_unit="ml"),
            _cost(WRAP, line="wrap", cost="0.35", base_unit="pc"),
        ],
        [],
    )
    milk, tea, wrap = prices.get(MILK), prices.get(TEA), prices.get(WRAP)
    assert (milk.per_display_unit, milk.display_unit, milk.unit_words) == (
        Decimal("20.20"),
        "kg",
        "per kg",
    )
    assert (tea.per_display_unit, tea.display_unit, tea.unit_words) == (
        Decimal("4.69"),
        "litre",
        "per litre",
    )
    assert (wrap.per_display_unit, wrap.display_unit, wrap.unit_words) == (
        Decimal("0.35"),
        "each",
        "each",
    )


def test_a_reliable_price_has_no_estimated_sentence():
    price = price_in_force.from_rows([_cost()], []).get(MILK)
    assert price.quality is Quality.RELIABLE
    assert price.stale is False
    assert price.newer_uncosted is None
    assert price.why_estimated is None


def test_a_newer_uncosted_purchase_makes_the_price_estimated_and_names_itself():
    prices = price_in_force.from_rows([_cost()], [_purchase(pack_size="1 ctn")])
    price = prices.get(MILK)
    assert price.stale is True
    assert price.quality is Quality.ESTIMATED
    assert price.newer_uncosted.invoice_line_id == "line-blocked"
    assert price.newer_uncosted.purchased_on == datetime.date(2026, 8, 1)
    assert price.newer_uncosted.reason == "Nothing on the invoice says how much one of these holds."
    assert price.why_estimated == (
        "Estimated: a newer delivery on 1 Aug 2026 has no cost yet - "
        "Nothing on the invoice says how much one of these holds."
    )


def test_a_costed_newest_purchase_is_not_stale():
    price = price_in_force.from_rows([_cost()], [_purchase(costed=True)]).get(MILK)
    assert price.stale is False
    assert price.why_estimated is None


def test_a_material_with_only_a_blocked_purchase_has_no_price_but_a_reason():
    prices = price_in_force.from_rows([], [_purchase(WRAP)])
    assert prices.get(WRAP) is None
    assert prices.blocked_reason(WRAP) == (
        "Nothing on the invoice says how much one of these holds."
    )
    assert prices.blocked_reason(MILK) is None


def test_a_blocked_line_costable_today_says_it_was_never_costed():
    """A line confirmed before M5 shipped: nothing blocks it on today's
    inputs, it simply has no cost yet."""
    prices = price_in_force.from_rows([], [_purchase(WRAP, pack_size="410 g")])
    assert prices.blocked_reason(WRAP) == "This purchase has not been costed yet."


def test_a_stored_verified_is_capped():
    """Nothing corroborates a pack size, so no price reads better than
    reliable with limitations - even a row that claims otherwise."""
    basis = {"quality": "verified", "asserted": [], "pack": "410 g", "pack_source": "pack_size"}
    price = price_in_force.from_rows([_cost(basis=basis)], []).get(MILK)
    assert price.quality is Quality.RELIABLE
    assert price.why_estimated is None


def test_a_pack_entered_by_a_person_is_named():
    basis = {"quality": "estimated", "asserted": [], "pack": "25 kg", "pack_source": "override"}
    price = price_in_force.from_rows([_cost(basis=basis)], []).get(MILK)
    assert price.quality is Quality.ESTIMATED
    assert (
        price.why_estimated
        == "Estimated: divided by 25 kg, which someone entered for this product."
    )


def test_fields_supplied_by_a_person_are_named():
    basis = {
        "quality": "estimated",
        "asserted": ["lines.2.unit_price", "total", "tax"],
        "pack": "410 g",
        "pack_source": "pack_size",
    }
    price = price_in_force.from_rows([_cost(basis=basis)], []).get(MILK)
    assert price.why_estimated == (
        "Estimated: leans on line 3's price and the invoice total, and 1 more, "
        "supplied by a person."
    )


def test_staleness_is_named_before_any_other_reason():
    basis = {"quality": "estimated", "asserted": [], "pack": "25 kg", "pack_source": "override"}
    price = price_in_force.from_rows([_cost(basis=basis)], [_purchase()]).get(MILK)
    assert price.why_estimated.startswith("Estimated: a newer delivery on 1 Aug 2026")


def test_an_estimated_price_always_carries_a_reason():
    """The invariant the screens lean on: the estimated word never travels
    without its sentence, even for a basis that recorded no cause."""
    basis = {"quality": "estimated", "asserted": [], "pack": "410 g", "pack_source": "pack_size"}
    price = price_in_force.from_rows([_cost(basis=basis)], []).get(MILK)
    assert price.quality is Quality.ESTIMATED
    assert price.why_estimated == "Estimated: one of its inputs was supplied by a person."


def test_describe_fields_matches_the_screens_words():
    """A port of the web's `describeFields`: line numbers 1-based, two named
    and the rest counted."""
    assert price_in_force.describe_fields(["total"]) == "the invoice total"
    assert price_in_force.describe_fields(["lines.0.qty"]) == "line 1's quantity"
    assert price_in_force.describe_fields(["total", "lines.4.pack_size"]) == (
        "the invoice total and line 5's pack size"
    )
    assert price_in_force.describe_fields(["unknown_field"]) == "unknown_field"


def test_the_prices_iterate_in_read_order():
    prices = price_in_force.from_rows([_cost(MILK), _cost(TEA, line="tea")], [])
    assert [ingredient_id for ingredient_id, _ in prices.items()] == [MILK, TEA]
    assert MILK in prices
    assert WRAP not in prices
