"""M6 WP-63: the money moment - a price move lands on the plates.

M2's price alert names cartons; this names cups. The rules under test are
the honesty ones: "previous" is the winning pack's own previous costed line
(D3 - same-pack, like M2's baseline), a winner-pack switch says "price basis
changed" with both packs named and **no delta**, and because everything
above the invoice line is derived, confirming a newer invoice moves the
answer on the next read with nothing recomputed and nothing to invalidate -
and unmapping the material takes the move with it, no residue.
"""

from decimal import Decimal

from .conftest import DEMO_TENANT_ID, requires_db
from .test_plates import (
    AUTH,
    _catalog_item,
    _delivery,
    _detail,
    _karak,
    _material,
    _menu_item,
    _recipe,
)
from .test_plates import api as plates_api

#: The same app fixture test_plates builds (both routers mounted); rebinding
#: it under the local name registers it for this module's tests.
api = plates_api


async def _moves(api) -> list[dict]:
    response = await api.get("/api/price-moves", headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()["moves"]


@requires_db
async def test_a_first_purchase_is_a_price_not_a_move(api, db):
    """One delivery per material: prices exist, but nothing has moved."""
    await _karak(db, api)
    assert await _moves(api) == []


@requires_db
async def test_milk_up_names_each_plate_and_its_exact_aed_drop(api, db):
    """The acceptance hand-check: milk 8.00 -> 9.00 a litre on the same 1 L
    pack. The karak cup uses 60 ml, so its margin fell exactly 0.06; the
    flask (tea only) is untouched and byte-identical."""
    scenario = await _karak(db, api)
    flask = await _menu_item(api, "Karak Flask", "35.00")
    await _recipe(
        api,
        flask,
        [{"ingredient_id": scenario["tea"], "qty": "220", "unit": "g"}],
        yield_portions="40",
    )
    flask_before = await _detail(api, flask)

    newer = await _delivery(
        db,
        scenario["milk_pack"],
        supplier_id=scenario["supplier_id"],
        pack_size="1l",
        unit_price=Decimal("9.00"),
        invoice_date="2026-08-15",
        raw_name="EVAP MILK 1L",
    )

    moves = await _moves(api)
    assert len(moves) == 1
    move = moves[0]
    assert move["kind"] == "moved"
    assert move["ingredient_name"] == "Evaporated Milk"
    assert move["delta_per_display_unit"] == "1.00"  # per litre
    assert move["current"]["per_display_unit"] == "9.00"
    assert move["previous"]["per_display_unit"] == "8.00"
    # Both sides drill to their own invoice - the move is checkable.
    assert move["current"]["invoice_id"] == newer
    assert move["previous"]["invoice_id"] != newer

    assert [item["name"] for item in move["items"]] == ["Karak Cup"]
    item = move["items"][0]
    # 60 ml x 0.001/ml = 0.06 a cup; margin 8.772 -> 8.712 at the new price.
    assert item["impact_per_portion"] == "0.060"
    assert item["margin_after"] == "8.712"
    assert item["margin_before"] == "8.772"
    assert item["margin_pct_after"] == "91.5"
    assert item["margin_pct_before"] == "92.1"

    # The unaffected item is byte-identical, not merely similar.
    assert await _detail(api, flask) == flask_before


@requires_db
async def test_the_same_price_again_is_not_a_move(api, db):
    scenario = await _karak(db, api)
    await _delivery(
        db,
        scenario["milk_pack"],
        supplier_id=scenario["supplier_id"],
        pack_size="1l",
        unit_price=Decimal("8.00"),
        invoice_date="2026-08-15",
        raw_name="EVAP MILK 1L",
    )
    assert await _moves(api) == []


@requires_db
async def test_a_winning_pack_switch_shows_basis_changed_and_no_delta(api, db):
    """A 24x400ml carton bought after the 1 L tin: the price basis changed.
    Both packs are named, and no delta appears anywhere - a delta across
    packs is a pack artifact wearing a percent sign."""
    scenario = await _karak(db, api)
    carton = await _catalog_item(db, scenario["supplier_id"], "EVAP MILK 24x400ML", "24x400ml")
    await _delivery(
        db,
        carton,
        supplier_id=scenario["supplier_id"],
        pack_size="24x400ml",
        unit_price=Decimal("45.00"),
        invoice_date="2026-08-15",
        raw_name="EVAP MILK 24x400ML",
    )
    # Map the carton onto the same material as the tin.
    ingredient = await db.map_supplier_item(
        carton, tenant_id=DEMO_TENANT_ID, ingredient_id=scenario["milk"], actor="console"
    )
    assert ingredient["id"] == scenario["milk"]

    moves = await _moves(api)
    assert len(moves) == 1
    move = moves[0]
    assert move["kind"] == "basis_changed"
    assert move["delta_per_display_unit"] is None
    assert move["items"] == []
    assert move["current"]["pack_size"] == "24x400ml"
    assert move["previous"]["pack_size"] == "1l"
    assert move["current"]["product_name"] == "EVAP MILK 24x400ML"
    assert move["previous"]["product_name"] == "EVAP MILK 1L"


@requires_db
async def test_unmapping_the_moved_material_leaves_no_residue(api, db):
    """WP-52's undo, visible at plate level: the move derives from the
    mapping, so unmapping corrects the display immediately with nothing left
    behind to clean up."""
    scenario = await _karak(db, api)
    await _delivery(
        db,
        scenario["milk_pack"],
        supplier_id=scenario["supplier_id"],
        pack_size="1l",
        unit_price=Decimal("9.00"),
        invoice_date="2026-08-15",
        raw_name="EVAP MILK 1L",
    )
    assert len(await _moves(api)) == 1

    await db.unmap_supplier_item(
        scenario["milk_pack"],
        tenant_id=DEMO_TENANT_ID,
        actor="console",
        ingredient_id=scenario["milk"],
    )
    assert await _moves(api) == []
    # And the plate above it now says what is missing rather than guessing.
    detail = await _detail(api, scenario["item_id"])
    assert detail["plate"]["quality"] == "incomplete"


@requires_db
async def test_a_moved_material_off_the_menu_stays_off_this_screen(api, db):
    """A moved material feeding no recipe belongs to M2's alert, not the
    money moment - this screen is about plates."""
    scenario = await _karak(db, api)
    oil = await _catalog_item(db, scenario["supplier_id"], "FRYING OIL 5L", "5l")
    await _delivery(
        db,
        oil,
        supplier_id=scenario["supplier_id"],
        pack_size="5l",
        unit_price=Decimal("40.00"),
        raw_name="FRYING OIL 5L",
    )
    await _material(db, oil, "Frying Oil", "ml")
    await _delivery(
        db,
        oil,
        supplier_id=scenario["supplier_id"],
        pack_size="5l",
        unit_price=Decimal("45.00"),
        invoice_date="2026-08-15",
        raw_name="FRYING OIL 5L",
    )

    assert await _moves(api) == []
