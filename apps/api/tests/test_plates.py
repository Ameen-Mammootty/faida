"""M6 WP-61: plate cost and margin - deterministic, labelled, naming its inputs.

The rule under test: **M6 invents no new numbers.** Every price is M5's
derivation read as-is, every quantity was typed by a consultant, and the only
new arithmetic is multiplication, one sum, and one division by the batch
yield - so the karak below is checked by hand, to the fils. The rest is C9
one layer up: an item missing anything reads *incomplete* with no number at
all, one *estimated* input makes the plate *estimated*, a material whose
newest purchase could not be costed is flagged instead of silently showing
an old price (D11), and **no plate ever reads *verified*** - pinned here by
feeding the maths a line that claims it.
"""

import datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from faida_api import plates
from faida_api.api import router as api_router
from faida_api.costing import Quality
from faida_api.menu import router as menu_router

from .conftest import AUTH, DEMO_TENANT_ID, requires_db, wire_auth

# -- the pure module (no DB) ---------------------------------------------------


def test_a_ten_dirham_menu_price_margins_against_9_524():
    """GCC menu prices are VAT-inclusive: the 5%% belongs to the FTA, so the
    margin base is 9.524, not 10.00 - the alternative overstates every plate
    by the VAT rate."""
    assert plates.net_of_vat(Decimal("10.00"), Decimal("0.05")) == Decimal("9.524")
    # An unlisted currency margins against the gross rather than a guessed rate.
    assert plates.net_of_vat(Decimal("10.00"), None) == Decimal("10.000")
    assert plates.net_of_vat(Decimal("10.00"), Decimal("0")) == Decimal("10.000")


def test_quantities_convert_to_base_units_and_vessels_do_not():
    assert plates.to_base_qty(Decimal("2"), "kg") == (Decimal("2000"), "g")
    assert plates.to_base_qty(Decimal("55"), "ml") == (Decimal("55"), "ml")
    assert plates.to_base_qty(Decimal("1"), "pc") == (Decimal("1"), "pc")
    assert plates.to_base_qty(Decimal("2"), "cups") is None  # a serving vessel
    assert plates.to_base_qty(Decimal("1"), "ctn") is None  # a container


def test_no_plate_vocabulary_can_say_verified():
    """The pin (WP-53's rule one layer up): even a line whose stored quality
    claimed 'verified' - which no write path produces - reads *reliable with
    limitations* at best, because nothing corroborates a pack size."""
    assert "verified" not in [q.value for q in plates.PlateQuality]
    assert plates.component_quality("verified") is Quality.RELIABLE
    assert plates.component_quality(None) is Quality.RELIABLE
    assert plates.component_quality("estimated") is Quality.ESTIMATED


def test_plate_arithmetic_by_hand_quantized_once():
    components = [
        plates.ComponentCost(0, cost=Decimal("0.072"), quality=Quality.RELIABLE),
        plates.ComponentCost(1, cost=Decimal("0.48"), quality=Quality.RELIABLE),
        plates.ComponentCost(2, cost=Decimal("0.2"), quality=Quality.RELIABLE),
    ]
    result = plates.plate(
        components,
        yield_portions=Decimal("1"),
        selling_price=Decimal("10.00"),
        vat_rate=Decimal("0.05"),
    )
    assert result.quality is plates.PlateQuality.RELIABLE
    assert result.cost_per_portion == Decimal("0.752")
    assert result.net_price == Decimal("9.524")
    assert result.margin == Decimal("8.772")
    assert result.margin_pct == Decimal("92.1")


def test_one_estimated_component_makes_the_plate_estimated():
    components = [
        plates.ComponentCost(0, cost=Decimal("1"), quality=Quality.RELIABLE),
        plates.ComponentCost(1, cost=Decimal("1"), quality=Quality.ESTIMATED),
    ]
    result = plates.plate(
        components,
        yield_portions=Decimal("1"),
        selling_price=Decimal("10.00"),
        vat_rate=Decimal("0.05"),
    )
    assert result.quality is plates.PlateQuality.ESTIMATED


def test_a_missing_component_means_no_numbers_at_all():
    """D4: an incomplete item must never read as a cheap one - so it has no
    cost, no margin, nothing to rank by, only its list of what is missing."""
    components = [
        plates.ComponentCost(0, cost=Decimal("1"), quality=Quality.RELIABLE),
        plates.ComponentCost(1, missing="no supplier product is mapped to Saffron yet"),
    ]
    result = plates.plate(
        components,
        yield_portions=Decimal("1"),
        selling_price=Decimal("10.00"),
        vat_rate=Decimal("0.05"),
    )
    assert result.quality is plates.PlateQuality.INCOMPLETE
    assert result.missing == ("no supplier product is mapped to Saffron yet",)
    assert result.cost_per_portion is None
    assert result.margin is None
    assert result.margin_pct is None


def test_a_usable_share_costs_what_the_storeroom_issued():
    """D13, the whole point of the column: a recipe says what goes in the pot,
    so 500 g of chicken at 85% usable cost 588.24 g off the shelf and the
    plate must cost the shelf. Hand-checked: 500 / 0.85 x 0.02 = 11.7647."""
    price = plates.Priced(cost_per_base_unit=Decimal("0.02"), base_unit="g", quality=None)
    trimmed = plates.cost_component(
        position=0,
        qty=Decimal("500"),
        unit="g",
        ingredient_name="Chicken",
        has_packs=True,
        price=price,
        usable_share=Decimal("0.85"),
    )
    assert trimmed.cost.quantize(Decimal("0.0001")) == Decimal("11.7647")
    # The divisor and nothing else: exactly 1/0.85 of the as-purchased cost.
    assert plates.bought_base_qty(Decimal("500"), Decimal("0.85")) == Decimal("500") / Decimal(
        "0.85"
    )


def test_a_component_with_no_share_costs_exactly_what_it_costed_before():
    """Every recipe on file predates 0021 and must be byte-identical: the same
    ComponentCost, whether the share arrives as None or never arrives at all.
    A manufactured 1.0 divisor would be arithmetically the same and is still
    not what this does - `bought_base_qty` returns the quantity untouched."""
    price = plates.Priced(cost_per_base_unit=Decimal("0.02"), base_unit="g", quality=None)
    args = dict(
        position=0,
        qty=Decimal("500"),
        unit="g",
        ingredient_name="Chicken",
        has_packs=True,
        price=price,
    )
    omitted = plates.cost_component(**args)
    explicit_none = plates.cost_component(**args, usable_share=None)
    assert omitted == explicit_none
    assert omitted == plates.ComponentCost(0, cost=Decimal("10.00"), quality=Quality.RELIABLE)
    assert plates.bought_base_qty(Decimal("500"), None) == Decimal("500")


def test_the_component_words_name_the_typed_amount_the_share_and_the_bought_one():
    """Composed here, printed on the screen - the screen never divides, so the
    bought amount a reader checks by hand is the one the plate costed. The
    columns hold four decimals for a 0.006 g draw of saffron; printing those
    zeros back would read as false precision on every line of every card."""
    assert (
        plates.usable_words(Decimal("500.0000"), "g", Decimal("0.8500"))
        == "500 g at 85% usable, 588 g bought"
    )
    # The bought amount takes the typed quantity's own precision, half up.
    assert (
        plates.usable_words(Decimal("27.5000"), "g", Decimal("0.8500"))
        == "27.5 g at 85% usable, 32.4 g bought"
    )
    # A thousand is 1000 and never 1E+3.
    assert (
        plates.usable_words(Decimal("1000.0000"), "g", Decimal("0.8500"))
        == "1000 g at 85% usable, 1176 g bought"
    )
    # A stated 100% is a fact somebody entered, and says so.
    assert (
        plates.usable_words(Decimal("1.0000"), "pc", Decimal("1.0000"))
        == "1 pc at 100% usable, 1 pc bought"
    )
    # No share, no words: the screen prints the quantity alone, as it always has.
    assert plates.usable_words(Decimal("220.0000"), "g", None) is None


def test_an_empty_version_is_incomplete_never_pure_margin():
    result = plates.plate(
        [], yield_portions=Decimal("1"), selling_price=Decimal("10.00"), vat_rate=None
    )
    assert result.quality is plates.PlateQuality.INCOMPLETE
    assert result.missing == (plates.EMPTY_RECIPE,)
    assert result.margin is None


# -- the endpoints (real Postgres) ---------------------------------------------


@pytest.fixture
def api(settings, db):
    app = FastAPI()
    app.include_router(api_router)
    app.include_router(menu_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _supplier(db, name: str = "Gulf Foods Trading L.L.C.") -> str:
    return str(
        await db.pool.fetchval(
            "insert into suppliers (tenant_id, name) values ($1, $2) "
            "on conflict (tenant_id, name) do update set name = excluded.name returning id",
            DEMO_TENANT_ID,
            name,
        )
    )


async def _catalog_item(db, supplier_id: str, canonical_name: str, pack_size: str | None) -> str:
    return str(
        await db.pool.fetchval(
            """
            insert into supplier_items (tenant_id, supplier_id, canonical_name, pack_size)
            values ($1, $2, $3, $4) returning id
            """,
            DEMO_TENANT_ID,
            supplier_id,
            canonical_name,
            pack_size,
        )
    )


async def _delivery(
    db,
    item_id: str,
    *,
    supplier_id: str,
    pack_size: str | None,
    unit_price: Decimal,
    invoice_date: str = "2026-07-06",
    raw_name: str = "Delivery line",
) -> str:
    """One confirmed delivery through the **real confirm path**, so the cost
    is frozen by the same transaction that confirms it (WP-50/WP-53) - the
    material prices below rest on lines an invoice actually produced."""
    document_id = await db.pool.fetchval(
        "insert into documents (tenant_id, source, status) values ($1, 'manual', 'extracted') "
        "returning id",
        DEMO_TENANT_ID,
    )
    invoice_id = await db.pool.fetchval(
        """
        insert into invoices (tenant_id, document_id, supplier_id, status, total, invoice_date)
        values ($1, $2, $3, 'awaiting_confirm', $4, $5)
        returning id::text
        """,
        DEMO_TENANT_ID,
        document_id,
        supplier_id,
        unit_price,
        datetime.date.fromisoformat(invoice_date),
    )
    await db.pool.execute(
        """
        insert into invoice_lines (tenant_id, invoice_id, position, raw_name, supplier_item_id,
                                   qty, pack_size, unit_price, line_total)
        values ($1, $2, 0, $3, $4, 1, $5, $6, $6)
        """,
        DEMO_TENANT_ID,
        invoice_id,
        raw_name,
        item_id,
        pack_size,
        unit_price,
    )
    assert await db.confirm_invoice(invoice_id, tenant_id=DEMO_TENANT_ID, actor="console") is True
    return invoice_id


async def _material(db, item_id: str, name: str, base_unit: str) -> str:
    """Map a pack onto a material through the M5 door (audit row included)."""
    ingredient = await db.map_supplier_item(
        item_id, tenant_id=DEMO_TENANT_ID, name=name, base_unit=base_unit, actor="console"
    )
    return ingredient["id"]


async def _menu_item(api, name: str, price: str) -> str:
    response = await api.post(
        "/api/menu-items", json={"name": name, "selling_price": price}, headers=AUTH
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _recipe(api, item_id: str, components: list[dict], yield_portions: str = "1") -> None:
    response = await api.post(
        f"/api/menu-items/{item_id}/recipe",
        json={"yield_portions": yield_portions, "yield_label": "cup", "components": components},
        headers=AUTH,
    )
    assert response.status_code == 201, response.text


async def _karak(db, api) -> dict:
    """The seeded hand-check scenario: tea at 90.00/5kg (0.018/g), milk at
    8.00/1L (0.008/ml), cups at 10.00/50pcs (0.20 each); a 10.00 karak using
    4 g + 60 ml + 1 cup. Plate cost 0.752, net 9.524, margin 8.772 = 92.1%%."""
    supplier_id = await _supplier(db)
    tea_pack = await _catalog_item(db, supplier_id, "CTC TEA 5KG", "5kg")
    milk_pack = await _catalog_item(db, supplier_id, "EVAP MILK 1L", "1l")
    cup_pack = await _catalog_item(db, supplier_id, "PAPER CUP 50PCS", "50 pcs")
    await _delivery(
        db,
        tea_pack,
        supplier_id=supplier_id,
        pack_size="5kg",
        unit_price=Decimal("90.00"),
        raw_name="CTC TEA 5KG",
    )
    await _delivery(
        db,
        milk_pack,
        supplier_id=supplier_id,
        pack_size="1l",
        unit_price=Decimal("8.00"),
        raw_name="EVAP MILK 1L",
    )
    await _delivery(
        db,
        cup_pack,
        supplier_id=supplier_id,
        pack_size="50 pcs",
        unit_price=Decimal("10.00"),
        raw_name="PAPER CUP 50PCS",
    )
    tea = await _material(db, tea_pack, "CTC Black Tea", "g")
    milk = await _material(db, milk_pack, "Evaporated Milk", "ml")
    cup = await _material(db, cup_pack, "Paper Cup", "pc")

    item_id = await _menu_item(api, "Karak Cup", "10.00")
    await _recipe(
        api,
        item_id,
        [
            {"ingredient_id": tea, "qty": "4", "unit": "g", "source_text": "70 ml concentrate"},
            {"ingredient_id": milk, "qty": "60", "unit": "ml"},
            {"ingredient_id": cup, "qty": "1", "unit": "pc"},
        ],
    )
    return {
        "item_id": item_id,
        "supplier_id": supplier_id,
        "tea": tea,
        "milk": milk,
        "cup": cup,
        "tea_pack": tea_pack,
        "milk_pack": milk_pack,
    }


async def _detail(api, item_id: str) -> dict:
    response = await api.get(f"/api/menu-items/{item_id}", headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


@requires_db
async def test_the_karak_hand_check_to_the_fils(api, db):
    """Hand arithmetic on the seeded karak matches to the fils, the margin is
    computed against the price net of VAT, a packaging cup priced per piece
    lands in the plate cost, and the answer names its recipe version and each
    component's invoice line (the forensics of the current number)."""
    scenario = await _karak(db, api)
    detail = await _detail(api, scenario["item_id"])

    result = detail["plate"]
    assert result["quality"] == "reliable_with_limitations"
    assert result["missing"] == []
    assert result["cost_per_portion"] == "0.752"
    assert result["net_price"] == "9.524"
    assert result["vat_rate"] == "0.05"
    assert result["margin"] == "8.772"
    assert result["margin_pct"] == "92.1"

    assert detail["recipe"]["version"] == 1
    amounts = {c["ingredient_name"]: c["cost"]["amount"] for c in detail["recipe"]["components"]}
    assert amounts == {"CTC Black Tea": "0.072", "Evaporated Milk": "0.480", "Paper Cup": "0.200"}
    for component in detail["recipe"]["components"]:
        price = component["cost"]["price"]
        assert price["invoice_line_id"] and price["invoice_id"]
    # The word "food cost" appears nowhere in this product's answers (§3).
    assert "food_cost" not in str(detail)


@requires_db
async def test_a_batch_recipe_divides_once_by_its_yield(api, db):
    """One pot -> 40 cups: 220 g of tea at 0.018/g is 3.96 a batch, 0.099 a
    cup."""
    scenario = await _karak(db, api)
    pot = await _menu_item(api, "Karak Flask", "35.00")
    await _recipe(
        api,
        pot,
        [{"ingredient_id": scenario["tea"], "qty": "220", "unit": "g"}],
        yield_portions="40",
    )
    detail = await _detail(api, pot)
    assert detail["plate"]["cost_per_portion"] == "0.099"


@requires_db
async def test_a_conversion_yield_moves_the_plate_and_says_so_on_the_line(api, db):
    """The same pot, with the tea dust at 85% usable: the batch draws 258.82 g
    off the shelf rather than 220, so the cup costs 0.116 instead of 0.099 -
    and the component line says where that came from, in words the screen
    prints rather than computes."""
    scenario = await _karak(db, api)
    pot = await _menu_item(api, "Karak Flask", "35.00")
    await _recipe(
        api,
        pot,
        [{"ingredient_id": scenario["tea"], "qty": "220", "unit": "g", "usable_share": "0.85"}],
        yield_portions="40",
    )
    detail = await _detail(api, pot)
    assert detail["plate"]["cost_per_portion"] == "0.116"
    component = detail["recipe"]["components"][0]
    assert component["usable_words"] == "220 g at 85% usable, 259 g bought"
    assert component["usable_share"] == "0.8500"


@requires_db
async def test_the_door_refuses_a_usable_share_outside_the_bounds(api, db):
    """A share is a fraction, and the mistake a spreadsheet makes is sending 85
    for 85%. Dividing the plate by eighty-five would cost the tea in fractions
    of a fil on every dish that named it - silently - so the door refuses it,
    names the material so the cell can be found, and writes no version."""
    scenario = await _karak(db, api)
    item_id = await _menu_item(api, "Trimmed Dish", "18.00")
    tail = (
        "is not a usable share for CTC Black Tea: send the share of what is bought "
        'that reaches the pot, above 0 and at most 1, like "0.85" for 85%'
    )
    # "0.00001" is the odd one: it passes the bounds and then rounds away to
    # nothing in a four-decimal column, so the door refuses what the check
    # constraint would otherwise refuse with a 500.
    for bad in ["0", "1.2", "85", "-0.5", "most of it", "0.00001"]:
        response = await api.post(
            f"/api/menu-items/{item_id}/recipe",
            json={
                "yield_portions": "1",
                "components": [
                    {
                        "ingredient_id": scenario["tea"],
                        "qty": "220",
                        "unit": "g",
                        "usable_share": bad,
                    }
                ],
            },
            headers=AUTH,
        )
        assert response.status_code == 422, bad
        assert response.json()["detail"] == f"'{bad}' {tail}"
    assert (
        await db.pool.fetchval("select count(*) from recipes where menu_item_id = $1", item_id)
    ) == 0


@requires_db
async def test_an_item_with_no_recipe_is_incomplete_never_pure_margin(api):
    item_id = await _menu_item(api, "Mystery Dish", "20.00")
    detail = await _detail(api, item_id)
    assert detail["plate"]["quality"] == "incomplete"
    assert detail["plate"]["missing"] == ["no recipe yet"]
    assert detail["plate"]["cost_per_portion"] is None
    assert detail["plate"]["margin"] is None
    assert detail["plate"]["margin_pct"] is None


@requires_db
async def test_one_unmapped_ingredient_makes_the_item_incomplete_with_no_cost(api, db):
    """The costed components keep their own figures in the drill, but the
    plate shows no number at all - a hole must never read as a fat margin."""
    scenario = await _karak(db, api)
    saffron = str(
        await db.pool.fetchval(
            "insert into ingredients (tenant_id, name, base_unit) values ($1, 'Saffron', 'g') "
            "returning id",
            DEMO_TENANT_ID,
        )
    )
    item_id = await _menu_item(api, "Zafran Karak", "8.00")
    await _recipe(
        api,
        item_id,
        [
            {"ingredient_id": scenario["tea"], "qty": "4", "unit": "g"},
            {"ingredient_id": saffron, "qty": "0.01", "unit": "g"},
        ],
    )
    detail = await _detail(api, item_id)
    assert detail["plate"]["quality"] == "incomplete"
    assert detail["plate"]["missing"] == ["no supplier product is mapped to Saffron yet"]
    assert detail["plate"]["cost_per_portion"] is None
    by_name = {c["ingredient_name"]: c for c in detail["recipe"]["components"]}
    assert by_name["CTC Black Tea"]["cost"]["amount"] == "0.072"
    assert by_name["Saffron"]["cost"] is None
    assert by_name["Saffron"]["missing"] == "no supplier product is mapped to Saffron yet"


@requires_db
async def test_a_blocked_component_names_its_wp55_reason(api, db):
    """A material whose only purchase is a bare carton: the missing sentence
    carries the blocked-cost queue's own words, so the fix is one click away."""
    supplier_id = await _supplier(db)
    wrap_pack = await _catalog_item(db, supplier_id, "FOIL WRAP", "1 ctn")
    await _delivery(
        db,
        wrap_pack,
        supplier_id=supplier_id,
        pack_size="1 ctn",
        unit_price=Decimal("25.00"),
        raw_name="FOIL WRAP",
    )
    wrap = await _material(db, wrap_pack, "Foil Wrap", "pc")

    item_id = await _menu_item(api, "Wrapped Shawarma", "12.00")
    await _recipe(api, item_id, [{"ingredient_id": wrap, "qty": "1", "unit": "pc"}])
    detail = await _detail(api, item_id)
    assert detail["plate"]["quality"] == "incomplete"
    assert detail["plate"]["missing"] == [
        "Foil Wrap has no costed purchase yet: "
        "Nothing on the invoice says how much one of these holds."
    ]


@requires_db
async def test_an_estimated_material_cost_makes_the_plate_estimated(api, db):
    """A cost built on a human's pack conversion reads *estimated* (WP-55/C9),
    and the plate inherits the label - one layer up, automatically."""
    supplier_id = await _supplier(db)
    flour_pack = await _catalog_item(db, supplier_id, "FLOUR CTN", "1 ctn")
    await _delivery(
        db,
        flour_pack,
        supplier_id=supplier_id,
        pack_size="1 ctn",
        unit_price=Decimal("43.50"),
        raw_name="FLOUR CTN",
    )
    flour = await _material(db, flour_pack, "Refined Flour", "g")
    costed = await db.set_pack_size_override(
        flour_pack, tenant_id=DEMO_TENANT_ID, pack_size="25 kg", actor="console"
    )
    assert costed == 1

    item_id = await _menu_item(api, "Paratha", "3.00")
    await _recipe(api, item_id, [{"ingredient_id": flour, "qty": "100", "unit": "g"}])
    detail = await _detail(api, item_id)
    assert detail["plate"]["quality"] == "estimated"
    component = detail["recipe"]["components"][0]
    assert component["cost"]["quality"] == "estimated"
    # 43.50 / 25000 g = 0.00174/g x 100 g = 0.174
    assert component["cost"]["amount"] == "0.174"


@requires_db
async def test_a_newer_uncosted_purchase_caps_the_material_and_its_plates(api, db):
    """D11, the silent-stale-number class one layer up: milk's newest delivery
    is a bare carton nothing could cost, so the old price stays visible but
    everything reads *estimated* and the blocked line is named - on the
    materials screen and on the plate alike."""
    scenario = await _karak(db, api)
    blocked_invoice = await _delivery(
        db,
        scenario["milk_pack"],
        supplier_id=scenario["supplier_id"],
        pack_size="1 ctn",
        unit_price=Decimal("95.00"),
        invoice_date="2026-08-01",
        raw_name="EVAP MILK CTN",
    )

    materials = (await api.get("/api/ingredients", headers=AUTH)).json()["ingredients"]
    milk = next(row for row in materials if row["name"] == "Evaporated Milk")
    assert milk["price"]["per_base_unit"] == "0.00800000"  # the old figure, still visible
    assert milk["price"]["quality"] == "estimated"  # capped
    newer = milk["price"]["newer_uncosted"]
    assert newer["invoice_id"] == blocked_invoice
    assert newer["reason"] == "Nothing on the invoice says how much one of these holds."

    detail = await _detail(api, scenario["item_id"])
    assert detail["plate"]["quality"] == "estimated"
    milk_component = next(
        c for c in detail["recipe"]["components"] if c["ingredient_name"] == "Evaporated Milk"
    )
    assert milk_component["cost"]["quality"] == "estimated"
    assert milk_component["cost"]["price"]["newer_uncosted"]["invoice_id"] == blocked_invoice


@requires_db
async def test_a_line_claiming_verified_still_never_reaches_a_plate(api, db):
    """The pin, end to end: hand-edit a stored cost basis to claim 'verified'
    (no write path produces one) and the plate still reads *reliable with
    limitations* - the vocabulary cannot say the word."""
    scenario = await _karak(db, api)
    await db.pool.execute(
        """
        update invoice_lines
        set cost_basis = jsonb_set(cost_basis, '{quality}', '"verified"')
        where cost_per_base_unit is not null
        """
    )
    detail = await _detail(api, scenario["item_id"])
    assert detail["plate"]["quality"] == "reliable_with_limitations"
    assert "verified" not in str(detail["plate"])


@requires_db
async def test_confirming_a_newer_invoice_moves_the_plate_with_zero_menu_writes(api, db):
    """The demo's act-two turn: milk goes up, the karak margin falls on the
    next read - no cache, no recompute job, and the menu tables are
    byte-identical before and after."""
    scenario = await _karak(db, api)
    tables = ("menu_items", "recipes", "recipe_components")
    before = {t: await db.pool.fetch(f"select * from {t} order by id") for t in tables}

    await _delivery(
        db,
        scenario["milk_pack"],
        supplier_id=scenario["supplier_id"],
        pack_size="1l",
        unit_price=Decimal("9.00"),
        invoice_date="2026-08-15",
        raw_name="EVAP MILK 1L",
    )

    detail = await _detail(api, scenario["item_id"])
    # 4 x 0.018 + 60 x 0.009 + 1 x 0.20 = 0.812
    assert detail["plate"]["cost_per_portion"] == "0.812"
    assert detail["plate"]["margin"] == "8.712"

    after = {t: await db.pool.fetch(f"select * from {t} order by id") for t in tables}
    assert before == after


class _CountingPool:
    """Counts every query the wrapped pool answers, so the bounded-queries
    rule (D10) is a measured fact rather than a comment."""

    def __init__(self, inner):
        self._inner = inner
        self.queries = 0

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if name in ("fetch", "fetchrow", "fetchval", "execute"):

            async def counted(*args, **kwargs):
                self.queries += 1
                return await attr(*args, **kwargs)

            return counted
        return attr


@requires_db
async def test_the_menu_screens_query_count_does_not_grow_with_the_menu(api, db):
    """One karak on the menu and five items on the menu answer in the same
    number of queries - the derivation is per request, never per row."""
    scenario = await _karak(db, api)
    counting = _CountingPool(db.pool)

    db.pool = counting
    try:
        assert (await api.get("/api/menu-items", headers=AUTH)).status_code == 200
        small_menu = counting.queries
    finally:
        db.pool = counting._inner

    for name in ("Karak Flask", "Zafran Karak", "Sulaimani", "Honey Cake"):
        item_id = await _menu_item(api, name, "11.00")
        await _recipe(api, item_id, [{"ingredient_id": scenario["tea"], "qty": "3", "unit": "g"}])

    counting = _CountingPool(db.pool)
    db.pool = counting
    try:
        assert (await api.get("/api/menu-items", headers=AUTH)).status_code == 200
        large_menu = counting.queries
    finally:
        db.pool = counting._inner

    assert small_menu == large_menu


@requires_db
async def test_one_material_missing_twice_is_named_once(api, db):
    """The real menu draws lemon twice in one dish - 7 g in the marinade and
    20 g as the wedge - so an unmapped material would be listed as two jobs
    when it is one click, in the very place a person looks to find out what to
    do next (found loading F7's menu, 2026-08-31)."""
    supplier_id = await _supplier(db)
    pack = await _catalog_item(db, supplier_id, "LEMON 5KG", "5kg")
    lemon = await _material(db, pack, "Lemon", "g")
    item_id = await _menu_item(api, "Chicken 65 Dry", "17.00")
    await _recipe(
        api,
        item_id,
        [
            {"ingredient_id": lemon, "qty": "7.143", "unit": "g"},
            {"ingredient_id": lemon, "qty": "20", "unit": "g"},
        ],
    )
    plate = (await _detail(api, item_id))["plate"]
    assert plate["quality"] == "incomplete"
    assert plate["missing"] == ["Lemon has no costed purchase yet"]
