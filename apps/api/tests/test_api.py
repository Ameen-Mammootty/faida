"""WP-30: the C6 review-screen API (plan.md §6 M3, §7.2 C6).

Auth fail-closed unit tests (no DB), then the endpoints end-to-end against a
real Postgres: invoices are created by driving the actual WhatsApp path
(webhook -> jobs -> pipeline) with Meta/storage/provider mocked at the
transport layer, exactly like the flow tests, then read and mutated through
the API the way the review screen will.
"""

import datetime
import hashlib
import uuid
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from faida_api.api import UPLOAD_MAX_BYTES
from faida_api.api import router as api_router
from faida_api.config import Settings
from faida_api.confirm import handle_inbound_text
from faida_api.storage import Storage
from faida_api.wa import WhatsAppClient
from faida_api.webhook import router as webhook_router

from .conftest import (
    AUTH,
    DEMO_PHONE,
    DEMO_TENANT_ID,
    TEST_ACTOR,
    FakeExtraction,
    FakeJwks,
    FakeMeta,
    FakeStorage,
    requires_db,
    wa_image_payload,
    wire_auth,
)
from .test_extraction_flow import (
    drain_jobs,
    good_invoice,
    invoice_result,
    post_webhook,
    seed_supplier_with_items,
)

DEMO_BRANCH_ID = "00000000-0000-0000-0000-000000000011"  # matches seed.sql


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# --- auth: fail closed (no DB needed) ---------------------------------------


def bare_app() -> FastAPI:
    """An app with only the API router, settings and the verifier over the
    fake JWKS: auth rejects before any handler (or the DB) is ever touched."""
    app = FastAPI()
    app.include_router(api_router)
    app.state.settings = Settings(supabase_url="http://supabase.test")
    wire_auth(app)
    return app


async def test_no_or_malformed_token_is_refused_on_every_request():
    # Fail closed: nothing gets past the door without a token it can verify.
    client = client_for(bare_app())
    assert (await client.get("/api/invoices")).status_code == 401
    assert (
        await client.get("/api/invoices", headers={"Authorization": "Bearer "})
    ).status_code == 401
    assert (
        await client.get("/api/invoices", headers={"Authorization": "Bearer not-a-jwt"})
    ).status_code == 401


async def test_a_token_signed_elsewhere_is_rejected_on_every_route():
    """A token from another key pair - another project, or an attacker with
    the old shared secret - is refused on every route, with no tenant
    resolved and no query run."""
    client = client_for(bare_app())
    elsewhere = {"Authorization": f"Bearer {FakeJwks().mint()}"}
    some_id = str(uuid.uuid4())
    requests = [
        ("GET", "/api/invoices", {}),
        ("GET", f"/api/invoices/{some_id}", {}),
        ("PATCH", f"/api/invoices/{some_id}/fields", {"json": {"corrections": []}}),
        ("POST", f"/api/invoices/{some_id}/confirm", {}),
        ("POST", "/api/documents", {"files": {"file": ("a.jpg", b"x", "image/jpeg")}}),
        ("GET", f"/api/supplier-items/{some_id}/prices", {}),
    ]
    for method, url, kwargs in requests:
        assert (await client.request(method, url, **kwargs)).status_code == 401, url
        response = await client.request(method, url, headers=elsewhere, **kwargs)
        assert response.status_code == 401, url
    # Not a bearer header at all.
    token = AUTH["Authorization"].removeprefix("Bearer ")
    assert (await client.get("/api/invoices", headers={"Authorization": token})).status_code == 401


async def test_a_verified_token_reaches_the_membership_lookup():
    # No DB is wired, so getting past the signature check means reaching the
    # membership read and dying on the missing pool - proof the token was
    # verified. (The happy paths below cover the full flow against a real DB.)
    app = bare_app()
    app.state.db = None
    client = client_for(app)
    with pytest.raises(AttributeError):
        await client.get(f"/api/supplier-items/{uuid.uuid4()}/prices", headers=AUTH)


# --- e2e harness ------------------------------------------------------------


@pytest.fixture
def api(settings, db):
    """A FastAPI app with both routers, the test DB, mock transports, and the
    verifier over the fake JWKS; mirrors the flow-test fixture."""
    fake_meta = FakeMeta()
    fake_storage = FakeStorage()

    app = FastAPI()
    app.include_router(webhook_router)
    app.include_router(api_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    app.state.wa = WhatsAppClient(settings, transport=fake_meta.transport())
    app.state.storage = Storage(settings, transport=fake_storage.transport())

    client = client_for(app)
    return app, client, fake_meta, fake_storage


async def extracted_invoice(api, db, invoice=None, message_id="wamid.in1") -> dict:
    """Drive one invoice through the real path (webhook -> ingest -> extract)
    and return its row as a dict."""
    app, client, *_ = api
    await post_webhook(client, wa_image_payload(message_id=message_id))
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(invoice or good_invoice())))
    doc = await db.get_document_by_wa_message(message_id)
    row = await db.get_invoice_by_document(str(doc["id"]), tenant_id=DEMO_TENANT_ID)
    return dict(row)


# --- list + filters ---------------------------------------------------------


@requires_db
async def test_list_is_newest_first_and_filters_work(api, db):
    app, client, *_ = api
    first = await extracted_invoice(api, db, message_id="wamid.in1")
    cash = good_invoice()
    cash.invoice_no = "INV-2000"
    cash.payment_kind = "cash"
    second = await extracted_invoice(api, db, cash, message_id="wamid.in2")
    # Pin creation times so newest-first is deterministic.
    await db.pool.execute(
        "update invoices set created_at = '2026-08-20 06:00:00+00' where id = $1", first["id"]
    )
    await db.pool.execute(
        "update invoices set created_at = '2026-08-21 06:00:00+00' where id = $1", second["id"]
    )

    resp = await client.get("/api/invoices", headers=AUTH)
    assert resp.status_code == 200
    invoices = resp.json()["invoices"]
    assert [inv["id"] for inv in invoices] == [str(second["id"]), str(first["id"])]
    assert invoices[1] == {
        "id": str(first["id"]),
        "supplier_name": "Gulf Foods Trading LLC",
        "supplier_id": None,
        "invoice_no": "INV-1041",
        "invoice_date": "2026-08-20",
        "currency": "AED",
        "total": "745.76",  # money is a string, never a float
        "status": "awaiting_confirm",
        "created_at": "2026-08-20T06:00:00+00:00",
        "branch_id": DEMO_BRANCH_ID,
        "branch_name": "Al Barsha Branch",  # joined from branches (WP-32)
        "document_id": str(first["document_id"]),
        # An ordinary invoice is nobody's copy. Pinned here rather than in its
        # own test: a bug that set the pointer on every invoice would put a
        # Dismiss button on the whole list, and this is the assertion that
        # notices.
        "duplicate_of_invoice_id": None,
        "duplicate_of_invoice_no": None,
    }

    resp = await client.get("/api/invoices?status=needs_review", headers=AUTH)
    assert [inv["id"] for inv in resp.json()["invoices"]] == [str(second["id"])]

    resp = await client.get(f"/api/invoices?branch_id={DEMO_BRANCH_ID}", headers=AUTH)
    assert len(resp.json()["invoices"]) == 2
    resp = await client.get(f"/api/invoices?branch_id={uuid.uuid4()}", headers=AUTH)
    assert resp.json()["invoices"] == []

    # supplier_id is set on confirm (the catalog self-builds); filter by it.
    await client.post(f"/api/invoices/{first['id']}/confirm", headers=AUTH)
    supplier_id = await db.pool.fetchval("select id from suppliers limit 1")
    resp = await client.get(f"/api/invoices?supplier_id={supplier_id}", headers=AUTH)
    assert [inv["id"] for inv in resp.json()["invoices"]] == [str(first["id"])]

    # A status outside the C1 machine is a request error, not an empty list.
    assert (await client.get("/api/invoices?status=nonsense", headers=AUTH)).status_code == 422


# --- detail -----------------------------------------------------------------


@requires_db
async def test_detail_carries_fields_checks_and_a_signed_image_url(api, db):
    app, client, *_ = api
    invoice = await extracted_invoice(api, db)
    doc_id = str(invoice["document_id"])

    resp = await client.get(f"/api/invoices/{invoice['id']}", headers=AUTH)
    assert resp.status_code == 200
    detail = resp.json()

    assert detail["id"] == str(invoice["id"])
    assert detail["supplier_name"] == "Gulf Foods Trading LLC"
    assert detail["invoice_no"] == "INV-1041"
    assert detail["invoice_date"] == "2026-08-20"
    assert detail["currency"] == "AED"
    assert detail["branch_name"] == "Al Barsha Branch"  # joined from branches (WP-32)
    assert detail["payment_kind"] == "credit"
    assert detail["status"] == "awaiting_confirm"
    assert detail["confirmed_at"] is None
    # Money and quantities are decimal strings end to end.
    assert (detail["subtotal"], detail["tax"], detail["total"]) == ("710.25", "35.51", "745.76")
    line = detail["lines"][0]
    assert (line["qty"], line["unit_price"], line["line_total"]) == ("12.000", "54.500", "654.00")
    assert (line["position"], line["raw_name"]) == (0, "MILK PWDR 2.5KG NIDO")
    assert (line["unit"], line["pack_size"]) == ("sack", "2.5kg")
    assert line["supplier_item_id"] is None  # nothing snapped: empty catalog
    assert line["checks"]["arith"] == "passed"
    assert line["checks"]["status"] == "green"
    assert detail["confidence"]["lines"] == ["green", "green"]
    assert detail["confidence"]["document"]["status"] == "green"
    assert detail["document"]["status"] == "extracted"
    assert detail["document"]["classification"] == "invoice"
    assert detail["document"]["source"] == "whatsapp"
    assert detail["document"]["created_at"] is not None
    assert detail["image_url"] == (
        "http://supabase.test/storage/v1/object/sign/documents/"
        f"{DEMO_TENANT_ID}/documents/{doc_id}/original?token=fake-signed-token"
    )

    assert (await client.get(f"/api/invoices/{uuid.uuid4()}", headers=AUTH)).status_code == 404


@requires_db
async def test_detail_image_url_is_null_without_a_stored_original(api, db):
    app, client, *_ = api
    invoice = await extracted_invoice(api, db)
    await db.pool.execute(
        "update documents set storage_path = null where id = $1", invoice["document_id"]
    )
    resp = await client.get(f"/api/invoices/{invoice['id']}", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["image_url"] is None


# --- PATCH fields -----------------------------------------------------------


@requires_db
async def test_patch_applies_a_correction_and_revalidates(api, db):
    app, client, *_ = api
    misread = good_invoice()
    misread.lines[0].qty = Decimal("2")  # 2 x 54.50 != 654.00 -> amber
    invoice = await extracted_invoice(api, db, misread)
    assert invoice["confidence"]["lines"] == ["amber", "green"]

    resp = await client.patch(
        f"/api/invoices/{invoice['id']}/fields",
        headers=AUTH,
        json={"corrections": [{"line_index": 0, "field": "qty", "value": "12"}]},
    )
    assert resp.status_code == 200
    detail = resp.json()
    # The response is the re-validated detail: the amber flipped green.
    assert detail["lines"][0]["qty"] == "12.000"
    assert detail["lines"][0]["checks"]["arith"] == "passed"
    assert detail["lines"][0]["checks"]["status"] == "green"
    assert detail["confidence"]["lines"] == ["green", "green"]
    assert detail["confidence"]["document"]["status"] == "green"
    assert detail["status"] == "awaiting_confirm"  # a correction never confirms

    row = await db.pool.fetchrow(
        "select * from invoice_lines where invoice_id = $1 and position = 0", invoice["id"]
    )
    assert row["qty"] == Decimal("12")
    assert row["checks"]["status"] == "green"


@requires_db
async def test_patch_header_field_with_null_line_index(api, db):
    app, client, *_ = api
    invoice = await extracted_invoice(api, db)
    resp = await client.patch(
        f"/api/invoices/{invoice['id']}/fields",
        headers=AUTH,
        json={"corrections": [{"line_index": None, "field": "total", "value": "999.99"}]},
    )
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["total"] == "999.99"
    # Re-validation caught the now-broken reconciliation.
    assert detail["confidence"]["document"]["status"] == "amber"
    assert detail["confidence"]["document"]["arith"] == "failed"


@requires_db
async def test_patch_rejects_bad_corrections_with_422(api, db):
    app, client, *_ = api
    invoice = await extracted_invoice(api, db)
    url = f"/api/invoices/{invoice['id']}/fields"
    bad = [
        {"line_index": 0, "field": "qty", "value": "-5"},  # signed
        {"line_index": 0, "field": "qty", "value": "nan"},
        {"line_index": 9, "field": "qty", "value": "5"},  # out of range
        {"line_index": 0, "field": "total", "value": "5"},  # header field on a line
        {"line_index": None, "field": "qty", "value": "5"},  # line field without a line
        {"line_index": 0, "field": "name", "value": "  "},  # empty name
    ]
    for correction in bad:
        resp = await client.patch(url, headers=AUTH, json={"corrections": [correction]})
        assert resp.status_code == 422, correction
    # Nothing half-applied.
    line = await db.pool.fetchrow(
        "select qty from invoice_lines where invoice_id = $1 and position = 0", invoice["id"]
    )
    assert line["qty"] == Decimal("12")


@requires_db
async def test_patch_on_a_confirmed_invoice_is_409(api, db):
    app, client, *_ = api
    invoice = await extracted_invoice(api, db)
    assert (
        await client.post(f"/api/invoices/{invoice['id']}/confirm", headers=AUTH)
    ).status_code == 200
    resp = await client.patch(
        f"/api/invoices/{invoice['id']}/fields",
        headers=AUTH,
        json={"corrections": [{"line_index": 0, "field": "qty", "value": "1"}]},
    )
    assert resp.status_code == 409


# --- confirm ----------------------------------------------------------------


@requires_db
async def test_confirm_flips_status_and_records_prices(api, db):
    app, client, *_ = api
    invoice = await extracted_invoice(api, db)

    resp = await client.post(f"/api/invoices/{invoice['id']}/confirm", headers=AUTH)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["status"] == "confirmed"
    assert detail["confirmed_at"] is not None
    # The document's status is ingest-only; confirmation shows on the invoice.
    assert detail["document"]["status"] == "extracted"
    assert detail["supplier_id"] is not None  # the catalog self-built on confirm

    prices = await db.pool.fetch("select price from supplier_item_prices order by price")
    assert [row["price"] for row in prices] == [Decimal("18.75"), Decimal("54.50")]

    # Double confirm: 409, and the price history did not grow.
    resp = await client.post(f"/api/invoices/{invoice['id']}/confirm", headers=AUTH)
    assert resp.status_code == 409
    assert await db.pool.fetchval("select count(*) from supplier_item_prices") == 2
    milk = await db.pool.fetchrow(
        "select * from supplier_items where canonical_name = 'MILK PWDR 2.5KG NIDO'"
    )
    assert milk["last_price"] == Decimal("54.50")
    assert milk["prev_price"] is None  # never shifted by a re-confirm


@requires_db
async def test_confirm_refuses_a_cash_hold_and_names_the_approve_door(api, db):
    """M7 WP-74 (PRD §21): the screen's Confirm used to be the cash approval
    path, recording nothing but a status flip. Now it refuses cash outright and
    the sentence says where to go instead."""
    app, client, *_ = api
    cash = good_invoice()
    cash.payment_kind = "cash"
    invoice = await extracted_invoice(api, db, cash)
    assert invoice["status"] == "needs_review"

    resp = await client.post(f"/api/invoices/{invoice['id']}/confirm", headers=AUTH)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "invoice is paid in cash; approve it with a reason instead"
    assert (await db.get_invoice(str(invoice["id"]), tenant_id=DEMO_TENANT_ID))["status"] == (
        "needs_review"
    )
    assert await db.pool.fetchval("select count(*) from supplier_item_prices") == 0
    assert (
        await db.audit_events_for_subject("invoice", str(invoice["id"]), tenant_id=DEMO_TENANT_ID)
        == []
    )


@requires_db
async def test_approve_records_a_cash_hold_with_a_reason_and_moves_the_baseline(api, db):
    """The one gate PRD §21 makes non-negotiable: a cash paper reaches
    `confirmed` only through the approve door, with a reason, and the record
    names the person, the reason and what was approved."""
    app, client, *_ = api
    cash = good_invoice()
    cash.payment_kind = "cash"
    invoice = await extracted_invoice(api, db, cash)

    resp = await client.post(
        f"/api/invoices/{invoice['id']}/approve",
        headers=AUTH,
        json={"reason": "  Petty cash, receipt in the drawer  "},
    )
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["status"] == "confirmed"
    assert detail["confirmed_at"] is not None
    assert detail["payment_kind"] == "cash"
    assert detail["document"]["status"] == "extracted"
    assert detail["supplier_id"] is not None

    # The same write as confirm: the price baseline moved inside it.
    prices = await db.pool.fetch("select price from supplier_item_prices order by price")
    assert [row["price"] for row in prices] == [Decimal("18.75"), Decimal("54.50")]

    events = await db.audit_events_for_subject(
        "invoice", str(invoice["id"]), tenant_id=DEMO_TENANT_ID
    )
    assert [(e["action"], e["actor"]) for e in events] == [("invoice.cash_approved", TEST_ACTOR)]
    assert events[0]["detail"] == {
        "from_status": "needs_review",
        "reason": "Petty cash, receipt in the drawer",
        "supplier_name": "Gulf Foods Trading LLC",
        "invoice_no": "INV-1041",
        "currency": "AED",
        "total": "745.76",
        "payment_kind": "cash",
        "duplicate_of_invoice_id": None,
    }

    # Double-click: the second answers with the fresh status, and the trail
    # still holds one row.
    again = await client.post(
        f"/api/invoices/{invoice['id']}/approve", headers=AUTH, json={"reason": "again"}
    )
    assert again.status_code == 409
    assert again.json()["detail"] == "invoice is already confirmed"
    assert (
        len(
            await db.audit_events_for_subject(
                "invoice", str(invoice["id"]), tenant_id=DEMO_TENANT_ID
            )
        )
        == 1
    )
    assert await db.pool.fetchval("select count(*) from supplier_item_prices") == 2
    missing = await client.post(
        f"/api/invoices/{uuid.uuid4()}/approve", headers=AUTH, json={"reason": "x"}
    )
    assert missing.status_code == 404


@requires_db
async def test_approve_without_a_reason_is_422_and_writes_nothing(api, db):
    app, client, *_ = api
    cash = good_invoice()
    cash.payment_kind = "cash"
    invoice = await extracted_invoice(api, db, cash)

    for body in ({"reason": ""}, {"reason": "   \n\t"}, {}, {"reason": None}):
        resp = await client.post(f"/api/invoices/{invoice['id']}/approve", headers=AUTH, json=body)
        assert resp.status_code == 422, (body, resp.text)

    row = await db.get_invoice(str(invoice["id"]), tenant_id=DEMO_TENANT_ID)
    assert row["status"] == "needs_review" and row["confirmed_at"] is None
    assert await db.pool.fetchval("select count(*) from audit_events") == 0
    assert await db.pool.fetchval("select count(*) from supplier_item_prices") == 0


@requires_db
async def test_approve_refuses_anything_that_is_not_a_held_cash_paper(api, db):
    """Keyed on cash alone: a credit paper is confirmed, never approved (a
    misread cash is corrected, not laundered through an approval); a recorded
    or dismissed paper is refused with its real status."""
    app, client, *_ = api
    credit = await extracted_invoice(api, db)
    resp = await client.post(
        f"/api/invoices/{credit['id']}/approve", headers=AUTH, json={"reason": "why not"}
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "invoice is paid by credit, not cash; confirm it instead"

    await client.post(f"/api/invoices/{credit['id']}/confirm", headers=AUTH)
    resp = await client.post(
        f"/api/invoices/{credit['id']}/approve", headers=AUTH, json={"reason": "why not"}
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "invoice is paid by credit, not cash; confirm it instead"

    cash = good_invoice()
    cash.payment_kind = "cash"
    cash.invoice_no = "INV-2000"
    held = await extracted_invoice(api, db, cash, message_id="wamid.cash")
    await client.post(f"/api/invoices/{held['id']}/approve", headers=AUTH, json={"reason": "ok"})
    resp = await client.post(
        f"/api/invoices/{held['id']}/approve", headers=AUTH, json={"reason": "twice"}
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "invoice is already confirmed"

    original, copy = await held_duplicate(api, db, payment_kind="cash", invoice_no="INV-3000")
    await client.post(f"/api/invoices/{copy['id']}/dismiss", headers=AUTH)
    resp = await client.post(
        f"/api/invoices/{copy['id']}/approve", headers=AUTH, json={"reason": "late"}
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "invoice is dismissed; a dismissed copy cannot be approved"
    events = await db.audit_events_for_subject("invoice", str(copy["id"]), tenant_id=DEMO_TENANT_ID)
    assert [e["action"] for e in events] == ["invoice.dismissed"]


@requires_db
async def test_a_cash_paper_that_is_also_a_held_duplicate_approves_and_the_record_says_both(
    api, db
):
    """D12: the approve door keys on cash alone. A cash copy that really is a
    new paper has to have a recording door, and its audit row carries the
    duplicate pointer beside the reason so the two facts are read together."""
    app, client, *_ = api
    original, copy = await held_duplicate(api, db, payment_kind="cash")
    assert copy["payment_kind"] == "cash"

    resp = await client.post(
        f"/api/invoices/{copy['id']}/approve",
        headers=AUTH,
        json={"reason": "Second delivery the same day, both paid at the door"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "confirmed"

    events = await db.audit_events_for_subject("invoice", str(copy["id"]), tenant_id=DEMO_TENANT_ID)
    assert [(e["action"], e["actor"]) for e in events] == [("invoice.cash_approved", TEST_ACTOR)]
    assert events[0]["detail"]["duplicate_of_invoice_id"] == str(original["id"])
    assert events[0]["detail"]["payment_kind"] == "cash"
    assert events[0]["detail"]["reason"] == "Second delivery the same day, both paid at the door"
    # The original is untouched.
    assert (await db.get_invoice(str(original["id"]), tenant_id=DEMO_TENANT_ID))["status"] == (
        "awaiting_confirm"
    )


@requires_db
async def test_a_non_cash_duplicate_hold_still_confirms_through_confirm(api, db):
    app, client, *_ = api
    original, copy = await held_duplicate(api, db)
    resp = await client.post(f"/api/invoices/{copy['id']}/confirm", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"
    events = await db.audit_events_for_subject("invoice", str(copy["id"]), tenant_id=DEMO_TENANT_ID)
    assert [e["action"] for e in events] == ["invoice.confirmed"]


@requires_db
async def test_the_screen_corrects_a_misread_cash_and_the_hold_lifts(api, db):
    """D23: payment_kind is correctable. Cash to credit on a held paper with
    no duplicate pointer returns it to awaiting_confirm - the first correction
    that moves a status - stamped like every other correction."""
    app, client, *_ = api
    cash = good_invoice()
    cash.payment_kind = "cash"
    invoice = await extracted_invoice(api, db, cash)
    assert invoice["status"] == "needs_review"

    resp = await client.patch(
        f"/api/invoices/{invoice['id']}/fields",
        headers=AUTH,
        json={"corrections": [{"line_index": None, "field": "payment_kind", "value": "credit"}]},
    )
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["payment_kind"] == "credit"
    assert detail["status"] == "awaiting_confirm"
    assert detail["provenance"]["payment_kind"]["origin"] == "corrected_screen"
    assert detail["provenance"]["payment_kind"]["actor"] == TEST_ACTOR
    assert detail["provenance"]["total"]["origin"] == "extracted"
    assert detail["confidence"]["document"]["status"] == "green"  # re-validation unchanged

    events = await db.audit_events_for_subject(
        "invoice", str(invoice["id"]), tenant_id=DEMO_TENANT_ID
    )
    assert [(e["action"], e["actor"]) for e in events] == [("invoice.corrected", TEST_ACTOR)]
    assert events[0]["detail"] == {
        "fields": ["payment_kind"],
        "message_id": None,
        "from_status": "needs_review",
        "to_status": "awaiting_confirm",
    }

    # Now an ordinary paper: confirm works, approve does not.
    refused = await client.post(
        f"/api/invoices/{invoice['id']}/approve", headers=AUTH, json={"reason": "x"}
    )
    assert refused.status_code == 409
    confirmed = await client.post(f"/api/invoices/{invoice['id']}/confirm", headers=AUTH)
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "confirmed"


@requires_db
async def test_the_screen_marks_a_paper_cash_and_it_is_held(api, db):
    app, client, *_ = api
    invoice = await extracted_invoice(api, db)
    assert invoice["status"] == "awaiting_confirm"

    resp = await client.patch(
        f"/api/invoices/{invoice['id']}/fields",
        headers=AUTH,
        json={"corrections": [{"line_index": None, "field": "payment_kind", "value": "Cash"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["payment_kind"] == "cash"
    assert resp.json()["status"] == "needs_review"

    # Held now: confirm refuses, approve is the door.
    resp = await client.post(f"/api/invoices/{invoice['id']}/confirm", headers=AUTH)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "invoice is paid in cash; approve it with a reason instead"
    resp = await client.post(
        f"/api/invoices/{invoice['id']}/approve", headers=AUTH, json={"reason": "paid at the door"}
    )
    assert resp.status_code == 200 and resp.json()["status"] == "confirmed"

    # Bad values are 422, and a line_index on a header field too.
    for correction in (
        {"line_index": None, "field": "payment_kind", "value": "cheque"},
        {"line_index": None, "field": "payment_kind", "value": ""},
        {"line_index": 0, "field": "payment_kind", "value": "cash"},
    ):
        other = await extracted_invoice(api, db, message_id=f"wamid.{hash(str(correction))}")
        resp = await client.patch(
            f"/api/invoices/{other['id']}/fields", headers=AUTH, json={"corrections": [correction]}
        )
        assert resp.status_code == 422, (correction, resp.text)


@requires_db
async def test_a_cash_duplicate_corrected_to_credit_stays_held(api, db):
    """The duplicate hold still applies once the cash reason is gone, so the
    paper stays needs_review and its exits are confirm or dismiss."""
    app, client, *_ = api
    original, copy = await held_duplicate(api, db, payment_kind="cash")

    resp = await client.patch(
        f"/api/invoices/{copy['id']}/fields",
        headers=AUTH,
        json={"corrections": [{"line_index": None, "field": "payment_kind", "value": "credit"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["payment_kind"] == "credit"
    assert resp.json()["status"] == "needs_review"
    events = await db.audit_events_for_subject("invoice", str(copy["id"]), tenant_id=DEMO_TENANT_ID)
    assert events[0]["detail"] == {"fields": ["payment_kind"], "message_id": None}

    refused = await client.post(
        f"/api/invoices/{copy['id']}/approve", headers=AUTH, json={"reason": "x"}
    )
    assert refused.status_code == 409
    assert refused.json()["detail"] == "invoice is paid by credit, not cash; confirm it instead"
    dismissed = await client.post(f"/api/invoices/{copy['id']}/dismiss", headers=AUTH)
    assert dismissed.status_code == 200 and dismissed.json()["status"] == "dismissed"


# --- manual upload ----------------------------------------------------------


@requires_db
async def test_upload_stores_the_original_and_enqueues_extraction(api, db):
    app, client, _, fake_storage = api
    data = b"\xff\xd8upload-jpeg-bytes"

    resp = await client.post(
        "/api/documents",
        headers=AUTH,
        files={"file": ("invoice.jpg", data, "image/jpeg")},
        data={"branch_id": DEMO_BRANCH_ID},
    )
    assert resp.status_code == 201
    document_id = resp.json()["document_id"]

    doc = await db.get_document(document_id, tenant_id=DEMO_TENANT_ID)
    assert doc["source"] == "upload"
    assert doc["mime"] == "image/jpeg"
    assert doc["status"] == "received"
    assert str(doc["branch_id"]) == DEMO_BRANCH_ID
    assert str(doc["tenant_id"]) == DEMO_TENANT_ID
    assert doc["sha256"] == hashlib.sha256(data).hexdigest()
    assert doc["wa_message_id"] is None
    path = f"{DEMO_TENANT_ID}/documents/{document_id}/original"
    assert doc["storage_path"] == path
    assert fake_storage.objects[path] == data  # the immutable original, byte for byte

    job = await db.pool.fetchrow("select * from jobs order by id desc limit 1")
    assert job["kind"] == "extract_document"
    # C2 as amended (WP-72): the job carries the caller's tenant and the
    # validated branch, so the worker never reads the row to guess whose it is.
    assert job["payload"] == {
        "document_id": document_id,
        "tenant_id": DEMO_TENANT_ID,
        "branch_id": DEMO_BRANCH_ID,
    }

    # The enqueued job really extracts: same pipeline as the WhatsApp path.
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(good_invoice())))
    invoice = await db.get_invoice_by_document(document_id, tenant_id=DEMO_TENANT_ID)
    assert invoice["status"] == "awaiting_confirm"
    assert (await db.get_document(document_id, tenant_id=DEMO_TENANT_ID))["status"] == "extracted"


@requires_db
async def test_upload_without_branch_is_fine_and_unknown_branch_is_not(api, db):
    app, client, *_ = api
    resp = await client.post(
        "/api/documents", headers=AUTH, files={"file": ("a.png", b"png-bytes", "image/png")}
    )
    assert resp.status_code == 201
    doc = await db.get_document(resp.json()["document_id"], tenant_id=DEMO_TENANT_ID)
    assert doc["branch_id"] is None

    resp = await client.post(
        "/api/documents",
        headers=AUTH,
        files={"file": ("a.png", b"png-bytes2", "image/png")},
        data={"branch_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 422


@requires_db
async def test_upload_rejects_unsupported_types_and_oversize(api, db):
    app, client, _, fake_storage = api
    resp = await client.post(
        "/api/documents", headers=AUTH, files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert resp.status_code == 415

    resp = await client.post(
        "/api/documents",
        headers=AUTH,
        files={"file": ("huge.jpg", b"x" * (UPLOAD_MAX_BYTES + 1), "image/jpeg")},
    )
    assert resp.status_code == 413

    # Neither rejection left anything behind.
    assert await db.pool.fetchval("select count(*) from documents") == 0
    assert await db.pool.fetchval("select count(*) from jobs") == 0
    assert fake_storage.objects == {}


# --- manual entry (WP-34) ---------------------------------------------------


def manual_body(**overrides) -> dict:
    """A POST /api/invoices/manual body typed from the good_invoice photo:
    the same numbers, so its checks land exactly where the pipeline's do."""
    body = {
        "branch_id": DEMO_BRANCH_ID,
        "supplier_name": "Gulf Foods Trading LLC",
        "invoice_no": "MAN-77",
        "invoice_date": "2026-08-22",
        "currency": "AED",
        "payment_kind": "credit",
        "subtotal": "710.25",
        "tax": "35.51",
        "total": "745.76",
        "lines": [
            {
                "raw_name": "MILK PWDR 2.5KG NIDO",
                "qty": "12",
                "unit": "sack",
                "pack_size": "2.5kg",
                "unit_price": "54.50",
                "line_total": "654.00",
            },
            {
                "raw_name": "KARAK TEA DUST",
                "qty": "3",
                "unit_price": "18.75",
                "line_total": "56.25",
            },
        ],
    }
    body.update(overrides)
    return body


@requires_db
async def test_manual_entry_creates_a_checked_invoice(api, db):
    app, client, *_ = api
    resp = await client.post("/api/invoices/manual", headers=AUTH, json=manual_body())
    assert resp.status_code == 201
    detail = resp.json()

    assert detail["status"] == "awaiting_confirm"
    assert detail["supplier_name"] == "Gulf Foods Trading LLC"
    assert detail["invoice_no"] == "MAN-77"
    assert detail["invoice_date"] == "2026-08-22"
    assert detail["currency"] == "AED"
    assert detail["payment_kind"] == "credit"
    assert detail["branch_id"] == DEMO_BRANCH_ID
    assert detail["branch_name"] == "Al Barsha Branch"
    assert (detail["subtotal"], detail["tax"], detail["total"]) == ("710.25", "35.51", "745.76")

    # The same deterministic checks the pipeline persists, from the same code.
    line = detail["lines"][0]
    assert (line["qty"], line["unit_price"], line["line_total"]) == ("12.000", "54.500", "654.00")
    assert (line["unit"], line["pack_size"]) == ("sack", "2.5kg")
    assert line["checks"]["arith"] == "passed"
    assert line["checks"]["status"] == "green"
    assert detail["confidence"]["lines"] == ["green", "green"]
    assert detail["confidence"]["document"]["status"] == "green"

    # The stub document: source 'manual', no photo, no classification - and
    # 'extracted', because a draft invoice with checks exists (C1 invariant).
    assert detail["document"]["source"] == "manual"
    assert detail["document"]["status"] == "extracted"
    assert detail["document"]["classification"] is None
    assert detail["image_url"] is None
    doc = await db.get_document(detail["document"]["id"], tenant_id=DEMO_TENANT_ID)
    assert doc["storage_path"] is None
    assert doc["wa_message_id"] is None
    assert doc["mime"] is None and doc["sha256"] is None
    assert str(doc["branch_id"]) == DEMO_BRANCH_ID

    # No AI anywhere in this path: nothing enqueued, no extraction run.
    assert await db.pool.fetchval("select count(*) from jobs") == 0
    assert await db.pool.fetchval("select count(*) from extraction_runs") == 0


@requires_db
async def test_manual_cash_invoice_is_held_and_approved_from_the_screen(api, db):
    app, client, *_ = api
    resp = await client.post(
        "/api/invoices/manual", headers=AUTH, json=manual_body(payment_kind="cash")
    )
    assert resp.status_code == 201
    detail = resp.json()
    assert detail["status"] == "needs_review"  # WP-24 holds typed cash too

    # Confirm is not the door for cash any more (WP-74); approve with a reason is.
    resp = await client.post(f"/api/invoices/{detail['id']}/confirm", headers=AUTH)
    assert resp.status_code == 409
    resp = await client.post(
        f"/api/invoices/{detail['id']}/approve",
        headers=AUTH,
        json={"reason": "Typed in from the till slip, cash paid on delivery"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "confirmed"
    events = await db.audit_events_for_subject("invoice", detail["id"], tenant_id=DEMO_TENANT_ID)
    assert [e["action"] for e in events] == ["invoice.cash_approved", "invoice.created_by_hand"]


@requires_db
async def test_manual_entry_derives_amber_from_the_same_checks(api, db):
    app, client, *_ = api
    body = manual_body()
    body["lines"][0]["qty"] = "2"  # 2 x 54.50 != 654.00
    body["lines"].append({"raw_name": "COOKING OIL 5L"})  # typed with no numbers
    resp = await client.post("/api/invoices/manual", headers=AUTH, json=body)
    assert resp.status_code == 201
    detail = resp.json()

    assert detail["confidence"]["lines"] == ["amber", "green", "amber"]
    assert detail["lines"][0]["checks"]["arith"] == "failed"
    assert detail["lines"][0]["checks"]["expected"] == "109.00"  # 2 x 54.50
    assert detail["lines"][2]["checks"]["arith"] == "indeterminate"
    # A failed line taints the totals: never green past a broken line.
    assert detail["confidence"]["document"]["status"] == "amber"

    # The review loop is one machinery for typed and photographed invoices:
    # PATCH the typo, everything flips green.
    resp = await client.patch(
        f"/api/invoices/{detail['id']}/fields",
        headers=AUTH,
        json={
            "corrections": [
                {"line_index": 0, "field": "qty", "value": "12"},
                {"line_index": 2, "field": "qty", "value": "1"},
                {"line_index": 2, "field": "unit_price", "value": "36.00"},
                {"line_index": 2, "field": "line_total", "value": "36.00"},
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json()["confidence"]["lines"] == ["green", "green", "green"]


@requires_db
async def test_manual_entry_rejects_bad_input_and_persists_nothing(api, db):
    app, client, *_ = api
    url = "/api/invoices/manual"

    bad_bodies = [
        manual_body(subtotal="-5"),  # signed
        manual_body(tax="nan"),
        manual_body(total="1e3"),  # exponent
        manual_body(lines=[]),  # at least one line
        manual_body(branch_id=str(uuid.uuid4())),  # unknown branch
        manual_body(branch_id="not-a-uuid"),
        manual_body(invoice_date="22/08/2026"),  # not ISO
        manual_body(payment_kind="cheque"),
        manual_body(surprise="field"),  # extra="forbid"
    ]
    bad_qty = manual_body()
    bad_qty["lines"][0]["qty"] = "twelve"
    bad_bodies.append(bad_qty)
    empty_name = manual_body()
    empty_name["lines"][0]["raw_name"] = "   "
    bad_bodies.append(empty_name)

    for body in bad_bodies:
        assert (await client.post(url, headers=AUTH, json=body)).status_code == 422, body

    # Every rejection was whole: no document, invoice, or job left behind.
    assert await db.pool.fetchval("select count(*) from documents") == 0
    assert await db.pool.fetchval("select count(*) from invoices") == 0
    assert await db.pool.fetchval("select count(*) from jobs") == 0


@requires_db
async def test_manual_entry_snaps_to_supplier_memory(api, db):
    # Layer 4 runs for typed invoices exactly as for photographed ones:
    # supplier fuzzy-matched, lines snapped, flags folded into the checks
    # without recomputing status - and the price baseline stays untouched
    # until confirm.
    app, client, *_ = api
    supplier_id, item_ids = await seed_supplier_with_items(
        db,
        [
            {
                "canonical_name": "MILK PWDR 2.5KG NIDO",
                "unit": "sack",
                "pack_size": "2.5kg",
                "last_price": Decimal("50.00"),
            }
        ],
    )

    resp = await client.post("/api/invoices/manual", headers=AUTH, json=manual_body())
    assert resp.status_code == 201
    detail = resp.json()
    assert detail["supplier_id"] == str(supplier_id)
    assert detail["lines"][0]["supplier_item_id"] == str(item_ids["MILK PWDR 2.5KG NIDO"])
    assert detail["lines"][0]["checks"]["snapped"] is True
    assert detail["lines"][1]["checks"]["snapped"] is False  # not in the catalog
    # Pipeline parity: an unsnapped line keeps its green arithmetic while the
    # catalog self-builds.
    assert detail["confidence"]["lines"] == ["green", "green"]

    milk = await db.pool.fetchrow(
        "select last_price from supplier_items where id = $1", item_ids["MILK PWDR 2.5KG NIDO"]
    )
    assert milk["last_price"] == Decimal("50.00")  # baseline moves only on confirm


# --- the revoked-key drill (plan.md §6 M3 done-when) -------------------------


@requires_db
async def test_revoked_key_drill_manual_path_survives(api, db):
    """With the Anthropic key revoked (provider None, exactly how main.py
    wires a missing key), upload + manual entry + list + detail + edit +
    confirm all still work: no financial workflow depends on AI being up
    (PRD §25.4). This is the M3 done-when as a permanent test."""
    app, client, _, fake_storage = api
    data = b"\xff\xd8drill-jpeg-bytes"

    # 1. Upload still ingests: document created, original stored byte for byte.
    resp = await client.post(
        "/api/documents",
        headers=AUTH,
        files={"file": ("invoice.jpg", data, "image/jpeg")},
        data={"branch_id": DEMO_BRANCH_ID},
    )
    assert resp.status_code == 201
    document_id = resp.json()["document_id"]
    path = f"{DEMO_TENANT_ID}/documents/{document_id}/original"
    assert fake_storage.objects[path] == data

    # 2. The extract job fails cleanly with no provider: the queue retries to
    # its 3-attempt end, the error is recorded, the document lands failed
    # (C1), no invoice appears - and the stored original survives for a
    # retry once the key is back.
    await drain_jobs(db, app, None, release_backoff=True)
    job = await db.pool.fetchrow("select * from jobs where kind = 'extract_document'")
    assert job["status"] == "failed"
    assert job["attempts"] == 3
    assert "no extraction provider configured" in job["last_error"]
    assert (await db.get_document(document_id, tenant_id=DEMO_TENANT_ID))["status"] == "failed"
    assert await db.get_invoice_by_document(document_id, tenant_id=DEMO_TENANT_ID) is None
    assert fake_storage.objects[path] == data

    # 3. Manual entry still works - the fallback the failed upload points to.
    resp = await client.post("/api/invoices/manual", headers=AUTH, json=manual_body())
    assert resp.status_code == 201
    invoice_id = resp.json()["id"]

    # 4. The list still serves: the manual invoice is there, and the failed
    # document produced no phantom row.
    resp = await client.get("/api/invoices", headers=AUTH)
    assert resp.status_code == 200
    assert [inv["id"] for inv in resp.json()["invoices"]] == [invoice_id]

    # 5. Detail, edit, and confirm all still work end to end.
    resp = await client.get(f"/api/invoices/{invoice_id}", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["confidence"]["document"]["status"] == "green"
    resp = await client.patch(
        f"/api/invoices/{invoice_id}/fields",
        headers=AUTH,
        json={"corrections": [{"line_index": 0, "field": "qty", "value": "12"}]},
    )
    assert resp.status_code == 200
    resp = await client.post(f"/api/invoices/{invoice_id}/confirm", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"
    # Confirm did its whole job: the catalog self-built, prices recorded.
    assert await db.pool.fetchval("select count(*) from supplier_item_prices") == 2


# --- price history ----------------------------------------------------------


@requires_db
async def test_price_history_is_ascending_with_the_item_header(api, db):
    app, client, *_ = api
    invoice = await extracted_invoice(api, db)
    await client.post(f"/api/invoices/{invoice['id']}/confirm", headers=AUTH)
    milk = await db.pool.fetchrow(
        "select * from supplier_items where canonical_name = 'MILK PWDR 2.5KG NIDO'"
    )
    # An older manual observation (no invoice), inserted after the confirmed
    # one: ordering must come from observed_at, not insertion order.
    await db.pool.execute(
        """
        insert into supplier_item_prices (tenant_id, supplier_item_id, price, observed_at)
        values ($1, $2, 50.50, now() - interval '7 days')
        """,
        milk["tenant_id"],
        milk["id"],
    )

    resp = await client.get(f"/api/supplier-items/{milk['id']}/prices", headers=AUTH)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["id"] == str(milk["id"])
    assert payload["canonical_name"] == "MILK PWDR 2.5KG NIDO"
    assert payload["unit"] == "sack"
    assert payload["pack_size"] == "2.5kg"
    assert payload["last_price"] == "54.500"
    assert payload["prev_price"] is None

    assert [row["price"] for row in payload["prices"]] == ["50.500", "54.500"]
    assert payload["prices"][0]["invoice_id"] is None
    assert payload["prices"][1]["invoice_id"] == str(invoice["id"])
    observed = [row["observed_at"] for row in payload["prices"]]
    assert observed == sorted(observed)

    resp = await client.get(f"/api/supplier-items/{uuid.uuid4()}/prices", headers=AUTH)
    assert resp.status_code == 404


# --- WP-26 on the review screen (the same door) -----------------------------


@requires_db
async def test_wp26_screen_cannot_confirm_a_null_total_and_the_patch_unblocks_it(api, db):
    """The founder's rule is about the invoice, not the door: an invoice with
    no total is not recordable from chat or from the screen. The screen can
    supply one through the same _apply_correction the chat grammar uses, and
    then it confirms."""
    app, client, *_ = api
    totals_less = good_invoice().model_copy(update={"subtotal": None, "tax": None, "total": None})
    invoice = await extracted_invoice(api, db, totals_less)
    assert invoice["total"] is None

    blocked = await client.post(f"/api/invoices/{invoice['id']}/confirm", headers=AUTH)
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "invoice has no total; set the total before confirming"
    assert await db.pool.fetchval("select count(*) from supplier_item_prices") == 0

    resp = await client.patch(
        f"/api/invoices/{invoice['id']}/fields",
        headers=AUTH,
        json={
            "corrections": [
                {"line_index": None, "field": "total", "value": "710.25"},
                {"line_index": None, "field": "tax", "value": "0"},
            ]
        },
    )
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["total"] == "710.25"
    assert detail["confidence"]["document"]["status"] == "green"
    # C8: typed on the screen, so `corrected_screen` - the screen cannot tell
    # a figure read off the paper from one worked out, and neither claim is
    # made. Only the chat reconstruction grammar says `reconstructed`.
    assert detail["provenance"]["total"]["origin"] == "corrected_screen"
    assert detail["provenance"]["total"]["actor"] == TEST_ACTOR

    resp = await client.post(f"/api/invoices/{invoice['id']}/confirm", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"
    assert await db.pool.fetchval("select count(*) from supplier_item_prices") == 2


@requires_db
async def test_wp26_screen_shows_a_reconstructed_total_as_reconstructed(api, db):
    # C6's provenance extension exists so the screen can show this; the API
    # side of it is the assertion here (the web app renders it already).
    app, client, *_ = api
    totals_less = good_invoice().model_copy(update={"subtotal": None, "tax": None, "total": None})
    invoice = await extracted_invoice(api, db, totals_less)
    await apply_chat_correction(db, "total 710.25 inc vat 5%")

    detail = (await client.get(f"/api/invoices/{invoice['id']}", headers=AUTH)).json()
    assert detail["total"] == "710.25"
    assert detail["provenance"]["total"]["origin"] == "reconstructed"
    assert detail["provenance"]["tax"]["origin"] == "reconstructed"
    assert detail["provenance"]["lines.0.unit_price"]["origin"] == "extracted"


@requires_db
async def test_wp28_screen_confirm_of_a_foreign_invoice_leaves_price_memory_alone(api, db):
    app, client, *_ = api
    usd = good_invoice().model_copy(update={"currency": "USD"})
    invoice = await extracted_invoice(api, db, usd)

    resp = await client.post(f"/api/invoices/{invoice['id']}/confirm", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"
    assert await db.pool.fetchval("select count(*) from supplier_item_prices") == 0
    assert await db.pool.fetchval("select count(*) from supplier_items") == 0


async def apply_chat_correction(db, text: str) -> str:
    """One chat correction through its own front door, so a screen test can set
    up state the chat grammar owns (WP-26's reconstruction)."""
    return await handle_inbound_text(db, DEMO_PHONE, text, datetime.datetime.now(datetime.UTC))


@requires_db
async def test_a_wrong_pack_size_can_be_corrected_and_cleared_from_the_screen(api, db):
    """The pack size is the one line field no arithmetic can check - C4's
    identities anchor on the line sum - and since 2026-08-29 it is sometimes
    derived from the item name rather than read off the page. A value nothing
    can verify and nobody can edit is a silent wrong number waiting to happen,
    so the screen must be able to both fix it and clear it.
    """
    app, client, *_ = api
    invoice = await extracted_invoice(api, db)
    url = f"/api/invoices/{invoice['id']}/fields"

    resp = await client.patch(
        url,
        headers=AUTH,
        json={"corrections": [{"line_index": 0, "field": "pack_size", "value": "5 kg"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["lines"][0]["pack_size"] == "5 kg"

    # "That pack is wrong and I do not know the right one" is a real answer.
    resp = await client.patch(
        url,
        headers=AUTH,
        json={"corrections": [{"line_index": 0, "field": "pack_size", "value": "-"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["lines"][0]["pack_size"] is None

    row = await db.pool.fetchrow(
        "select * from invoice_lines where invoice_id = $1 and position = 0", invoice["id"]
    )
    assert row["pack_size"] is None
    # C8: the human's correction is recorded against the field it moved.
    stored = await db.get_invoice(str(invoice["id"]), tenant_id=DEMO_TENANT_ID)
    assert stored["provenance"]["lines.0.pack_size"]["origin"] == "corrected_screen"


# --- dismiss a held duplicate (TODOS pull-forward, 2026-09-01) ---------------


async def held_duplicate(api, db, *, payment_kind: str = "credit", invoice_no: str | None = None):
    """The same paper sent twice, the way a salesman double-sends it: the first
    is recorded and awaits its OK, the second is held by WP-44. Driven through
    the real webhook path, never hand-inserted - the hold has to be the one the
    pipeline actually produces, pointer and all. `payment_kind` is the copy's:
    a cash copy is the D12 case, held on two grounds at once. `invoice_no`
    keeps a pair apart from papers a test already recorded."""
    app, client, *_ = api
    first = good_invoice()
    if invoice_no is not None:
        first.invoice_no = invoice_no
    prefix = "wamid" if invoice_no is None else invoice_no
    await post_webhook(client, wa_image_payload(message_id=f"{prefix}.in1"))
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(first)))
    second = good_invoice()
    second.invoice_no = first.invoice_no
    second.payment_kind = payment_kind
    await post_webhook(client, wa_image_payload(message_id=f"{prefix}.copy"))
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(second)))
    rows = await db.pool.fetch(
        "select * from invoices where invoice_no = $1 order by created_at, id", first.invoice_no
    )
    assert [row["status"] for row in rows] == ["awaiting_confirm", "needs_review"]
    original, copy = rows[0], rows[1]
    assert copy["duplicate_of_invoice_id"] == original["id"]
    assert original["duplicate_of_invoice_id"] is None
    return original, copy


@requires_db
async def test_dismissing_a_copy_clears_the_list_and_leaves_the_original_alone(api, db):
    """The founder's ask, end to end: the duplicate leaves the working list, the
    record that a double-send happened survives, and the invoice that was really
    recorded is untouched down to its price memory."""
    _, client, *_ = api
    original, copy = await held_duplicate(api, db)
    await client.post(f"/api/invoices/{original['id']}/confirm", headers=AUTH)
    prices_before = await db.pool.fetch("select * from supplier_item_prices order by id")
    assert prices_before  # confirming the original moved price memory

    resp = await client.post(f"/api/invoices/{copy['id']}/dismiss", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "dismissed"

    listed = (await client.get("/api/invoices", headers=AUTH)).json()["invoices"]
    assert [inv["id"] for inv in listed] == [str(original["id"])]

    events = await db.audit_events_for_subject("invoice", str(copy["id"]), tenant_id=DEMO_TENANT_ID)
    assert [(e["action"], e["actor"]) for e in events] == [("invoice.dismissed", TEST_ACTOR)]
    assert events[0]["detail"] == {
        "from_status": "needs_review",
        "duplicate_of_invoice_id": str(original["id"]),
    }

    after = await db.get_invoice(str(original["id"]), tenant_id=DEMO_TENANT_ID)
    assert after["status"] == "confirmed"
    assert after["total"] == original["total"]
    assert await db.pool.fetch("select * from supplier_item_prices order by id") == prices_before


@requires_db
async def test_the_record_survives_and_is_reachable_by_name(api, db):
    """Dismissal is not deletion. The row, its lines, its document and its photo
    all stay - only the working list stops carrying it."""
    _, client, *_ = api
    _, copy = await held_duplicate(api, db)
    await client.post(f"/api/invoices/{copy['id']}/dismiss", headers=AUTH)

    listed = (await client.get("/api/invoices?status=dismissed", headers=AUTH)).json()
    assert [inv["id"] for inv in listed["invoices"]] == [str(copy["id"])]
    assert (
        await db.pool.fetchval(
            "select count(*) from invoice_lines where invoice_id = $1", copy["id"]
        )
        > 0
    )
    document = await db.get_document(str(copy["document_id"]), tenant_id=DEMO_TENANT_ID)
    assert document is not None and document["status"] == "extracted"
    assert document["storage_path"]  # originals are immutable evidence


@requires_db
async def test_the_original_cannot_be_dismissed(api, db):
    """The guard that stops a paper being erased. When the copy lands, the
    original is usually still awaiting_confirm - so without this, a reviewer
    could dismiss the original and then the copy, and the invoice would be gone
    with one WhatsApp reply as its only trace."""
    _, client, *_ = api
    original, _ = await held_duplicate(api, db)
    resp = await client.post(f"/api/invoices/{original['id']}/dismiss", headers=AUTH)
    assert resp.status_code == 409
    assert "not a held duplicate" in resp.json()["detail"]
    assert (await db.get_invoice(str(original["id"]), tenant_id=DEMO_TENANT_ID))[
        "status"
    ] == "awaiting_confirm"


@requires_db
async def test_an_ordinary_invoice_cannot_be_dismissed(api, db):
    """Dismissal is not a general archive door. A cash hold or a plain invoice
    someone dislikes is M7's approvals question, not this one."""
    _, client, *_ = api
    invoice = await extracted_invoice(api, db)
    resp = await client.post(f"/api/invoices/{invoice['id']}/dismiss", headers=AUTH)
    assert resp.status_code == 409
    assert "not a held duplicate" in resp.json()["detail"]


@requires_db
async def test_a_confirmed_copy_cannot_be_dismissed(api, db):
    """The WhatsApp reply invites confirming a copy that really is a new
    invoice. Once someone takes that offer it is a financial record, and the
    door closes behind it."""
    _, client, *_ = api
    _, copy = await held_duplicate(api, db)
    first = await client.post(f"/api/invoices/{copy['id']}/confirm", headers=AUTH)
    assert first.status_code == 200

    resp = await client.post(f"/api/invoices/{copy['id']}/dismiss", headers=AUTH)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "invoice is confirmed; a recorded invoice cannot be dismissed"
    assert (await db.get_invoice(str(copy["id"]), tenant_id=DEMO_TENANT_ID))[
        "status"
    ] == "confirmed"


@requires_db
async def test_dismissing_twice_is_refused_and_writes_one_audit_row(api, db):
    _, client, *_ = api
    _, copy = await held_duplicate(api, db)
    first = await client.post(f"/api/invoices/{copy['id']}/dismiss", headers=AUTH)
    assert first.status_code == 200

    resp = await client.post(f"/api/invoices/{copy['id']}/dismiss", headers=AUTH)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "invoice is already dismissed"
    events = await db.audit_events_for_subject("invoice", str(copy["id"]), tenant_id=DEMO_TENANT_ID)
    assert len(events) == 1


@requires_db
async def test_dismissing_an_unknown_invoice_is_404(api, db):
    _, client, *_ = api
    resp = await client.post(f"/api/invoices/{uuid.uuid4()}/dismiss", headers=AUTH)
    assert resp.status_code == 404


@requires_db
async def test_a_dismissed_copy_cannot_be_confirmed_and_the_refusal_names_its_real_status(api, db):
    """Two tabs on the same held duplicate: one dismisses, the other presses
    Confirm. The guard refuses correctly either way - what this pins is that the
    sentence names `dismissed`, the status the row actually has, rather than the
    `needs_review` that was true when the endpoint first read it."""
    _, client, *_ = api
    _, copy = await held_duplicate(api, db)
    await client.post(f"/api/invoices/{copy['id']}/dismiss", headers=AUTH)

    resp = await client.post(f"/api/invoices/{copy['id']}/confirm", headers=AUTH)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "invoice is dismissed; cannot confirm"


@requires_db
async def test_a_dismissed_copy_cannot_be_edited(api, db):
    """_EDITABLE_STATUSES is an allowlist, so it refuses a dismissed invoice
    without anyone having to remember to add it. Pinned so it stays that way."""
    _, client, *_ = api
    _, copy = await held_duplicate(api, db)
    await client.post(f"/api/invoices/{copy['id']}/dismiss", headers=AUTH)

    resp = await client.patch(
        f"/api/invoices/{copy['id']}/fields",
        headers=AUTH,
        json={"corrections": [{"field": "total", "value": "1.00"}]},
    )
    assert resp.status_code == 409


@requires_db
async def test_the_detail_payload_names_the_paper_a_copy_duplicates(api, db):
    """What the review screen's banner is built from. An ordinary invoice pays
    nothing for it - the field is null and no second read happens."""
    _, client, *_ = api
    original, copy = await held_duplicate(api, db)

    detail = (await client.get(f"/api/invoices/{copy['id']}", headers=AUTH)).json()
    assert detail["duplicate_of"] == {
        "id": str(original["id"]),
        "supplier_name": "Gulf Foods Trading LLC",
        "invoice_no": "INV-1041",
        "currency": "AED",
        "total": "745.76",
        "created_at": detail["duplicate_of"]["created_at"],
    }
    assert (await client.get(f"/api/invoices/{original['id']}", headers=AUTH)).json()[
        "duplicate_of"
    ] is None


@requires_db
async def test_a_third_send_is_held_against_the_live_original(api, db):
    """Once a copy is dismissed it stops being an answer. The next send of the
    same paper is held against the invoice that is really recorded, so the reply
    names a date the reviewer has not thrown away."""
    app, client, *_ = api
    original, copy = await held_duplicate(api, db)
    await client.post(f"/api/invoices/{copy['id']}/dismiss", headers=AUTH)

    await post_webhook(client, wa_image_payload(message_id="wamid.copy3"))
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(good_invoice())))

    third = await db.pool.fetchrow(
        "select * from invoices order by created_at desc, id desc limit 1"
    )
    assert third["status"] == "needs_review"
    assert third["duplicate_of_invoice_id"] == original["id"]
