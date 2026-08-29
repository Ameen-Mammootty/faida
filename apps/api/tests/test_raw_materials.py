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

from .conftest import DEMO_TENANT_ID, requires_db

API_TOKEN = "test-api-token"
AUTH = {"Authorization": f"Bearer {API_TOKEN}"}

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
    api_settings = settings.model_copy(update={"api_token": API_TOKEN})
    app = FastAPI()
    app.include_router(api_router)
    app.state.settings = api_settings
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
        assert await db.confirm_invoice(invoice_id, actor="console") is True
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
    assert events[0]["actor"] == "console"
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
    assert events[0]["actor"] == "console"

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
