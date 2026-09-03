"""M6 WP-60: the menu and its recipes exist, and every version of them survives.

The rule these tests hold the door to: **M6 invents no new numbers.** Every
quantity is typed by a named consultant, so the schema's job is to keep what
was typed, keep every version of it, and refuse the shapes that later divide
by zero or cost an empty set as a perfect margin. Each refusal answers with
its own plain sentence and has its own test here (eng review D7); editing
writes a whole new version and never touches an old one; and every write
lands one audit row naming its actor (C8).
"""

import asyncio
import pathlib

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from faida_api.menu import router as menu_router

from .conftest import (
    AUTH,
    DEMO_TENANT_ID,
    MIGRATIONS_DIR,
    SEED_FILE,
    TEST_ACTOR,
    TEST_DATABASE_URL,
    requires_db,
    wire_auth,
)

DOCS = pathlib.Path(__file__).resolve().parents[3] / "Docs"
APPLY_FILE = DOCS / "apply_m6_migrations.sql"
CATEGORY_FILE = DOCS / "apply_m6_category.sql"


@pytest.fixture
def api(settings, db):
    app = FastAPI()
    app.include_router(menu_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _ingredient(db, name: str, base_unit: str = "g", tenant_id: str = DEMO_TENANT_ID) -> str:
    return str(
        await db.pool.fetchval(
            "insert into ingredients (tenant_id, name, base_unit) values ($1, $2, $3) returning id",
            tenant_id,
            name,
            base_unit,
        )
    )


async def _item(api, name: str = "Karak Tea", price: str = "5.00") -> dict:
    response = await api.post(
        "/api/menu-items", json={"name": name, "selling_price": price}, headers=AUTH
    )
    assert response.status_code == 201, response.text
    return response.json()


def _recipe_body(ingredient_id: str, **overrides) -> dict:
    body = {
        "yield_portions": "40",
        "yield_label": "cups",
        "components": [
            {"ingredient_id": ingredient_id, "qty": "220", "unit": "g", "source_text": "220 g tea"}
        ],
    }
    body.update(overrides)
    return body


async def _audit(db, subject_id: str) -> list:
    return await db.pool.fetch(
        "select actor, action, detail from audit_events "
        "where subject_type = 'menu_item' and subject_id = $1 order by id",
        subject_id,
    )


# -- creating and versioning ---------------------------------------------------


@requires_db
async def test_editing_a_recipe_leaves_the_old_version_byte_identical(api, db):
    """The acceptance row's core: two versions after an edit, the old one
    untouched down to the byte, the newest one current."""
    tea = await _ingredient(db, "CTC Black Tea")
    milk = await _ingredient(db, "Evaporated Milk", "ml")
    item = await _item(api)

    response = await api.post(
        f"/api/menu-items/{item['id']}/recipe", json=_recipe_body(tea), headers=AUTH
    )
    assert response.status_code == 201, response.text
    v1 = response.json()["recipe"]
    assert v1["version"] == 1

    before = await db.pool.fetchrow("select * from recipes where id = $1", v1["id"])
    components_before = await db.pool.fetch(
        "select * from recipe_components where recipe_id = $1 order by position", v1["id"]
    )

    response = await api.post(
        f"/api/menu-items/{item['id']}/recipe",
        json={
            "yield_portions": "56",
            "yield_label": "cups",
            "components": [
                {"ingredient_id": tea, "qty": "220", "unit": "g", "source_text": None},
                {"ingredient_id": milk, "qty": "55", "unit": "ml", "source_text": "1 small tin"},
            ],
        },
        headers=AUTH,
    )
    assert response.status_code == 201, response.text
    v2 = response.json()["recipe"]
    assert v2["version"] == 2
    assert v2["yield_portions"] == "56.000"
    assert [c["source_text"] for c in v2["components"]] == [None, "1 small tin"]

    after = await db.pool.fetchrow("select * from recipes where id = $1", v1["id"])
    components_after = await db.pool.fetch(
        "select * from recipe_components where recipe_id = $1 order by position", v1["id"]
    )
    assert before == after
    assert components_before == components_after

    detail = (await api.get(f"/api/menu-items/{item['id']}", headers=AUTH)).json()
    assert detail["recipe"]["version"] == 2


@requires_db
async def test_money_and_quantities_travel_as_strings(api, db):
    """C4/C6: never floats, anywhere in the payload."""
    tea = await _ingredient(db, "CTC Black Tea")
    item = await _item(api, price="5.00")
    response = await api.post(
        f"/api/menu-items/{item['id']}/recipe", json=_recipe_body(tea), headers=AUTH
    )
    detail = response.json()
    assert detail["selling_price"] == "5.000"
    assert detail["recipe"]["yield_portions"] == "40.000"
    assert detail["recipe"]["components"][0]["qty"] == "220.0000"


@requires_db
async def test_two_concurrent_saves_cannot_mint_the_same_version_number(api, db):
    """D17: version = max+1 inside the transaction, unique (menu_item_id,
    version) as the referee. Whatever the interleaving, versions come out
    distinct - and a loser is told in a sentence, not a stack trace."""
    tea = await _ingredient(db, "CTC Black Tea")
    item = await _item(api)

    responses = await asyncio.gather(
        api.post(f"/api/menu-items/{item['id']}/recipe", json=_recipe_body(tea), headers=AUTH),
        api.post(f"/api/menu-items/{item['id']}/recipe", json=_recipe_body(tea), headers=AUTH),
    )
    statuses = sorted(response.status_code for response in responses)
    assert statuses in ([201, 201], [201, 409])
    for response in responses:
        if response.status_code == 409:
            assert "at the same moment" in response.json()["detail"]

    versions = [
        row["version"]
        for row in await db.pool.fetch(
            "select version from recipes where menu_item_id = $1 order by version", item["id"]
        )
    ]
    assert versions == list(range(1, len(versions) + 1))  # distinct and consecutive


@requires_db
async def test_the_constraint_itself_refuses_a_duplicate_version(db):
    """The database carries the promise even for a caller the API never met."""
    tea = await _ingredient(db, "CTC Black Tea")
    item_id = await db.pool.fetchval(
        "insert into menu_items (tenant_id, name, selling_price) values ($1, 'Karak', 5) "
        "returning id",
        DEMO_TENANT_ID,
    )
    await db.pool.execute(
        "insert into recipes (tenant_id, menu_item_id, version, yield_portions) "
        "values ($1, $2, 1, 40)",
        DEMO_TENANT_ID,
        item_id,
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.pool.execute(
            "insert into recipes (tenant_id, menu_item_id, version, yield_portions) "
            "values ($1, $2, 1, 56)",
            DEMO_TENANT_ID,
            item_id,
        )
    del tea


# -- the refusal set, one sentence and one test each ---------------------------


@requires_db
async def test_a_zero_yield_is_refused_with_a_sentence(api, db):
    tea = await _ingredient(db, "CTC Black Tea")
    item = await _item(api)
    for bad in ("0", "-3", "forty"):
        response = await api.post(
            f"/api/menu-items/{item['id']}/recipe",
            json=_recipe_body(tea, yield_portions=bad),
            headers=AUTH,
        )
        assert response.status_code == 422
        assert f"'{bad}' is not a yield" in response.json()["detail"]


@requires_db
async def test_a_non_positive_component_qty_is_refused_with_a_sentence(api, db):
    """A negative quantity would silently subtract cost from the plate."""
    tea = await _ingredient(db, "CTC Black Tea")
    item = await _item(api)
    for bad in ("0", "-220"):
        response = await api.post(
            f"/api/menu-items/{item['id']}/recipe",
            json=_recipe_body(
                tea,
                components=[{"ingredient_id": tea, "qty": bad, "unit": "g"}],
            ),
            headers=AUTH,
        )
        assert response.status_code == 422
        assert f"'{bad}' is not a quantity" in response.json()["detail"]


@requires_db
async def test_a_non_positive_selling_price_is_refused_with_a_sentence(api):
    for bad in ("0", "-17"):
        response = await api.post(
            "/api/menu-items", json={"name": "Karak", "selling_price": bad}, headers=AUTH
        )
        assert response.status_code == 422
        assert f"'{bad}' is not a selling price" in response.json()["detail"]


@requires_db
async def test_an_empty_recipe_is_refused_at_the_door(api, db):
    """D4: a version with zero components would sum to 0 and read as a
    100%-margin plate. Refused here; WP-61 refuses the maths for versions
    that predate the door."""
    item = await _item(api)
    response = await api.post(
        f"/api/menu-items/{item['id']}/recipe",
        json={"yield_portions": "40", "components": []},
        headers=AUTH,
    )
    assert response.status_code == 422
    assert "at least one component" in response.json()["detail"]


@requires_db
async def test_a_duplicate_live_name_is_refused(api):
    await _item(api, name="Karak Tea")
    response = await api.post(
        "/api/menu-items", json={"name": "Karak Tea", "selling_price": "5.00"}, headers=AUTH
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


@requires_db
async def test_a_blank_name_is_refused(api):
    response = await api.post(
        "/api/menu-items", json={"name": "   ", "selling_price": "5.00"}, headers=AUTH
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "a menu item needs a name"


@requires_db
async def test_two_cups_of_milk_are_refused_with_a_sentence(api, db):
    """PRD §16: a karak cup is a serving vessel, not a measure. The consultant
    converts during loading; the door refuses rather than guesses."""
    milk = await _ingredient(db, "Fresh Milk", "ml")
    item = await _item(api)
    response = await api.post(
        f"/api/menu-items/{item['id']}/recipe",
        json=_recipe_body(
            milk,
            components=[
                {"ingredient_id": milk, "qty": "2", "unit": "cups", "source_text": "2 cups milk"}
            ],
        ),
        headers=AUTH,
    )
    assert response.status_code == 422
    assert "'cups' is not a measure this system converts" in response.json()["detail"]


@requires_db
async def test_a_carton_is_a_container_not_an_amount(api, db):
    flour = await _ingredient(db, "Refined Flour", "g")
    item = await _item(api)
    response = await api.post(
        f"/api/menu-items/{item['id']}/recipe",
        json=_recipe_body(flour, components=[{"ingredient_id": flour, "qty": "1", "unit": "ctn"}]),
        headers=AUTH,
    )
    assert response.status_code == 422
    assert "a ctn is a container, not an amount" in response.json()["detail"]


@requires_db
async def test_a_volume_unit_on_a_weight_material_is_refused(api, db):
    """The M5 approval gate's rule, one layer up: a material has one
    dimension, and a millilitre of flour is wrong in a way no later
    arithmetic can notice."""
    flour = await _ingredient(db, "Refined Flour", "g")
    item = await _item(api)
    response = await api.post(
        f"/api/menu-items/{item['id']}/recipe",
        json=_recipe_body(flour, components=[{"ingredient_id": flour, "qty": "50", "unit": "ml"}]),
        headers=AUTH,
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "measured by volume" in detail and "measured by weight" in detail


@requires_db
async def test_another_tenants_ingredient_reads_as_not_found(api, db):
    """The API's answer has a reason in it; Postgres refuses regardless."""
    other_tenant = await db.pool.fetchval(
        "insert into tenants (name, currency) values ('Other', 'AED') returning id"
    )
    foreign = await _ingredient(db, "Their Flour", "g", tenant_id=str(other_tenant))
    item = await _item(api)
    response = await api.post(
        f"/api/menu-items/{item['id']}/recipe", json=_recipe_body(foreign), headers=AUTH
    )
    assert response.status_code == 404
    assert "ingredient not found" in response.json()["detail"]


@requires_db
async def test_postgres_refuses_a_cross_tenant_component_whatever_the_code_missed(db):
    """The 0012 composite-key shape on recipe_components: tenancy fails at
    the write, in the database, not in a code path remembering to check."""
    other_tenant = await db.pool.fetchval(
        "insert into tenants (name, currency) values ('Other', 'AED') returning id"
    )
    foreign = await _ingredient(db, "Their Flour", "g", tenant_id=str(other_tenant))
    item_id = await db.pool.fetchval(
        "insert into menu_items (tenant_id, name, selling_price) values ($1, 'Karak', 5) "
        "returning id",
        DEMO_TENANT_ID,
    )
    recipe_id = await db.pool.fetchval(
        "insert into recipes (tenant_id, menu_item_id, version, yield_portions) "
        "values ($1, $2, 1, 40) returning id",
        DEMO_TENANT_ID,
        item_id,
    )
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await db.pool.execute(
            "insert into recipe_components (tenant_id, recipe_id, position, ingredient_id, "
            "qty, unit) values ($1, $2, 0, $3, 220, 'g')",
            DEMO_TENANT_ID,
            recipe_id,
            foreign,
        )


# -- archive: the reverse gear -------------------------------------------------


@requires_db
async def test_archive_and_unarchive_round_trip_with_audit_rows(api, db):
    item = await _item(api)
    response = await api.post(f"/api/menu-items/{item['id']}/archive", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["archived_at"] is not None

    # Archived is read-only: the item is off every screen, so its history
    # must not grow behind the ranking's back.
    response = await api.patch(
        f"/api/menu-items/{item['id']}/price", json={"selling_price": "6.00"}, headers=AUTH
    )
    assert response.status_code == 409
    assert "archived" in response.json()["detail"]

    # A second archive click is answered, not double-recorded.
    response = await api.post(f"/api/menu-items/{item['id']}/archive", headers=AUTH)
    assert response.status_code == 409

    response = await api.post(f"/api/menu-items/{item['id']}/unarchive", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["archived_at"] is None

    actions = [row["action"] for row in await _audit(db, item["id"])]
    assert actions == ["menu_item.created", "menu_item.archived", "menu_item.unarchived"]


@requires_db
async def test_archiving_frees_the_name_and_unarchiving_into_it_is_refused(api):
    """The 0015 partial index: one live 'Karak Tea' at a time, but an archived
    one keeps its history under the same name."""
    first = await _item(api, name="Karak Tea")
    await api.post(f"/api/menu-items/{first['id']}/archive", headers=AUTH)
    await _item(api, name="Karak Tea")  # the successor takes the name

    response = await api.post(f"/api/menu-items/{first['id']}/unarchive", headers=AUTH)
    assert response.status_code == 409
    assert "already called 'Karak Tea'" in response.json()["detail"]


# -- audit: every write names its actor ---------------------------------------


@requires_db
async def test_every_write_lands_one_audit_row_naming_console(api, db):
    tea = await _ingredient(db, "CTC Black Tea")
    item = await _item(api)
    await api.post(f"/api/menu-items/{item['id']}/recipe", json=_recipe_body(tea), headers=AUTH)
    await api.patch(
        f"/api/menu-items/{item['id']}/price", json={"selling_price": "6.00"}, headers=AUTH
    )

    rows = await _audit(db, item["id"])
    assert [row["action"] for row in rows] == [
        "menu_item.created",
        "recipe.version_created",
        "menu_item.price_changed",
    ]
    assert all(row["actor"] == TEST_ACTOR for row in rows)
    price_change = rows[-1]["detail"]
    assert price_change["previous_selling_price"] == "5.000"
    assert price_change["selling_price"] == "6.000"


@requires_db
async def test_resending_the_same_price_writes_no_history(api, db):
    """Selling-price history is the audit trail (§2 rule 8), so a no-change
    PATCH must not mint a history of nothing changing."""
    item = await _item(api, price="5.00")
    response = await api.patch(
        f"/api/menu-items/{item['id']}/price", json={"selling_price": "5.00"}, headers=AUTH
    )
    assert response.status_code == 200
    actions = [row["action"] for row in await _audit(db, item["id"])]
    assert actions == ["menu_item.created"]


# -- the paste-safe apply file (the M5 lesson, D6) -----------------------------


@requires_db
async def test_apply_file_brings_a_0014_database_to_0016():
    """Docs/apply_m6_migrations.sql, run on a database at 0014, lands the menu
    tables with the 0016 category column - proven by doing it, not by
    comparing file text."""
    conn = await asyncpg.connect(TEST_DATABASE_URL)
    try:
        await conn.execute("drop schema public cascade; create schema public;")
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if migration.name.startswith(("0015", "0016")):
                continue
            await conn.execute(migration.read_text())
        await conn.execute(SEED_FILE.read_text())

        needs_0015 = await conn.fetchval("select to_regclass('public.menu_items') is null")
        assert needs_0015 is True

        await conn.execute(APPLY_FILE.read_text())

        needs_0015 = await conn.fetchval("select to_regclass('public.menu_items') is null")
        assert needs_0015 is False
        # And the write the schema exists for works end to end, category included.
        await conn.execute(
            "insert into menu_items (tenant_id, name, selling_price, category) "
            "values ($1, 'Karak', 5, 'Tea Corner')",
            DEMO_TENANT_ID,
        )
    finally:
        await conn.close()


@requires_db
async def test_category_file_brings_a_0015_database_to_0016():
    """The live project ran 0015 before the design review added the category
    column, so Docs/apply_m6_category.sql is its catch-up - proven the same
    way, on a database stopped at 0015."""
    conn = await asyncpg.connect(TEST_DATABASE_URL)
    try:
        await conn.execute("drop schema public cascade; create schema public;")
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if migration.name.startswith("0016"):
                continue
            await conn.execute(migration.read_text())
        await conn.execute(SEED_FILE.read_text())

        needs_0016 = await conn.fetchval(
            "select not exists (select 1 from information_schema.columns "
            "where table_name = 'menu_items' and column_name = 'category')"
        )
        assert needs_0016 is True

        await conn.execute(CATEGORY_FILE.read_text())

        await conn.execute(
            "insert into menu_items (tenant_id, name, selling_price, category) "
            "values ($1, 'Karak', 5, 'Tea Corner')",
            DEMO_TENANT_ID,
        )
    finally:
        await conn.close()


@requires_db
async def test_a_category_travels_from_creation_to_every_read(api):
    """The menu's own section (0016, design D9): stored as typed, carried on
    the list and the detail, and never invented when the menu prints none."""
    response = await api.post(
        "/api/menu-items",
        json={"name": "Karak Tea", "selling_price": "5.00", "category": "Tea Corner"},
        headers=AUTH,
    )
    assert response.status_code == 201, response.text
    assert response.json()["category"] == "Tea Corner"

    response = await api.post(
        "/api/menu-items", json={"name": "Special Item", "selling_price": "9.00"}, headers=AUTH
    )
    assert response.json()["category"] is None

    listed = {
        row["name"]: row["category"]
        for row in (await api.get("/api/menu-items", headers=AUTH)).json()["menu_items"]
    }
    assert listed == {"Karak Tea": "Tea Corner", "Special Item": None}
