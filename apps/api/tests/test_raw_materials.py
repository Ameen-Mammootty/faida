"""M5: the raw-material layer and its mapping screen (plan.md §8 M5).

The layer's job in one sentence: the same milk powder bought from two
suppliers in two pack sizes must read as one material at one price per kilo,
and every figure inside that price must drill back to an invoice photo.

Invoices are created by driving the real path (webhook -> jobs -> pipeline ->
confirm), so the catalog these tests map is the one the product actually
builds, not a fixture arrangement of it.
"""

import datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI

from faida_api.api import router as api_router
from faida_api.extraction.schema import ExtractedInvoice, ExtractedLine
from faida_api.storage import Storage
from faida_api.wa import WhatsAppClient
from faida_api.webhook import router as webhook_router

from .conftest import (
    DEMO_TENANT_ID,
    FakeExtraction,
    FakeMeta,
    FakeStorage,
    requires_db,
    wa_image_payload,
)
from .test_api import API_TOKEN, AUTH, client_for
from .test_extraction_flow import drain_jobs, invoice_result, post_webhook

pytestmark = requires_db


@pytest.fixture
def api(settings, db):
    api_settings = settings.model_copy(update={"api_token": API_TOKEN})
    app = FastAPI()
    app.include_router(webhook_router)
    app.include_router(api_router)
    app.state.settings = api_settings
    app.state.db = db
    app.state.wa = WhatsAppClient(api_settings, transport=FakeMeta().transport())
    app.state.storage = Storage(api_settings, transport=FakeStorage().transport())
    return app, client_for(app)


def line(name: str, qty: str, unit_price: str, total: str, **kwargs) -> ExtractedLine:
    return ExtractedLine(
        raw_name=name,
        qty=Decimal(qty),
        unit_price=Decimal(unit_price),
        line_total=Decimal(total),
        **kwargs,
    )


def invoice(supplier: str, no: str, lines: list[ExtractedLine]) -> ExtractedInvoice:
    total = sum((entry.line_total for entry in lines), Decimal("0"))
    return ExtractedInvoice(
        supplier_name=supplier,
        invoice_no=no,
        invoice_date=datetime.date(2026, 8, 20),
        currency="AED",
        payment_kind="credit",
        lines=lines,
        subtotal=total,
        tax=Decimal("0.00"),
        total=total,
    )


async def ingest_and_confirm(api, db, extracted: ExtractedInvoice, message_id: str) -> str:
    """One invoice all the way through: forwarded, extracted, confirmed. The
    confirm is what builds the catalog and moves price memory, so it is what
    puts rows in the mapping queue."""
    app, client = api
    await post_webhook(client, wa_image_payload(message_id=message_id))
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(extracted)))
    invoice_id = await db.pool.fetchval(
        "select i.id from invoices i join documents d on d.id = i.document_id "
        "where d.wa_message_id = $1",
        message_id,
    )
    response = await client.post(f"/api/invoices/{invoice_id}/confirm", headers=AUTH)
    assert response.status_code == 200, response.text
    return str(invoice_id)


async def queue(client) -> list[dict]:
    response = await client.get("/api/raw-materials/queue", headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def find(items: list[dict], name: str) -> dict:
    matches = [item for item in items if item["canonical_name"] == name]
    assert matches, f"{name} not in {[item['canonical_name'] for item in items]}"
    return matches[0]


# --- the queue ---------------------------------------------------------------


async def test_queue_ranks_by_money_spent_not_by_name_or_age(api, db):
    """The ranking is the point of the screen: a consultant's afternoon goes
    to the rice that holds up every recipe, not to the food colouring."""
    _, client = api
    await ingest_and_confirm(
        api,
        db,
        invoice(
            "Gulf Foods Trading LLC",
            "INV-1",
            [
                line("FOOD COLOURING 100ML", "1", "6.00", "6.00"),
                line("BASMATI RICE 20KG", "10", "72.00", "720.00"),
                line("CARDAMOM 250G", "2", "45.00", "90.00"),
            ],
        ),
        "wamid.rank",
    )
    items = await queue(client)
    assert [item["canonical_name"] for item in items] == [
        "BASMATI RICE 20KG",
        "CARDAMOM 250G",
        "FOOD COLOURING 100ML",
    ]
    assert Decimal(find(items, "BASMATI RICE 20KG")["spend"]) == Decimal("720.00")
    assert find(items, "BASMATI RICE 20KG")["invoices"] == 1


async def test_queue_derives_a_cost_per_base_unit_from_the_printed_pack(api, db):
    _, client = api
    await ingest_and_confirm(
        api,
        db,
        invoice(
            "Gulf Foods Trading LLC",
            "INV-2",
            [line("MILK PWDR", "4", "50.50", "202.00", unit="ctn", pack_size="2.5kg")],
        ),
        "wamid.cost",
    )
    item = find(await queue(client), "MILK PWDR")
    assert item["blocked"] is None
    assert item["cost"]["per_base"] == "0.02020000"
    assert item["cost"]["base_unit"] == "g"
    assert item["cost"]["basis"] == "pack_size"
    # The screen shows what a person says out loud, computed in Python (C4).
    assert item["cost"]["per_display"] == "20.200"
    assert item["cost"]["display_unit"] == "kg"


async def test_a_carton_of_nothing_stated_is_blocked_rather_than_guessed(api, db):
    _, client = api
    await ingest_and_confirm(
        api,
        db,
        invoice(
            "Gulf Foods Trading LLC",
            "INV-3",
            [line("CHICKEN FRESH", "3", "120.00", "360.00", unit="ctn")],
        ),
        "wamid.blocked",
    )
    item = find(await queue(client), "CHICKEN FRESH")
    assert item["cost"] is None
    assert item["blocked"] == "unknown_pack"


# --- mapping -----------------------------------------------------------------


async def test_two_suppliers_two_pack_sizes_one_price_per_kilo(api, db):
    """The M5 done-when, end to end."""
    app, client = api
    await ingest_and_confirm(
        api,
        db,
        invoice(
            "Gulf Foods Trading LLC",
            "INV-4",
            [line("MILK PWDR NIDO", "4", "50.50", "202.00", unit="ctn", pack_size="2.5kg")],
        ),
        "wamid.m1",
    )
    await ingest_and_confirm(
        api,
        db,
        invoice(
            "Al Madina Trading",
            "INV-5",
            [line("Milk Powder", "2", "104.00", "208.00", unit="bag", pack_size="5kg")],
        ),
        "wamid.m2",
    )

    items = await queue(client)
    nido = find(items, "MILK PWDR NIDO")
    madina = find(items, "Milk Powder")

    # First mapping creates the material in the same click.
    created = await client.post(
        f"/api/supplier-items/{nido['id']}/ingredient",
        headers=AUTH,
        json={"name": "Milk Powder", "base_unit": "g"},
    )
    assert created.status_code == 200, created.text
    ingredient_id = created.json()["ingredient"]["id"]

    # The second pack is now proposed against its mapped sibling.
    proposal = find(await queue(client), "Milk Powder")["proposal"]
    assert proposal is not None
    assert proposal["ingredient_id"] == ingredient_id
    assert proposal["via"] in {"ingredient", "sibling"}

    mapped = await client.post(
        f"/api/supplier-items/{madina['id']}/ingredient",
        headers=AUTH,
        json={"ingredient_id": ingredient_id},
    )
    assert mapped.status_code == 200, mapped.text

    # One material, one cost per kilo, whatever it was bought as.
    listing = await client.get("/api/ingredients", headers=AUTH)
    material = listing.json()["ingredients"][0]
    assert material["name"] == "Milk Powder"
    assert material["packs"] == 2
    assert material["blocked_packs"] == 0
    # Latest purchase wins (PRD §19): Al Madina's 5 kg bag at 104.00 = 20.80/kg.
    assert material["cost"]["per_display"] == "20.800"
    assert material["cost"]["display_unit"] == "kg"

    detail = await client.get(f"/api/ingredients/{ingredient_id}", headers=AUTH)
    body = detail.json()
    assert {pack["cost"]["per_display"] for pack in body["packs"]} == {"20.200", "20.800"}
    # ... and every figure drills back to the photo it was read off.
    assert len(body["prices"]) == 2
    assert all(price["invoice_id"] and price["document_id"] for price in body["prices"])
    assert {price["invoice_no"] for price in body["prices"]} == {"INV-4", "INV-5"}


async def test_a_pack_priced_per_litre_cannot_join_a_material_measured_in_grams(api, db):
    _, client = api
    await ingest_and_confirm(
        api,
        db,
        invoice(
            "Gulf Foods Trading LLC",
            "INV-6",
            [line("SUNFLOWER OIL", "2", "45.00", "90.00", unit="l")],
        ),
        "wamid.mismatch",
    )
    item = find(await queue(client), "SUNFLOWER OIL")
    created = await client.post(
        "/api/ingredients", headers=AUTH, json={"name": "Sunflower Oil", "base_unit": "g"}
    )
    assert created.status_code == 201
    response = await client.post(
        f"/api/supplier-items/{item['id']}/ingredient",
        headers=AUTH,
        json={"ingredient_id": created.json()["id"]},
    )
    assert response.status_code == 409
    assert "measured in g" in response.json()["detail"]


async def test_mapping_records_who_approved_it_and_when(api, db):
    _, client = api
    await ingest_and_confirm(
        api,
        db,
        invoice("Gulf Foods Trading LLC", "INV-7", [line("SUGAR 50KG", "1", "150.00", "150.00")]),
        "wamid.actor",
    )
    item = find(await queue(client), "SUGAR 50KG")
    await client.post(
        f"/api/supplier-items/{item['id']}/ingredient",
        headers=AUTH,
        json={"name": "Sugar", "base_unit": "g"},
    )
    row = await db.pool.fetchrow(
        "select mapped_by, mapped_at from supplier_items where id = $1", item["id"]
    )
    assert row["mapped_by"] == "shared-token"
    assert row["mapped_at"] is not None


async def test_unmapping_returns_the_pack_to_the_queue_and_leaves_prices_alone(api, db):
    _, client = api
    await ingest_and_confirm(
        api,
        db,
        invoice("Gulf Foods Trading LLC", "INV-8", [line("SUGAR 50KG", "1", "150.00", "150.00")]),
        "wamid.unmap",
    )
    item = find(await queue(client), "SUGAR 50KG")
    await client.post(
        f"/api/supplier-items/{item['id']}/ingredient",
        headers=AUTH,
        json={"name": "Sugar", "base_unit": "g"},
    )
    prices_before = await db.pool.fetchval("select count(*) from supplier_item_prices")

    response = await client.delete(f"/api/supplier-items/{item['id']}/ingredient", headers=AUTH)
    assert response.status_code == 200
    assert find(await queue(client), "SUGAR 50KG")["id"] == item["id"]
    assert await db.pool.fetchval("select count(*) from supplier_item_prices") == prices_before


# --- conversions -------------------------------------------------------------


async def test_a_stated_conversion_unblocks_a_carton(api, db):
    _, client = api
    await ingest_and_confirm(
        api,
        db,
        invoice(
            "Gulf Foods Trading LLC",
            "INV-9",
            [line("CHICKEN FRESH", "3", "120.00", "360.00", unit="ctn")],
        ),
        "wamid.convert",
    )
    item = find(await queue(client), "CHICKEN FRESH")
    assert item["blocked"] == "unknown_pack"

    response = await client.post(
        f"/api/supplier-items/{item['id']}/conversion",
        headers=AUTH,
        json={"base_quantity": "10000", "base_unit": "g", "note": "1 carton = 10 kg"},
    )
    assert response.status_code == 201, response.text
    costed = response.json()["item"]
    assert costed["blocked"] is None
    assert costed["cost"]["basis"] == "conversion"
    assert costed["cost"]["per_display"] == "12.000"
    assert costed["conversion"]["note"] == "1 carton = 10 kg"


async def test_correcting_a_conversion_keeps_the_older_one_on_the_record(api, db):
    _, client = api
    await ingest_and_confirm(
        api,
        db,
        invoice(
            "Gulf Foods Trading LLC",
            "INV-10",
            [line("CHICKEN FRESH", "3", "120.00", "360.00", unit="ctn")],
        ),
        "wamid.reconvert",
    )
    item = find(await queue(client), "CHICKEN FRESH")
    for quantity in ("10000", "12000"):
        response = await client.post(
            f"/api/supplier-items/{item['id']}/conversion",
            headers=AUTH,
            json={"base_quantity": quantity, "base_unit": "g"},
        )
        assert response.status_code == 201

    # Newest wins for the cost; both rows survive, so a cost computed before
    # the correction is still reconstructible (PRD §8, versioned conversions).
    assert find(await queue(client), "CHICKEN FRESH")["cost"]["per_display"] == "10.000"
    assert await db.pool.fetchval("select count(*) from supplier_item_conversions") == 2


async def test_a_zero_conversion_is_refused(api, db):
    _, client = api
    await ingest_and_confirm(
        api,
        db,
        invoice(
            "Gulf Foods Trading LLC",
            "INV-11",
            [line("CHICKEN FRESH", "3", "120.00", "360.00", unit="ctn")],
        ),
        "wamid.zero",
    )
    item = find(await queue(client), "CHICKEN FRESH")
    response = await client.post(
        f"/api/supplier-items/{item['id']}/conversion",
        headers=AUTH,
        json={"base_quantity": "0", "base_unit": "g"},
    )
    assert response.status_code == 422


# --- access ------------------------------------------------------------------


async def test_the_raw_material_surface_refuses_an_unauthorized_caller(api, db):
    _, client = api
    for path in ("/api/raw-materials/queue", "/api/ingredients"):
        assert (await client.get(path)).status_code == 401


async def test_an_unknown_material_is_a_404_not_an_empty_page(api, db):
    _, client = api
    missing = "00000000-0000-0000-0000-0000000000ff"
    assert (await client.get(f"/api/ingredients/{missing}", headers=AUTH)).status_code == 404


async def test_creating_the_same_material_twice_is_not_an_error(api, db):
    """The queue creates materials as a side effect of approving a pack, and a
    double submit must not become something a consultant has to think about."""
    _, client = api
    first = await client.post(
        "/api/ingredients", headers=AUTH, json={"name": "Tea Dust", "base_unit": "g"}
    )
    second = await client.post(
        "/api/ingredients", headers=AUTH, json={"name": "Tea Dust", "base_unit": "g"}
    )
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert (
        await db.pool.fetchval(
            "select count(*) from ingredients where tenant_id = $1", DEMO_TENANT_ID
        )
        == 1
    )
