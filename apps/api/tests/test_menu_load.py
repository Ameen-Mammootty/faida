"""M6 WP-64: the batch loader's door - one recipe, one transaction.

The loader's whole promise to a consultant is a loop: upload 45 recipes, read
what went wrong on the two rows that failed, fix those two cells in the
spreadsheet, upload the same file again. That loop only works if three things
are true of this door, and each of them has its tests here:

1. **A row commits whole or not at all.** A recipe with a bad component must
   not leave a menu item behind with no recipe - that item would read
   *incomplete* on the menu screen for a reason nobody could see.
2. **Re-uploading is a no-op.** The 43 recipes that did not change must not
   gain a version recording nothing, or the version number stops meaning
   anything and the audit trail fills with noise (D8, `recipes.py`).
3. **A CSV is not privileged.** Every refusal a person gets typing one recipe
   by hand, the loader gets too, in the same words - there is exactly one
   write door (WP-60), and this is a second entrance to it, not a bypass.
"""

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from faida_api.api import router as api_router
from faida_api.menu import router as menu_router

from .conftest import AUTH, DEMO_TENANT_ID, TEST_ACTOR, requires_db, wire_auth


@pytest.fixture
def api(settings, db):
    """Both routers: the loader writes recipes through menu.py and creates the
    materials they name through the M5 surface in api.py."""
    app = FastAPI()
    app.include_router(menu_router)
    app.include_router(api_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _row(**overrides) -> dict:
    """One CSV recipe as the grid sends it: a karak flask, two components."""
    body = {
        "name": "Karak Tea - Flask 1 L",
        "category": "Tea Corner",
        "selling_price": "35.00",
        "yield_portions": "1",
        "yield_label": "serving",
        "components": [],
    }
    body.update(overrides)
    return body


def _component(ingredient_id: str, qty: str = "27.5", unit: str = "g", **overrides) -> dict:
    body = {
        "ingredient_id": ingredient_id,
        "qty": qty,
        "unit": unit,
        "source_text": "500 ml Karak Concentrate",
    }
    body.update(overrides)
    return body


async def _material(api, name: str, unit: str = "g") -> str:
    response = await api.post("/api/ingredients", json={"name": name, "unit": unit}, headers=AUTH)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _load(api, body: dict) -> httpx.Response:
    return await api.post("/api/menu-items/load", json=body, headers=AUTH)


async def _versions(db, menu_item_id: str) -> list:
    return await db.pool.fetch(
        "select id::text as id, version, yield_portions, yield_label from recipes "
        "where menu_item_id = $1 order by version",
        menu_item_id,
    )


async def _audit_actions(db) -> list[str]:
    return [
        row["action"] for row in await db.pool.fetch("select action from audit_events order by id")
    ]


# --- the material door the loader needs (POST /api/ingredients) -------------


@requires_db
async def test_a_material_can_exist_before_any_invoice_names_it(api, db):
    """The menu says "Saffron" months before a supplier invoice does. Until
    M6 a material could only be born through a merge; a recipe is the second
    reason one exists."""
    ingredient_id = await _material(api, "Saffron")
    row = await db.pool.fetchrow(
        "select name, base_unit from ingredients where id = $1", ingredient_id
    )
    assert (row["name"], row["base_unit"]) == ("Saffron", "g")
    audit = await db.pool.fetchrow(
        "select actor, action, detail from audit_events where subject_type = 'ingredient'"
    )
    assert audit["actor"] == TEST_ACTOR
    assert audit["action"] == "ingredient.created"


@requires_db
async def test_a_duplicate_material_name_is_refused_with_a_sentence(api):
    await _material(api, "Saffron")
    response = await api.post(
        "/api/ingredients", json={"name": "Saffron", "unit": "g"}, headers=AUTH
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "a raw material called 'Saffron' already exists"


@requires_db
async def test_the_shelf_a_new_material_sits_on_is_decided_by_units_py(api, db):
    """The loader sends the recipe row's own measure, never a base unit, so a
    browser can never invent a dimension: "ea" is pieces because `units.py`
    says so, and a container is refused because it says how many, not how
    much."""
    cups = await _material(api, "Delivery cup L + lid", unit="ea")
    assert await db.pool.fetchval("select base_unit from ingredients where id = $1", cups) == "pc"

    response = await api.post(
        "/api/ingredients", json={"name": "Flour", "unit": "ctn"}, headers=AUTH
    )
    assert response.status_code == 422
    assert response.json()["detail"] == (
        "'ctn' does not say whether Flour is measured by weight (g, kg), by volume "
        "(ml, l) or in pieces"
    )


@requires_db
async def test_a_material_with_no_pack_makes_its_plate_incomplete_not_cheap(api):
    """The honest consequence of loading a menu before mapping its materials:
    the item appears, keeps its menu price, and shows no cost at all."""
    saffron = await _material(api, "Saffron")
    await _load(api, _row(components=[_component(saffron, qty="0.05")]))

    listed = await api.get("/api/menu-items", headers=AUTH)
    item = listed.json()["menu_items"][0]
    assert item["plate"]["quality"] == "incomplete"
    assert item["plate"]["cost_per_portion"] is None
    assert item["plate"]["missing"] == ["no supplier product is mapped to Saffron yet"]


# --- one recipe, one transaction --------------------------------------------


@requires_db
async def test_a_new_item_and_its_first_version_arrive_together(api, db):
    tea = await _material(api, "CTC black tea")
    response = await _load(api, _row(components=[_component(tea)]))
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["outcome"] == "created"
    assert body["version"] == 1
    assert body["changed"] == []
    assert body["menu_item"]["name"] == "Karak Tea - Flask 1 L"
    assert body["menu_item"]["category"] == "Tea Corner"
    assert body["menu_item"]["selling_price"] == "35.000"
    assert body["menu_item"]["recipe"]["version"] == 1
    assert body["menu_item"]["recipe"]["components"][0]["source_text"] == (
        "500 ml Karak Concentrate"
    )
    assert await _audit_actions(db) == [
        "ingredient.created",
        "menu_item.created",
        "recipe.version_created",
    ]


@requires_db
async def test_a_refused_component_leaves_no_half_loaded_item_behind(api, db):
    """The row that justifies the transaction. Component two is measured by
    volume on a material measured by weight - so the whole row is refused and
    no menu item exists at all, rather than one that reads *incomplete* for a
    reason nobody can see."""
    tea = await _material(api, "CTC black tea")
    milk = await _material(api, "Evaporated milk", unit="ml")
    response = await _load(
        api,
        _row(components=[_component(tea), _component(milk, qty="390", unit="g")]),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == (
        "'g' is measured by weight, but Evaporated milk is measured by volume"
    )
    assert await db.pool.fetchval("select count(*) from menu_items") == 0
    assert await db.pool.fetchval("select count(*) from recipes") == 0


@requires_db
async def test_one_bad_row_does_not_stop_the_rest_of_the_file(api, db):
    """The loop's other half: fix-in-spreadsheet works because the 44 good
    recipes are already in."""
    tea = await _material(api, "CTC black tea")
    milk = await _material(api, "Evaporated milk", unit="ml")

    bad = await _load(api, _row(name="Broken", components=[_component(milk, unit="g")]))
    good = await _load(api, _row(name="Karak Tea - Cup", components=[_component(tea)]))

    assert bad.status_code == 422
    assert good.status_code == 200
    names = [r["name"] for r in await db.pool.fetch("select name from menu_items")]
    assert names == ["Karak Tea - Cup"]


# --- re-uploading is a no-op (D8) -------------------------------------------


@requires_db
async def test_committing_the_same_file_twice_changes_nothing(api, db):
    tea = await _material(api, "CTC black tea")
    body = _row(components=[_component(tea)])
    first = await _load(api, body)
    before = await _audit_actions(db)

    second = await _load(api, body)
    assert second.status_code == 200
    assert second.json()["outcome"] == "unchanged"
    assert second.json()["changed"] == []
    assert second.json()["version"] == first.json()["version"] == 1
    assert await _audit_actions(db) == before


@requires_db
async def test_sorting_the_spreadsheet_is_not_editing_the_recipe(api, db):
    """Order-insensitive by D8: a consultant who sorts their sheet by
    ingredient has not changed a single recipe."""
    tea = await _material(api, "CTC black tea")
    cardamom = await _material(api, "Green cardamom")
    await _load(api, _row(components=[_component(tea), _component(cardamom, qty="2.25")]))

    response = await _load(
        api, _row(components=[_component(cardamom, qty="2.25"), _component(tea)])
    )
    assert response.json()["outcome"] == "unchanged"
    item_id = response.json()["menu_item"]["id"]
    assert len(await _versions(db, item_id)) == 1


@requires_db
async def test_the_same_amount_typed_differently_is_the_same_recipe(api, db):
    """The column stores four decimals and the spreadsheet types none; "ml",
    "ML" and "mls" are one measure. Formatting must never re-version."""
    milk = await _material(api, "Evaporated milk", unit="ml")
    await _load(api, _row(components=[_component(milk, qty="390", unit="ml")]))

    response = await _load(api, _row(components=[_component(milk, qty="390.0000", unit="mls")]))
    assert response.json()["outcome"] == "unchanged"
    assert len(await _versions(db, response.json()["menu_item"]["id"])) == 1


@requires_db
async def test_a_kilo_is_not_a_thousand_grams_on_the_card(api, db):
    """The other side of that rule: a magnitude is not formatting. The card
    now says something different, and the card's words are the only audit a
    typed quantity has - so this re-versions."""
    tea = await _material(api, "CTC black tea")
    await _load(api, _row(components=[_component(tea, qty="1000", unit="g")]))

    response = await _load(api, _row(components=[_component(tea, qty="1", unit="kg")]))
    assert response.json()["outcome"] == "version_added"
    assert response.json()["version"] == 2


@requires_db
async def test_a_changed_quantity_appends_a_version_and_leaves_the_old_one_alone(api, db):
    tea = await _material(api, "CTC black tea")
    first = await _load(api, _row(components=[_component(tea, qty="27.5")]))
    item_id = first.json()["menu_item"]["id"]
    original = await db.pool.fetch(
        "select ingredient_id, qty, unit, source_text from recipe_components "
        "where recipe_id = $1 order by position",
        first.json()["menu_item"]["recipe"]["id"],
    )

    second = await _load(api, _row(components=[_component(tea, qty="30")]))
    assert second.json()["outcome"] == "version_added"
    assert second.json()["version"] == 2
    versions = await _versions(db, item_id)
    assert [v["version"] for v in versions] == [1, 2]
    assert (
        await db.pool.fetch(
            "select ingredient_id, qty, unit, source_text from recipe_components "
            "where recipe_id = $1 order by position",
            versions[0]["id"],
        )
        == original
    )


@requires_db
async def test_a_second_draw_of_the_same_material_is_not_collapsed(api, db):
    """Two identical lines are two lines - the comparison sorts, it does not
    de-duplicate, or a recipe drawing milk twice would read as one that draws
    it once."""
    milk = await _material(api, "Evaporated milk", unit="ml")
    await _load(
        api,
        _row(components=[_component(milk, qty="100", unit="ml"), _component(milk, "100", "ml")]),
    )
    response = await _load(api, _row(components=[_component(milk, qty="100", unit="ml")]))
    assert response.json()["outcome"] == "version_added"


@requires_db
async def test_a_changed_yield_is_a_new_recipe(api):
    tea = await _material(api, "CTC black tea")
    await _load(api, _row(yield_portions="40", components=[_component(tea, qty="220")]))
    response = await _load(api, _row(yield_portions="35", components=[_component(tea, qty="220")]))
    assert response.json()["outcome"] == "version_added"


# --- the item's own facts follow the CSV (D19) ------------------------------


@requires_db
async def test_the_csv_moves_price_and_category_through_their_own_doors(api, db):
    """The spreadsheet is the single source for what an item is called, what
    it sells for and which section it prints in - so a category corrected
    there is corrected on the menu screen's headings too, with its own audit
    row rather than a silent update."""
    tea = await _material(api, "CTC black tea")
    await _load(api, _row(components=[_component(tea)]))

    response = await _load(
        api,
        _row(selling_price="38.00", category="Hot Drinks", components=[_component(tea)]),
    )
    body = response.json()
    assert body["outcome"] == "unchanged"
    assert body["changed"] == ["selling price", "category"]
    assert body["menu_item"]["selling_price"] == "38.000"
    assert body["menu_item"]["category"] == "Hot Drinks"
    assert len(await _versions(db, body["menu_item"]["id"])) == 1

    actions = await _audit_actions(db)
    assert actions[-2:] == ["menu_item.price_changed", "menu_item.category_changed"]
    detail = await db.pool.fetchval(
        "select detail from audit_events where action = 'menu_item.category_changed'"
    )
    assert detail["previous_category"] == "Tea Corner"
    assert detail["category"] == "Hot Drinks"


@requires_db
async def test_a_menu_that_prints_no_sections_loads_without_one(api):
    tea = await _material(api, "CTC black tea")
    response = await _load(api, _row(category=None, components=[_component(tea)]))
    assert response.json()["menu_item"]["category"] is None


@requires_db
async def test_an_archived_dish_is_not_resurrected_by_a_re_upload(api, db):
    """The partial unique index would happily allow a second live row under
    the same name. A re-upload that quietly forks a dish somebody took off the
    menu is worse than a sentence asking for a click."""
    tea = await _material(api, "CTC black tea")
    first = await _load(api, _row(components=[_component(tea)]))
    item_id = first.json()["menu_item"]["id"]
    await api.post(f"/api/menu-items/{item_id}/archive", headers=AUTH)

    response = await _load(api, _row(components=[_component(tea)]))
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "'Karak Tea - Flask 1 L' is archived in Faida. Bring it back first, or take "
        "the row out of the spreadsheet"
    )
    assert await db.pool.fetchval("select count(*) from menu_items") == 1

    # And the click the sentence asks for makes the same upload work.
    await api.post(f"/api/menu-items/{item_id}/unarchive", headers=AUTH)
    assert (await _load(api, _row(components=[_component(tea)]))).json()["outcome"] == "unchanged"


# --- a CSV is not privileged ------------------------------------------------


@requires_db
async def test_the_loader_refuses_what_the_by_hand_door_refuses(api):
    """Same sentences, same status codes - one write door with two entrances.
    A kitchen measure is the one every consultant tries first: a karak "cup"
    is a serving vessel, not an amount, and the conversion is theirs to do."""
    tea = await _material(api, "CTC black tea")
    cases = [
        (
            _row(components=[_component(tea, qty="2", unit="cup")]),
            422,
            "'cup' is not a measure this system converts: give the amount by weight "
            "(g, kg), by volume (ml, l) or in pieces",
        ),
        (
            _row(components=[_component(tea, qty="1", unit="ctn")]),
            422,
            "a ctn is a container, not an amount: say how much of CTC black tea goes "
            "in, by weight, volume or pieces",
        ),
        (
            _row(components=[_component(tea, qty="0")]),
            422,
            "'0' is not a quantity: send an amount above zero, like \"130\"",
        ),
        (
            _row(yield_portions="0", components=[_component(tea)]),
            422,
            "'0' is not a yield: send an amount above zero, like \"40\"",
        ),
        (
            _row(selling_price="0", components=[_component(tea)]),
            422,
            "'0' is not a selling price: send an amount above zero, like \"17.00\"",
        ),
        (
            _row(components=[]),
            422,
            "a recipe needs at least one component: an empty recipe would cost "
            "nothing and read as pure margin",
        ),
        (_row(name="   ", components=[_component(tea)]), 422, "a menu item needs a name"),
    ]
    for body, status, sentence in cases:
        response = await _load(api, body)
        assert response.status_code == status, body
        assert response.json()["detail"] == sentence


@requires_db
async def test_another_tenants_material_reads_as_not_found(api, db):
    other = await db.pool.fetchval(
        "insert into tenants (name, currency) values ('Other', 'AED') returning id"
    )
    theirs = await db.pool.fetchval(
        "insert into ingredients (tenant_id, name, base_unit) values ($1, 'Saffron', 'g') "
        "returning id::text",
        other,
    )
    response = await _load(api, _row(components=[_component(theirs)]))
    assert response.status_code == 404
    assert response.json()["detail"] == "component 1: ingredient not found"


@requires_db
async def test_postgres_refuses_a_cross_tenant_component_whatever_the_code_missed(db):
    """The backstop under the check above (the 0012 composite-key shape), held
    here because the loader is a new caller of the same write."""
    other = await db.pool.fetchval(
        "insert into tenants (name, currency) values ('Other', 'AED') returning id"
    )
    theirs = await db.pool.fetchval(
        "insert into ingredients (tenant_id, name, base_unit) values ($1, 'Saffron', 'g') "
        "returning id::text",
        other,
    )
    from decimal import Decimal

    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await db.load_menu_recipe(
            tenant_id=DEMO_TENANT_ID,
            name="Karak",
            category=None,
            selling_price=Decimal("5"),
            yield_portions=Decimal("1"),
            yield_label=None,
            components=[{"ingredient_id": theirs, "qty": Decimal("1"), "unit": "g"}],
            actor="console",
        )
    assert await db.pool.fetchval("select count(*) from menu_items") == 0
