"""M5 WP-52: raw materials - one shelf per ingredient (plan.md §8 M5).

The catalog fills itself from invoices but is scoped to a supplier, so the same
material bought from two suppliers is two rows with two price histories. These
tests cover the layer that joins them, and the rule that governs the whole
milestone: the matcher **proposes**, a person approves, and nothing merges on
its own. A wrong merge corrupts the cost of every menu item using that
material, and unlike a bad extraction there is no photo to check it against -
so every approve, reject, remap and unmap has to land one audit row naming who
did it, and there has to be a way back.
"""

import datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from faida_api.api import router as api_router
from faida_api.matching import propose_ingredients

from .conftest import AUTH, DEMO_TENANT_ID, TEST_ACTOR, requires_db, wire_auth

# -- propose_ingredients (no DB) ----------------------------------------------

INGREDIENTS = [
    {"id": "1", "name": "Milk Powder", "base_unit": "g"},
    {"id": "2", "name": "Evaporated Milk", "base_unit": "ml"},
    {"id": "3", "name": "Basmati Rice", "base_unit": "g"},
    {"id": "4", "name": "Chicken Breast", "base_unit": "g"},
]


def test_proposals_ignore_pack_size_where_snapping_insists_on_it():
    """The one place mapping must differ from snapping. `snap_item` vetoes
    across pack sizes, because a 2.5 kg sack and a 500 g pouch are two catalog
    rows with two price histories. They are one *material*, so the pack sizes
    come out of both names before scoring and there is no veto."""
    for printed in ("Milk Powder 2.5kg", "Milk Powder 500g", "MILK PWDR 2.5KG NIDO"):
        assert [row["name"] for row in propose_ingredients(INGREDIENTS, printed)] == ["Milk Powder"]
    # A multiplier carton reads through to the same material too (WP-51).
    assert [row["name"] for row in propose_ingredients(INGREDIENTS, "EVAP MILK 48x400ML")] == [
        "Evaporated Milk"
    ]


def test_two_confusable_foods_are_not_proposed_for_each_other():
    """Chickpeas scores 0.696 against chicken breast - the same as a genuine
    match elsewhere - so the threshold breaks the tie toward silence. Offering
    those as one material is the merge a tired consultant approves and nobody
    catches afterwards."""
    assert propose_ingredients(INGREDIENTS, "Chickpeas 1kg") == []
    assert propose_ingredients(INGREDIENTS, "Tomato Paste 800g") == []


def test_a_rejected_material_is_dropped_rather_than_ranked_last():
    """Re-offering an answer a person already refused is how an approval queue
    teaches people to stop reading it."""
    assert [row["name"] for row in propose_ingredients(INGREDIENTS, "Milk Powder 2.5kg")] == [
        "Milk Powder"
    ]
    assert propose_ingredients(INGREDIENTS, "Milk Powder 2.5kg", rejected_ids=["1"]) == []


# -- the mapping endpoints (real Postgres) ------------------------------------


@pytest.fixture
def api(settings, db):
    app = FastAPI()
    app.include_router(api_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _supplier(db, name: str) -> str:
    return str(
        await db.pool.fetchval(
            "insert into suppliers (tenant_id, name) values ($1, $2) returning id",
            DEMO_TENANT_ID,
            name,
        )
    )


async def _item(db, supplier_id: str, canonical_name: str, pack_size: str | None = None) -> str:
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


async def _confirmed_spend(
    db, item_id: str, line_total: Decimal, status: str = "confirmed"
) -> None:
    """One invoice line against a pack, so the queue has money to rank by."""
    document_id = await db.pool.fetchval(
        "insert into documents (tenant_id, source, status) values ($1, 'manual', 'extracted') "
        "returning id",
        DEMO_TENANT_ID,
    )
    invoice_id = await db.pool.fetchval(
        "insert into invoices (tenant_id, document_id, status, total) values ($1, $2, $3, $4) "
        "returning id",
        DEMO_TENANT_ID,
        document_id,
        status,
        line_total,
    )
    await db.pool.execute(
        """
        insert into invoice_lines (tenant_id, invoice_id, position, raw_name, supplier_item_id,
                                   qty, unit_price, line_total)
        values ($1, $2, 0, 'line', $3, 1, $4, $4)
        """,
        DEMO_TENANT_ID,
        invoice_id,
        item_id,
        line_total,
    )


async def _audit(db, item_id: str) -> list:
    return await db.pool.fetch(
        "select actor, action, detail from audit_events where subject_id = $1 order by id", item_id
    )


async def _delivery(
    db,
    item_id: str,
    *,
    supplier_id: str,
    pack_size: str,
    unit_price: Decimal,
    invoice_date: str | None = "2026-07-06",
    raw_name: str = "Milk Powder",
    confirm: bool = True,
) -> str:
    """One delivery of a pack, put through the **real confirm path** so its
    cost is frozen by the same transaction that confirms it (WP-50/WP-53).

    Seeding the cost column directly would test the query and not the product;
    every material price below therefore rests on a line an invoice actually
    produced."""
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
        None if invoice_date is None else datetime.date.fromisoformat(invoice_date),
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
    if confirm:
        assert (
            await db.confirm_invoice(invoice_id, tenant_id=DEMO_TENANT_ID, actor="console") is True
        )
    return invoice_id


async def _materials(api) -> list[dict]:
    return (await api.get("/api/ingredients", headers=AUTH)).json()["ingredients"]


async def _price(api, name: str = "Milk Powder") -> dict | None:
    return next(row for row in await _materials(api) if row["name"] == name)["price"]


@requires_db
async def test_the_queue_ranks_unmapped_packs_by_money_spent(api, db):
    """Most money first, because that is the order in which a wrong cost hurts.
    Only confirmed invoices count - an unconfirmed one must not move the
    consultant's queue any more than it moves price memory."""
    supplier_id = await _supplier(db, "Gulf Foods Trading L.L.C.")
    cheap = await _item(db, supplier_id, "Cardamom Powder 500g", "500g")
    dear = await _item(db, supplier_id, "Milk Powder 2.5kg", "2.5kg")
    draft_only = await _item(db, supplier_id, "Saffron 10g", "10g")
    await _confirmed_spend(db, cheap, Decimal("240.00"))
    await _confirmed_spend(db, dear, Decimal("5050.00"))
    await _confirmed_spend(db, draft_only, Decimal("9999.00"), status="awaiting_confirm")

    body = (await api.get("/api/supplier-items/unmapped", headers=AUTH)).json()
    ranked = [(row["canonical_name"], row["spend"]) for row in body["items"]]
    assert ranked[0] == ("Milk Powder 2.5kg", "5050.00")
    assert ranked[1] == ("Cardamom Powder 500g", "240.00")
    # Present, but worth nothing yet: its only invoice is unconfirmed.
    assert ("Saffron 10g", "0") in ranked
    assert {row["id"] for row in body["items"]} == {cheap, dear, draft_only}


@requires_db
async def test_approving_creates_the_material_and_names_who_did_it(api, db):
    """The first approval on a fresh tenant has to be able to create the
    material: the matcher can only propose materials that already exist."""
    supplier_id = await _supplier(db, "Gulf Foods Trading L.L.C.")
    item_id = await _item(db, supplier_id, "Milk Powder 2.5kg", "2.5kg")

    response = await api.post(
        f"/api/supplier-items/{item_id}/ingredient", json={"name": "Milk Powder"}, headers=AUTH
    )
    assert response.status_code == 200
    ingredient = response.json()["ingredient"]
    assert ingredient["name"] == "Milk Powder"
    # Read off the pack rather than asked for: "2.5kg" is a mass.
    assert ingredient["base_unit"] == "g"

    events = await _audit(db, item_id)
    assert len(events) == 1
    assert events[0]["actor"] == TEST_ACTOR
    assert events[0]["action"] == "supplier_item.mapped"
    assert events[0]["detail"]["ingredient_id"] == ingredient["id"]
    # And it has left the queue.
    body = (await api.get("/api/supplier-items/unmapped", headers=AUTH)).json()
    assert body["items"] == []


@requires_db
async def test_two_suppliers_milk_powder_becomes_one_material(api, db):
    """The milestone's whole point, in the smallest form that shows it."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    madina = await _supplier(db, "Al Madina Trading Co.")
    gulf_item = await _item(db, gulf, "Milk Powder 2.5kg", "2.5kg")
    madina_item = await _item(db, madina, "MILK PWDR 500G NIDO", "500g")

    created = await api.post(
        f"/api/supplier-items/{gulf_item}/ingredient", json={"name": "Milk Powder"}, headers=AUTH
    )
    ingredient_id = created.json()["ingredient"]["id"]

    # The matcher now proposes it for the other supplier's pack, at a different
    # pack size, under a different printed name.
    queue = (await api.get("/api/supplier-items/unmapped", headers=AUTH)).json()
    row = next(item for item in queue["items"] if item["id"] == madina_item)
    assert [p["name"] for p in row["proposals"]] == ["Milk Powder"]

    assert (
        await api.post(
            f"/api/supplier-items/{madina_item}/ingredient",
            json={"ingredient_id": ingredient_id},
            headers=AUTH,
        )
    ).status_code == 200

    materials = (await api.get("/api/ingredients", headers=AUTH)).json()["ingredients"]
    assert len(materials) == 1
    assert materials[0]["pack_count"] == 2
    assert {p["supplier_name"] for p in materials[0]["packs"]} == {
        "Gulf Foods Trading L.L.C.",
        "Al Madina Trading Co.",
    }


@requires_db
async def test_a_millilitre_pack_cannot_be_mapped_onto_a_gram_material(api, db):
    """A material has one dimension. Mapping across them is wrong in a way no
    later arithmetic can notice, so it is refused with a reason rather than
    coerced into something."""
    supplier_id = await _supplier(db, "Gulf Foods Trading L.L.C.")
    powder = await _item(db, supplier_id, "Milk Powder 2.5kg", "2.5kg")
    liquid = await _item(db, supplier_id, "Evaporated Milk 400ml", "400ml")
    created = await api.post(
        f"/api/supplier-items/{powder}/ingredient", json={"name": "Milk Powder"}, headers=AUTH
    )
    ingredient_id = created.json()["ingredient"]["id"]

    response = await api.post(
        f"/api/supplier-items/{liquid}/ingredient",
        json={"ingredient_id": ingredient_id},
        headers=AUTH,
    )
    assert response.status_code == 422
    # Plain English, not unit codes: the refusal lands on the screen, where the
    # no-jargon display rule applies (plan.md §3).
    detail = response.json()["detail"]
    assert "measured by volume" in detail
    assert "measured by weight" in detail
    assert "Milk Powder" in detail
    assert await _audit(db, liquid) == []


@requires_db
async def test_a_bare_carton_has_to_be_told_what_it_measures(api, db):
    """units.py refuses to guess what is inside a carton, so the approval asks
    instead of picking. Answering is allowed; guessing is not."""
    supplier_id = await _supplier(db, "Gulf Foods Trading L.L.C.")
    item_id = await _item(db, supplier_id, "Chicken Carton", "1 ctn")

    refused = await api.post(
        f"/api/supplier-items/{item_id}/ingredient", json={"name": "Chicken"}, headers=AUTH
    )
    assert refused.status_code == 422
    assert "by weight, by volume or by the piece" in refused.json()["detail"]

    accepted = await api.post(
        f"/api/supplier-items/{item_id}/ingredient",
        json={"name": "Chicken", "base_unit": "g"},
        headers=AUTH,
    )
    assert accepted.status_code == 200
    assert accepted.json()["ingredient"]["base_unit"] == "g"


@requires_db
async def test_a_pack_cannot_be_mapped_to_another_tenants_material(api, db):
    """RLS is deferred to M7 and the demo API holds one shared token, so
    nothing above the database would have caught this. The composite foreign
    key in 0012 is the real guard; the endpoint answers with a reason."""
    other_tenant = await db.pool.fetchval(
        "insert into tenants (name) values ('Other Chain') returning id"
    )
    foreign_ingredient = str(
        await db.pool.fetchval(
            "insert into ingredients (tenant_id, name, base_unit) values ($1, 'Milk Powder', 'g') "
            "returning id",
            other_tenant,
        )
    )
    supplier_id = await _supplier(db, "Gulf Foods Trading L.L.C.")
    item_id = await _item(db, supplier_id, "Milk Powder 2.5kg", "2.5kg")

    response = await api.post(
        f"/api/supplier-items/{item_id}/ingredient",
        json={"ingredient_id": foreign_ingredient},
        headers=AUTH,
    )
    assert response.status_code == 404
    assert await _audit(db, item_id) == []


@requires_db
async def test_a_rejected_material_stops_being_proposed_but_can_still_be_approved(api, db):
    """The rejection is the record - there is no second table holding it - and
    latest event wins, so changing your mind works."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    madina = await _supplier(db, "Al Madina Trading Co.")
    mapped = await _item(db, gulf, "Milk Powder 2.5kg", "2.5kg")
    candidate = await _item(db, madina, "Milk Powder 500g", "500g")
    created = await api.post(
        f"/api/supplier-items/{mapped}/ingredient", json={"name": "Milk Powder"}, headers=AUTH
    )
    ingredient_id = created.json()["ingredient"]["id"]

    def proposals(queue):
        row = next(item for item in queue["items"] if item["id"] == candidate)
        return [p["name"] for p in row["proposals"]]

    assert proposals((await api.get("/api/supplier-items/unmapped", headers=AUTH)).json()) == [
        "Milk Powder"
    ]

    rejected = await api.post(
        f"/api/supplier-items/{candidate}/ingredient/reject",
        json={"ingredient_id": ingredient_id},
        headers=AUTH,
    )
    assert rejected.status_code == 200
    assert proposals((await api.get("/api/supplier-items/unmapped", headers=AUTH)).json()) == []
    events = await _audit(db, candidate)
    assert [e["action"] for e in events] == ["supplier_item.mapping_rejected"]
    assert events[0]["actor"] == TEST_ACTOR

    # A rejection suppresses the suggestion, it does not forbid the answer.
    assert (
        await api.post(
            f"/api/supplier-items/{candidate}/ingredient",
            json={"ingredient_id": ingredient_id},
            headers=AUTH,
        )
    ).status_code == 200


@requires_db
async def test_a_wrong_merge_is_undone_on_the_same_screen(api, db):
    """The reverse gear. This is the milestone's stated worst case, and an
    approval gate without one leaves a consultant asking an engineer."""
    supplier_id = await _supplier(db, "Gulf Foods Trading L.L.C.")
    item_id = await _item(db, supplier_id, "Chicken Breast 10kg", "10kg")
    created = await api.post(
        f"/api/supplier-items/{item_id}/ingredient", json={"name": "Chickpeas"}, headers=AUTH
    )
    wrong_id = created.json()["ingredient"]["id"]

    undone = await api.delete(f"/api/supplier-items/{item_id}/ingredient", headers=AUTH)
    assert undone.status_code == 200
    assert undone.json()["ingredient"] is None

    # Back in the queue, and the whole story is on the record.
    queue = (await api.get("/api/supplier-items/unmapped", headers=AUTH)).json()
    assert [row["id"] for row in queue["items"]] == [item_id]
    events = await _audit(db, item_id)
    assert [e["action"] for e in events] == ["supplier_item.mapped", "supplier_item.unmapped"]
    assert events[1]["detail"]["previous_ingredient_id"] == wrong_id

    # Unmapping twice is refused rather than silently writing a second event.
    assert (
        await api.delete(f"/api/supplier-items/{item_id}/ingredient", headers=AUTH)
    ).status_code == 409

    # And remapping to the right material records what it replaced.
    remapped = await api.post(
        f"/api/supplier-items/{item_id}/ingredient", json={"name": "Chicken Breast"}, headers=AUTH
    )
    assert remapped.status_code == 200
    assert remapped.json()["ingredient"]["name"] == "Chicken Breast"


@requires_db
async def test_the_mapping_endpoints_refuse_an_unauthorized_caller(api, db):
    supplier_id = await _supplier(db, "Gulf Foods Trading L.L.C.")
    item_id = await _item(db, supplier_id, "Milk Powder 2.5kg", "2.5kg")
    assert (await api.get("/api/supplier-items/unmapped")).status_code == 401
    assert (await api.get("/api/ingredients")).status_code == 401
    assert (
        await api.post(f"/api/supplier-items/{item_id}/ingredient", json={"name": "Milk Powder"})
    ).status_code == 401
    assert (await api.delete(f"/api/supplier-items/{item_id}/ingredient")).status_code == 401


# -- WP-54: one material, one price per kilo, derived and never stored ---------


@requires_db
async def test_two_suppliers_and_three_packs_read_as_one_price_per_kilo(api, db):
    """**The milestone's done-when.** Milk powder bought from two suppliers in
    three pack sizes is one material at one price per kilo, and every figure
    inside that price traces to the invoice line - and so to the photo - it
    came from.

    Latest, not cheapest and not averaged: the 25 kg sack is much cheaper per
    kilo and the 500 g pouch dearer, and neither is the answer. What was paid
    most recently is."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    madina = await _supplier(db, "Al Madina Trading Co.")
    sack = await _item(db, gulf, "Milk Powder 2.5kg", "2.5kg")
    pouch = await _item(db, gulf, "Milk Powder 500g", "500g")
    bulk = await _item(db, madina, "MILK PWDR 25KG", "25kg")

    await _delivery(
        db,
        pouch,
        supplier_id=gulf,
        pack_size="500g",
        unit_price=Decimal("11.00"),
        invoice_date="2026-07-02",
    )
    await _delivery(
        db,
        bulk,
        supplier_id=madina,
        pack_size="25kg",
        unit_price=Decimal("420.00"),
        invoice_date="2026-07-04",
    )
    newest = await _delivery(
        db,
        sack,
        supplier_id=gulf,
        pack_size="2.5kg",
        unit_price=Decimal("50.50"),
        invoice_date="2026-07-06",
    )

    created = await api.post(
        f"/api/supplier-items/{sack}/ingredient", json={"name": "Milk Powder"}, headers=AUTH
    )
    ingredient_id = created.json()["ingredient"]["id"]
    for item_id in (pouch, bulk):
        assert (
            await api.post(
                f"/api/supplier-items/{item_id}/ingredient",
                json={"ingredient_id": ingredient_id},
                headers=AUTH,
            )
        ).status_code == 200

    materials = await _materials(api)
    assert len(materials) == 1
    assert materials[0]["pack_count"] == 3

    price = materials[0]["price"]
    assert price["per_display_unit"] == "20.20"
    assert price["display_unit"] == "kg"
    assert price["supplier_name"] == "Gulf Foods Trading L.L.C."
    assert price["purchased_on"] == "2026-07-06"
    # The answer names the line it came from, which is what puts the photo one
    # click away and what M6 will name as a plate's cost snapshot.
    assert price["invoice_id"] == newest
    assert price["invoice_line_id"]
    assert price["pack"] == "2.5kg"
    # Never green: nothing anywhere cross-checks a pack size (C9).
    assert price["quality"] == "reliable_with_limitations"

    # And each pack carries its own, which is the comparison the merge exists
    # to make possible: the same material at 16.80, 20.20 and 22.00 a kilo.
    per_kilo = {
        pack["canonical_name"]: pack["cost"]["per_display_unit"] for pack in materials[0]["packs"]
    }
    assert per_kilo == {
        "Milk Powder 2.5kg": "20.20",
        "Milk Powder 500g": "22.00",
        "MILK PWDR 25KG": "16.80",
    }


@requires_db
async def test_a_newer_invoice_moves_the_price_and_an_older_one_does_not(api, db):
    """PRD §19: the cost is what you last paid. An owner handing over a stack
    of last month's invoices during onboarding must not overwrite this month's
    real cost - silently, in the layer where nothing downstream can notice."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    madina = await _supplier(db, "Al Madina Trading Co.")
    sack = await _item(db, gulf, "Milk Powder 2.5kg", "2.5kg")
    other = await _item(db, madina, "Milk Powder 500g", "500g")
    await _delivery(
        db,
        sack,
        supplier_id=gulf,
        pack_size="2.5kg",
        unit_price=Decimal("50.50"),
        invoice_date="2026-07-06",
    )
    created = await api.post(
        f"/api/supplier-items/{sack}/ingredient", json={"name": "Milk Powder"}, headers=AUTH
    )
    ingredient_id = created.json()["ingredient"]["id"]
    await api.post(
        f"/api/supplier-items/{other}/ingredient",
        json={"ingredient_id": ingredient_id},
        headers=AUTH,
    )
    assert (await _price(api))["per_display_unit"] == "20.20"

    # An older delivery from the other supplier: cheaper per kilo, and ignored.
    await _delivery(
        db,
        other,
        supplier_id=madina,
        pack_size="500g",
        unit_price=Decimal("8.00"),
        invoice_date="2026-06-30",
    )
    assert (await _price(api))["per_display_unit"] == "20.20"

    # A newer one from the same supplier moves it.
    await _delivery(
        db,
        other,
        supplier_id=madina,
        pack_size="500g",
        unit_price=Decimal("12.00"),
        invoice_date="2026-07-11",
    )
    moved = await _price(api)
    assert moved["per_display_unit"] == "24.00"
    assert moved["supplier_name"] == "Al Madina Trading Co."


async def _confirmed_two_line_invoice(
    db,
    item_id: str,
    *,
    supplier_id: str,
    invoice_date: str,
    lines: list[tuple[Decimal, Decimal]],
) -> str:
    """One confirmed invoice with several lines on the same pack: (qty,
    unit_price) per line, positions in page order, totals consistent."""
    document_id = await db.pool.fetchval(
        "insert into documents (tenant_id, source, status) values ($1, 'manual', 'extracted') "
        "returning id",
        DEMO_TENANT_ID,
    )
    total = sum(qty * price for qty, price in lines)
    invoice_id = await db.pool.fetchval(
        """
        insert into invoices (tenant_id, document_id, supplier_id, status, total, invoice_date)
        values ($1, $2, $3, 'awaiting_confirm', $4, $5)
        returning id::text
        """,
        DEMO_TENANT_ID,
        document_id,
        supplier_id,
        total,
        datetime.date.fromisoformat(invoice_date),
    )
    for position, (qty, unit_price) in enumerate(lines):
        await db.pool.execute(
            """
            insert into invoice_lines (tenant_id, invoice_id, position, raw_name,
                                       supplier_item_id, qty, pack_size, unit_price, line_total)
            values ($1, $2, $3, 'Avocado', $4, $5, '2.5kg', $6, $7)
            """,
            DEMO_TENANT_ID,
            invoice_id,
            position,
            item_id,
            qty,
            unit_price,
            qty * unit_price,
        )
    assert await db.confirm_invoice(invoice_id, tenant_id=DEMO_TENANT_ID, actor="console") is True
    return invoice_id


@requires_db
async def test_a_credit_line_never_wins_newest_and_ties_break_on_position(api, db):
    """A return is not a purchase, and a tie is not a coin flip (found by the
    M6 eng review's outside voice, 2026-08-29, verified against this query).

    EDGE-01's shape: one page prints an avocado purchase and its partial
    credit, and both lines are costed. The credit's unit price is lower, and
    before the qty filter the material's price per kilo was whichever line's
    uuid sorted last - a nondeterministic number on the materials screen."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    avocado = await _item(db, gulf, "Avocado 2.5kg", "2.5kg")
    await _confirmed_two_line_invoice(
        db,
        avocado,
        supplier_id=gulf,
        invoice_date="2026-07-06",
        lines=[(Decimal("2"), Decimal("50.50")), (Decimal("-1"), Decimal("40.00"))],
    )
    assert (
        await api.post(
            f"/api/supplier-items/{avocado}/ingredient", json={"name": "Avocado"}, headers=AUTH
        )
    ).status_code == 200

    # 50.50 / 2.5 kg, never the credit's 16.00 - and the same on every run.
    assert (await _price(api, "Avocado"))["per_display_unit"] == "20.20"

    # A newer page prints the same pack twice at two prices (a bulk row and a
    # spot row). The winner is the later printed line, by position - not uuid.
    await _confirmed_two_line_invoice(
        db,
        avocado,
        supplier_id=gulf,
        invoice_date="2026-07-08",
        lines=[(Decimal("1"), Decimal("48.00")), (Decimal("1"), Decimal("52.50"))],
    )
    assert (await _price(api, "Avocado"))["per_display_unit"] == "21.00"


@requires_db
async def test_the_price_follows_the_printed_date_not_the_order_things_were_confirmed(api, db):
    """The ordering key, pinned. Confirm time is a tie-breaker and nothing
    more.

    Here the older invoice is confirmed *second*, which is exactly what
    onboarding looks like: someone hands over a pile of paper and it goes
    through in whatever order it comes out of the envelope. Ranking by confirm
    time would take AED 17.60 a kilo - a June price - as today's cost."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    sack = await _item(db, gulf, "Milk Powder 2.5kg", "2.5kg")
    await api.post(
        f"/api/supplier-items/{sack}/ingredient", json={"name": "Milk Powder"}, headers=AUTH
    )

    await _delivery(
        db,
        sack,
        supplier_id=gulf,
        pack_size="2.5kg",
        unit_price=Decimal("50.50"),
        invoice_date="2026-07-06",
    )
    await _delivery(
        db,
        sack,
        supplier_id=gulf,
        pack_size="2.5kg",
        unit_price=Decimal("44.00"),
        invoice_date="2026-06-02",
    )

    price = await _price(api)
    assert price["per_display_unit"] == "20.20"
    assert price["purchased_on"] == "2026-07-06"


@requires_db
async def test_an_invoice_with_no_printed_date_falls_back_to_when_it_was_confirmed(api, db):
    """A date is not always on the paper, and it is never guessed (C3). The
    honest fallback is the only other thing we know about when the purchase
    happened - and the payload says which of the two it is, because "bought on"
    and "recorded on" are different claims."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    sack = await _item(db, gulf, "Milk Powder 2.5kg", "2.5kg")
    await api.post(
        f"/api/supplier-items/{sack}/ingredient", json={"name": "Milk Powder"}, headers=AUTH
    )
    await _delivery(
        db,
        sack,
        supplier_id=gulf,
        pack_size="2.5kg",
        unit_price=Decimal("50.50"),
        invoice_date=None,
    )

    price = await _price(api)
    assert price["invoice_date"] is None
    assert price["purchased_on"] == datetime.datetime.now(datetime.UTC).date().isoformat()


@requires_db
async def test_unmapping_a_wrongly_merged_pack_corrects_the_price_immediately(api, db):
    """The reason there is no `ingredient_costs` table. A wrong merge is this
    milestone's stated worst case; because the price is derived, undoing one
    corrects every figure above it with nothing left to rebuild - no refresh to
    remember, no projection to recompute, no stale row to find later."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    sack = await _item(db, gulf, "Milk Powder 2.5kg", "2.5kg")
    saffron = await _item(db, gulf, "Saffron Threads 10g", "10g")
    await _delivery(
        db,
        sack,
        supplier_id=gulf,
        pack_size="2.5kg",
        unit_price=Decimal("50.50"),
        invoice_date="2026-07-06",
    )
    await _delivery(
        db,
        saffron,
        supplier_id=gulf,
        pack_size="10g",
        unit_price=Decimal("522.50"),
        invoice_date="2026-07-09",
        raw_name="Saffron Threads",
    )

    created = await api.post(
        f"/api/supplier-items/{sack}/ingredient", json={"name": "Milk Powder"}, headers=AUTH
    )
    ingredient_id = created.json()["ingredient"]["id"]
    assert (await _price(api))["per_display_unit"] == "20.20"

    # The merge nobody should make: saffron onto milk powder. It is newer, so
    # it takes the price straight away - AED 52,250 a kilo of "milk powder".
    await api.post(
        f"/api/supplier-items/{saffron}/ingredient",
        json={"ingredient_id": ingredient_id},
        headers=AUTH,
    )
    assert (await _price(api))["per_display_unit"] == "52250.00"

    undone = await api.delete(f"/api/supplier-items/{saffron}/ingredient", headers=AUTH)
    assert undone.status_code == 200
    assert (await _price(api))["per_display_unit"] == "20.20"


@requires_db
async def test_a_material_nobody_has_bought_yet_has_no_price_rather_than_a_zero(api, db):
    """An empty answer is not a cheap one. Nothing has been confirmed against
    this pack, so there is no price to show and the screen has to say so."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    sack = await _item(db, gulf, "Milk Powder 2.5kg", "2.5kg")
    await api.post(
        f"/api/supplier-items/{sack}/ingredient", json={"name": "Milk Powder"}, headers=AUTH
    )
    materials = await _materials(api)
    assert materials[0]["price"] is None
    assert materials[0]["packs"][0]["cost"] is None


@requires_db
async def test_an_unconfirmed_invoice_never_sets_a_material_price(api, db):
    """The same rule that governs price memory (plan.md §5 layer 4): nothing an
    owner has not confirmed moves a number they will be shown. The cost column
    is written here by hand, so what this pins is the status filter itself and
    not merely that confirming is what writes costs."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    sack = await _item(db, gulf, "Milk Powder 2.5kg", "2.5kg")
    await api.post(
        f"/api/supplier-items/{sack}/ingredient", json={"name": "Milk Powder"}, headers=AUTH
    )
    invoice_id = await _delivery(
        db, sack, supplier_id=gulf, pack_size="2.5kg", unit_price=Decimal("50.50"), confirm=False
    )
    await db.pool.execute(
        """
        update invoice_lines set cost_per_base_unit = 0.0202, cost_base_unit = 'g',
                                 cost_basis = '{"quality": "reliable_with_limitations"}'
        where invoice_id = $1
        """,
        invoice_id,
    )
    assert (await _price(api)) is None


# -- WP-55: the costs that cannot be computed, and the sentence that clears one


async def _blocked(api) -> list[dict]:
    return (await api.get("/api/blocked-costs", headers=AUTH)).json()["blocked"]


async def _line_costs(db, item_id: str) -> list:
    return await db.pool.fetch(
        """
        select l.id, l.cost_per_base_unit, l.cost_base_unit, l.cost_basis
        from invoice_lines l where l.supplier_item_id = $1 order by l.id
        """,
        item_id,
    )


@requires_db
async def test_a_carton_appears_with_its_reason_and_the_invoice_it_came_from(api, db):
    """A cost that cannot be computed is a line on a screen, never a guessed
    number. `units.py` refuses to say what is inside a carton, so the product
    ends up here with the invoice behind it and a sentence a person can act
    on."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    carton = await _item(db, gulf, "Chicken Carton", "1 ctn")
    invoice_id = await _delivery(
        db,
        carton,
        supplier_id=gulf,
        pack_size="1 ctn",
        unit_price=Decimal("148.00"),
        raw_name="Chicken Carton",
    )

    rows = await _blocked(api)
    assert len(rows) == 1
    assert rows[0]["product_name"] == "Chicken Carton"
    assert rows[0]["blocked"] == "bare_container"
    assert rows[0]["reason"] == "Nothing on the invoice says how much one of these holds."
    assert rows[0]["invoice_id"] == invoice_id
    assert rows[0]["can_override"] is True
    assert rows[0]["spend"] == "148.00"


@requires_db
async def test_each_way_a_line_can_refuse_shows_its_own_reason_and_its_own_answer(api, db):
    """Six blockers, six sentences, and only some of them are a person's to
    answer. Offering a box to type in beside "the invoice does not show a
    price" would be a promise this screen cannot keep - no conversion supplies
    a number the paper never had."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    carton = await _item(db, gulf, "Chicken Carton", "1 ctn")
    zero = await _item(db, gulf, "Tomato Paste", "0kg")
    nameless = await _item(db, gulf, "Assorted Spices", "assorted")
    await _delivery(db, carton, supplier_id=gulf, pack_size="1 ctn", unit_price=Decimal("148.00"))
    await _delivery(db, zero, supplier_id=gulf, pack_size="0kg", unit_price=Decimal("90.00"))
    await _delivery(
        db, nameless, supplier_id=gulf, pack_size="assorted", unit_price=Decimal("40.00")
    )

    # And one with no quantity at all, which the confirm loop never costs.
    priceless = await _item(db, gulf, "Cardamom Powder", "500g")
    invoice_id = await _delivery(
        db,
        priceless,
        supplier_id=gulf,
        pack_size="500g",
        unit_price=Decimal("24.00"),
        confirm=False,
    )
    await db.pool.execute("update invoice_lines set qty = null where invoice_id = $1", invoice_id)
    await db.confirm_invoice(invoice_id, tenant_id=DEMO_TENANT_ID, actor="console")

    reasons = {
        row["product_name"]: (row["blocked"], row["can_override"]) for row in await _blocked(api)
    }
    assert reasons["Chicken Carton"] == ("bare_container", True)
    assert reasons["Tomato Paste"] == ("zero_pack", True)
    assert reasons["Assorted Spices"] == ("unparseable_pack", True)
    # A number nobody wrote down is not a conversion question.
    assert reasons["Cardamom Powder"] == ("missing_quantity", False)


@requires_db
async def test_one_answer_clears_every_line_of_that_product(api, db):
    """A carton bought five times is one question, answered once. Twelve
    identical rows is how a queue teaches people to stop reading it."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    carton = await _item(db, gulf, "Chicken Carton", "1 ctn")
    for day in ("2026-07-02", "2026-07-06", "2026-07-09"):
        await _delivery(
            db,
            carton,
            supplier_id=gulf,
            pack_size="1 ctn",
            unit_price=Decimal("148.00"),
            invoice_date=day,
        )

    rows = await _blocked(api)
    assert len(rows) == 1
    assert rows[0]["line_count"] == 3
    assert rows[0]["spend"] == "444.00"

    answered = await api.post(
        f"/api/supplier-items/{carton}/pack-size", json={"pack_size": "10 kg"}, headers=AUTH
    )
    assert answered.status_code == 200
    assert answered.json()["lines_costed"] == 3
    assert await _blocked(api) == []


@requires_db
async def test_an_answer_costs_the_lines_with_no_cost_and_leaves_the_others_byte_identical(api, db):
    """The rule stated rather than implied. Half of it is that answering the
    question changes something - without that the conversion does nothing until
    the next delivery arrives. The other half is that it changes **only** what
    had no answer: a figure someone has already read must not move under them
    because a colleague answered a question about a different box."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    carton = await _item(db, gulf, "Chicken Carton", "1 ctn")
    # The same product, once with a pack size printed on the line and once
    # without. Only the second is anybody's question.
    await _delivery(
        db,
        carton,
        supplier_id=gulf,
        pack_size="8kg",
        unit_price=Decimal("120.00"),
        invoice_date="2026-07-02",
    )
    await _delivery(
        db,
        carton,
        supplier_id=gulf,
        pack_size="1 ctn",
        unit_price=Decimal("148.00"),
        invoice_date="2026-07-06",
    )
    before = {
        row["id"]: (row["cost_per_base_unit"], row["cost_basis"])
        for row in await _line_costs(db, carton)
    }
    already_costed = [line_id for line_id, (cost, _) in before.items() if cost is not None]
    assert len(already_costed) == 1

    assert (
        await api.post(
            f"/api/supplier-items/{carton}/pack-size", json={"pack_size": "10kg"}, headers=AUTH
        )
    ).json()["lines_costed"] == 1

    after = {
        row["id"]: (row["cost_per_base_unit"], row["cost_basis"])
        for row in await _line_costs(db, carton)
    }
    # The line that had a cost is untouched, down to how it says it was made.
    assert after[already_costed[0]] == before[already_costed[0]]
    # And the one that had none now costs 148.00 / 10 kg = AED 14.80 a kilo.
    costed = next(value for line_id, value in after.items() if line_id not in already_costed)
    assert costed[0] == Decimal("0.01480000")
    # C9, automatically: a human supplied the pack, so no arithmetic checked it.
    assert costed[1]["quality"] == "estimated"
    assert costed[1]["pack_source"] == "override"
    assert costed[1]["pack"] == "10kg"


@requires_db
async def test_clearing_the_block_gives_the_material_a_price_that_reads_estimated(api, db):
    """End to end, and the reason the two halves of this work package ship
    together: an issue with no resolution is half a feature, and a resolution
    that does not move the number it was blocking is worse than none."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    carton = await _item(db, gulf, "Chicken Carton", "1 ctn")
    await _delivery(db, carton, supplier_id=gulf, pack_size="1 ctn", unit_price=Decimal("148.00"))
    await api.post(
        f"/api/supplier-items/{carton}/ingredient",
        json={"name": "Chicken", "base_unit": "g"},
        headers=AUTH,
    )
    # Mapped, bought, confirmed - and still no price, because nothing said how
    # much a carton holds.
    assert (await _price(api, "Chicken")) is None

    await api.post(
        f"/api/supplier-items/{carton}/pack-size", json={"pack_size": "10 kg"}, headers=AUTH
    )
    price = await _price(api, "Chicken")
    assert price["per_display_unit"] == "14.80"
    assert price["quality"] == "estimated"
    assert price["pack_source"] == "override"


@requires_db
async def test_an_answer_that_is_not_an_amount_is_refused(api, db):
    """`units.py` refuses to guess and so does this: "a big box" is the same
    non-answer the invoice gave, and storing it would make the next cost a
    guess wearing a person's name."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    carton = await _item(db, gulf, "Chicken Carton", "1 ctn")
    for answer in ("a big box", "1 carton", "0 kg", ""):
        refused = await api.post(
            f"/api/supplier-items/{carton}/pack-size", json={"pack_size": answer}, headers=AUTH
        )
        assert refused.status_code == 422, answer
        assert "10 kg" in refused.json()["detail"]
    assert (
        await db.pool.fetchval(
            "select pack_size_override from supplier_items where id = $1", carton
        )
        is None
    )


@requires_db
async def test_an_answer_that_contradicts_the_material_is_refused(api, db):
    """The same guard the approval gate has, in the other place a dimension can
    be wrong. A millilitre conversion feeding a material measured by weight is
    wrong in a way nothing downstream could ever see."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    carton = await _item(db, gulf, "Chicken Carton", "1 ctn")
    await api.post(
        f"/api/supplier-items/{carton}/ingredient",
        json={"name": "Chicken", "base_unit": "g"},
        headers=AUTH,
    )
    refused = await api.post(
        f"/api/supplier-items/{carton}/pack-size", json={"pack_size": "5 litres"}, headers=AUTH
    )
    assert refused.status_code == 422
    # Plain English on the screen, not unit codes.
    assert "measured by volume" in refused.json()["detail"]
    assert "measured by weight" in refused.json()["detail"]


@requires_db
async def test_the_audit_trail_is_the_conversion_s_version_history(api, db):
    """No `container_conversions` table: audit_events already records who said
    what and when, inside the transaction that did it (C8). A second home for
    the same fact is the duplication migration 0010 was written to delete."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    carton = await _item(db, gulf, "Chicken Carton", "1 ctn")
    await api.post(
        f"/api/supplier-items/{carton}/pack-size", json={"pack_size": "10 kg"}, headers=AUTH
    )
    await api.post(
        f"/api/supplier-items/{carton}/pack-size", json={"pack_size": "12 kg"}, headers=AUTH
    )

    events = await _audit(db, carton)
    assert [event["action"] for event in events] == [
        "supplier_item.pack_size_set",
        "supplier_item.pack_size_set",
    ]
    assert all(event["actor"] == TEST_ACTOR for event in events)
    assert events[0]["detail"] == {"pack_size": "10 kg", "previous_pack_size": None}
    assert events[1]["detail"] == {"pack_size": "12 kg", "previous_pack_size": "10 kg"}


@requires_db
async def test_a_corrected_conversion_does_not_rewrite_a_cost_someone_has_already_read(api, db):
    """The half of the rule that only bites when a person changes their mind.

    Correcting "10 kg" to "12 kg" leaves the line already costed at AED 14.80 a
    kilo exactly where it was, and the next delivery costs at 12.33. That is
    the plan's rule as written, and its cost is stated rather than hidden: a
    conversion entered wrongly is not retro-fixed, so the earlier figure stands
    with the audit trail showing both answers. The reason it is worth it is the
    other direction - a figure on a screen that moves under someone because a
    colleague answered a question about a different box, with nothing anywhere
    showing that it did."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    carton = await _item(db, gulf, "Chicken Carton", "1 ctn")
    await _delivery(
        db,
        carton,
        supplier_id=gulf,
        pack_size="1 ctn",
        unit_price=Decimal("148.00"),
        invoice_date="2026-07-02",
    )
    await api.post(
        f"/api/supplier-items/{carton}/pack-size", json={"pack_size": "10 kg"}, headers=AUTH
    )
    first = await _line_costs(db, carton)
    assert [row["cost_per_base_unit"] for row in first] == [Decimal("0.01480000")]

    corrected = await api.post(
        f"/api/supplier-items/{carton}/pack-size", json={"pack_size": "12 kg"}, headers=AUTH
    )
    assert corrected.json()["lines_costed"] == 0
    assert await _line_costs(db, carton) == first

    # The new answer governs everything after it.
    await _delivery(
        db,
        carton,
        supplier_id=gulf,
        pack_size="1 ctn",
        unit_price=Decimal("148.00"),
        invoice_date="2026-07-20",
    )
    costs = sorted(row["cost_per_base_unit"] for row in await _line_costs(db, carton))
    assert costs == [Decimal("0.01233333"), Decimal("0.01480000")]


@requires_db
async def test_answering_one_question_does_not_move_the_answer_to_another(api, db):
    """Two unlabelled products on one invoice, answered on different days.

    Answering the second pulls that invoice back into the costing pass, and the
    first product's line has to come through it untouched - even though its own
    conversion was corrected in between. This is the case the line-level guard
    exists for: the invoice-level filter cannot see it, because the invoice
    genuinely does still have work to do."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    chicken = await _item(db, gulf, "Chicken Carton", "1 ctn")
    lamb = await _item(db, gulf, "Lamb Carton", "1 ctn")
    document_id = await db.pool.fetchval(
        "insert into documents (tenant_id, source, status) values ($1, 'manual', 'extracted') "
        "returning id",
        DEMO_TENANT_ID,
    )
    invoice_id = await db.pool.fetchval(
        """
        insert into invoices (tenant_id, document_id, supplier_id, status, total, invoice_date)
        values ($1, $2, $3, 'awaiting_confirm', 448.00, date '2026-07-06')
        returning id::text
        """,
        DEMO_TENANT_ID,
        document_id,
        gulf,
    )
    for position, (item_id, name, price) in enumerate(
        ((chicken, "Chicken Carton", "148.00"), (lamb, "Lamb Carton", "300.00"))
    ):
        await db.pool.execute(
            """
            insert into invoice_lines (tenant_id, invoice_id, position, raw_name,
                                       supplier_item_id, qty, pack_size, unit_price, line_total)
            values ($1, $2, $3, $4, $5, 1, '1 ctn', $6, $6)
            """,
            DEMO_TENANT_ID,
            invoice_id,
            position,
            name,
            item_id,
            Decimal(price),
        )
    await db.confirm_invoice(invoice_id, tenant_id=DEMO_TENANT_ID, actor="console")

    await api.post(
        f"/api/supplier-items/{chicken}/pack-size", json={"pack_size": "10 kg"}, headers=AUTH
    )
    chicken_cost = await _line_costs(db, chicken)
    assert [row["cost_per_base_unit"] for row in chicken_cost] == [Decimal("0.01480000")]

    # The consultant thinks better of it, then answers the other carton. The
    # second answer must not drag the first line onto the corrected figure.
    await api.post(
        f"/api/supplier-items/{chicken}/pack-size", json={"pack_size": "12 kg"}, headers=AUTH
    )
    await api.post(
        f"/api/supplier-items/{lamb}/pack-size", json={"pack_size": "15 kg"}, headers=AUTH
    )

    assert await _line_costs(db, chicken) == chicken_cost
    assert [row["cost_per_base_unit"] for row in await _line_costs(db, lamb)] == [
        Decimal("0.02000000")
    ]


@requires_db
async def test_a_later_delivery_of_an_answered_product_costs_without_being_asked_again(api, db):
    """A human says once. The conversion sits on the product, so the invoice
    that arrives next week costs inside its own confirm transaction with nobody
    asked anything."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    carton = await _item(db, gulf, "Chicken Carton", "1 ctn")
    await api.post(
        f"/api/supplier-items/{carton}/pack-size", json={"pack_size": "10 kg"}, headers=AUTH
    )
    await _delivery(
        db,
        carton,
        supplier_id=gulf,
        pack_size="1 ctn",
        unit_price=Decimal("155.00"),
        invoice_date="2026-07-20",
    )
    assert await _blocked(api) == []
    costs = await _line_costs(db, carton)
    assert [row["cost_per_base_unit"] for row in costs] == [Decimal("0.01550000")]


@requires_db
async def test_a_foreign_currency_invoice_says_so_rather_than_going_quiet(api, db):
    """WP-28's hold, given a sentence. The prices were held back on purpose,
    and a line that simply had no cost and no reason would look like a bug."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    sack = await _item(db, gulf, "Milk Powder 2.5kg", "2.5kg")
    document_id = await db.pool.fetchval(
        "insert into documents (tenant_id, source, status) values ($1, 'manual', 'extracted') "
        "returning id",
        DEMO_TENANT_ID,
    )
    invoice_id = await db.pool.fetchval(
        """
        insert into invoices (tenant_id, document_id, supplier_id, status, total, currency)
        values ($1, $2, $3, 'awaiting_confirm', 50.50, 'USD')
        returning id::text
        """,
        DEMO_TENANT_ID,
        document_id,
        gulf,
    )
    await db.pool.execute(
        """
        insert into invoice_lines (tenant_id, invoice_id, position, raw_name, supplier_item_id,
                                   qty, pack_size, unit_price, line_total)
        values ($1, $2, 0, 'Milk Powder', $3, 1, '2.5kg', 50.50, 50.50)
        """,
        DEMO_TENANT_ID,
        invoice_id,
        sack,
    )
    await db.confirm_invoice(invoice_id, tenant_id=DEMO_TENANT_ID, actor="console")

    rows = await _blocked(api)
    assert [row["blocked"] for row in rows] == ["foreign_currency"]
    assert rows[0]["can_override"] is False


@requires_db
async def test_saying_how_much_is_in_one_also_says_what_it_is_measured_in(api, db):
    """A bare carton normally has to be told what it measures, because
    `units.py` refuses to guess. Once a person has said "one holds 10 kg" they
    have already answered that, and asking again on the very next screen is the
    product not listening."""
    gulf = await _supplier(db, "Gulf Foods Trading L.L.C.")
    carton = await _item(db, gulf, "Chicken Carton", "1 ctn")
    refused = await api.post(
        f"/api/supplier-items/{carton}/ingredient", json={"name": "Chicken"}, headers=AUTH
    )
    assert refused.status_code == 422

    await api.post(
        f"/api/supplier-items/{carton}/pack-size", json={"pack_size": "10 kg"}, headers=AUTH
    )
    accepted = await api.post(
        f"/api/supplier-items/{carton}/ingredient", json={"name": "Chicken"}, headers=AUTH
    )
    assert accepted.status_code == 200
    assert accepted.json()["ingredient"]["base_unit"] == "g"


@requires_db
async def test_the_blocked_cost_endpoints_refuse_an_unauthorized_caller(api, db):
    supplier_id = await _supplier(db, "Gulf Foods Trading L.L.C.")
    item_id = await _item(db, supplier_id, "Chicken Carton", "1 ctn")
    assert (await api.get("/api/blocked-costs")).status_code == 401
    assert (
        await api.post(f"/api/supplier-items/{item_id}/pack-size", json={"pack_size": "10kg"})
    ).status_code == 401
