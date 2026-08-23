"""End-to-end M1 extraction flow against a real Postgres (TEST_DATABASE_URL),
with the Graph API, Supabase Storage, and the extraction provider mocked:

webhook POST -> ingest job (ack) -> extract_document job -> pipeline ->
draft invoice + lines + checks + extraction_runs -> summary reply. Plus the
repair, decline, z-report, provider-outage, and idempotency paths (WP-13).
"""

import datetime
import hashlib
import hmac
import json
from decimal import Decimal

import httpx
import pytest

from faida_api.contracts import JobKind
from faida_api.extraction.pipeline import (
    REPLY_FAILED,
    REPLY_NOT_INVOICE,
    REPLY_Z_REPORT,
)
from faida_api.extraction.schema import (
    Classification,
    ExtractedInvoice,
    ExtractedLine,
    ExtractionResult,
    RepairResult,
)
from faida_api.storage import Storage
from faida_api.wa import WhatsAppClient
from faida_api.webhook import router as webhook_router
from faida_api.worker import REPLY_MEDIA_RECEIVED, run_one_job

from .conftest import (
    DEMO_PHONE,
    DEMO_TENANT_ID,
    TEST_APP_SECRET,
    FakeExtraction,
    FakeMeta,
    FakeStorage,
    requires_db,
    wa_image_payload,
)

pytestmark = requires_db


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(TEST_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def api(settings, db):
    """A FastAPI app wired to the test DB and mock transports, plus the mocks."""
    from fastapi import FastAPI

    fake_meta = FakeMeta()
    fake_storage = FakeStorage()

    app = FastAPI()
    app.include_router(webhook_router)
    app.state.settings = settings
    app.state.db = db
    app.state.wa = WhatsAppClient(settings, transport=fake_meta.transport())
    app.state.storage = Storage(settings, transport=fake_storage.transport())

    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return app, client, fake_meta, fake_storage


async def post_webhook(client, payload: dict) -> httpx.Response:
    body = json.dumps(payload).encode()
    return await client.post("/webhook", content=body, headers={"X-Hub-Signature-256": sign(body)})


async def drain_jobs(db, app, provider, *, release_backoff: bool = False) -> None:
    """Run jobs until the queue is empty. With release_backoff, requeued jobs
    have their backoff cleared so the retry machinery runs to its 3-attempt end."""
    while True:
        while await run_one_job(db, app.state.wa, app.state.storage, provider):
            pass
        if not release_backoff:
            return
        queued = await db.pool.fetchval("select count(*) from jobs where status = 'queued'")
        if not queued:
            return
        await db.pool.execute("update jobs set run_after = now() where status = 'queued'")


def _line(name: str, qty: str, price: str, total: str, **kwargs) -> ExtractedLine:
    return ExtractedLine(
        raw_name=name,
        qty=Decimal(qty),
        unit_price=Decimal(price),
        line_total=Decimal(total),
        **kwargs,
    )


def good_invoice() -> ExtractedInvoice:
    """Fully reconciling two-line invoice (654.00 + 56.25 + tax 35.51 = 745.76)."""
    return ExtractedInvoice(
        supplier_name="Gulf Foods Trading LLC",
        invoice_no="INV-1041",
        invoice_date=datetime.date(2026, 8, 20),
        currency="AED",
        payment_kind="credit",
        lines=[
            _line("MILK PWDR 2.5KG NIDO", "12", "54.50", "654.00", unit="sack", pack_size="2.5kg"),
            _line("KARAK TEA DUST", "3", "18.75", "56.25"),
        ],
        subtotal=Decimal("710.25"),
        tax=Decimal("35.51"),
        total=Decimal("745.76"),
    )


def invoice_result(invoice: ExtractedInvoice) -> ExtractionResult:
    return ExtractionResult(classification=Classification.INVOICE, invoice=invoice)


async def outbound_bodies(db) -> list[str]:
    rows = await db.pool.fetch(
        "select payload from wa_messages where direction = 'out' order by id"
    )
    return [row["payload"]["text"] for row in rows]


async def test_happy_path_photo_to_draft_invoice(api, db):
    app, client, fake_meta, fake_storage = api
    provider = FakeExtraction(result=invoice_result(good_invoice()))

    assert (await post_webhook(client, wa_image_payload())).status_code == 200
    await drain_jobs(db, app, provider)

    # C1: extracted with the classification recorded.
    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc["status"] == "extracted"
    assert doc["classification"] == "invoice"

    # The provider read the exact stored original.
    assert provider.extract_calls == [(fake_meta.media_bytes, "image/jpeg")]
    assert provider.repair_calls == []

    # Draft invoice: header fields, Decimal money, derived confidence.
    invoice = await db.get_invoice_by_document(str(doc["id"]))
    assert invoice["status"] == "draft"
    assert invoice["invoice_no"] == "INV-1041"
    assert invoice["invoice_date"] == datetime.date(2026, 8, 20)
    assert invoice["currency"] == "AED"
    assert invoice["payment_kind"] == "credit"
    assert invoice["subtotal"] == Decimal("710.25")
    assert invoice["tax"] == Decimal("35.51")
    assert invoice["total"] == Decimal("745.76")
    assert invoice["supplier_id"] is None  # no suppliers exist yet for this tenant
    assert invoice["supplier_name"] == "Gulf Foods Trading LLC"  # raw extracted name kept
    assert invoice["confidence"]["document"]["status"] == "green"
    assert invoice["confidence"]["lines"] == ["green", "green"]

    # Lines in document order with pack_size and per-line checks.
    lines = await db.pool.fetch(
        "select * from invoice_lines where invoice_id = $1 order by position", invoice["id"]
    )
    assert [ln["raw_name"] for ln in lines] == ["MILK PWDR 2.5KG NIDO", "KARAK TEA DUST"]
    assert lines[0]["qty"] == Decimal("12")
    assert lines[0]["unit"] == "sack"
    assert lines[0]["unit_price"] == Decimal("54.50")
    assert lines[0]["line_total"] == Decimal("654.00")
    assert lines[0]["pack_size"] == "2.5kg"
    for line in lines:
        assert line["checks"]["arith"] == "passed"
        assert line["checks"]["status"] == "green"
        # No supplier matched, so snapping never ran: neutral, not False.
        assert line["checks"]["snapped"] is None
        assert line["supplier_item_id"] is None

    # Run metadata recorded.
    run = await db.pool.fetchrow("select * from extraction_runs where document_id = $1", doc["id"])
    assert run["outcome"] == "extracted"
    assert run["repair_applied"] is False
    assert run["model_id"] == "fake-model"
    assert run["prompt_version"] == "v0"
    assert (run["input_tokens"], run["output_tokens"], run["latency_ms"]) == (100, 50, 7)

    # Exactly two outbound messages: the ack, then the summary.
    bodies = await outbound_bodies(db)
    assert bodies == [
        REPLY_MEDIA_RECEIVED,
        "Read it: Gulf Foods Trading LLC, 2 lines, total AED 745.76.",
    ]
    assert [m["text"]["body"] for m in fake_meta.sent] == bodies
    assert fake_meta.sent[-1]["to"] == DEMO_PHONE


async def test_repair_path_fixes_wrong_line_with_one_call(api, db):
    app, client, fake_meta, _ = api
    truth = good_invoice()
    misread = good_invoice()
    misread.lines[1].line_total = Decimal("65.25")  # 3 x 18.75 != 65.25
    provider = FakeExtraction(
        result=invoice_result(misread),
        repair_patch=RepairResult(
            lines={1: truth.lines[1]},
            subtotal=truth.subtotal,
            tax=truth.tax,
            total=truth.total,
        ),
    )

    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, provider)

    assert len(provider.repair_calls) == 1  # one scoped round, never a second

    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc["status"] == "extracted"
    invoice = await db.get_invoice_by_document(str(doc["id"]))
    line = await db.pool.fetchrow(
        "select * from invoice_lines where invoice_id = $1 and position = 1", invoice["id"]
    )
    assert line["line_total"] == Decimal("56.25")
    assert line["checks"]["arith"] == "passed"
    assert invoice["confidence"]["document"]["status"] == "green"

    run = await db.pool.fetchrow("select * from extraction_runs where document_id = $1", doc["id"])
    assert run["repair_applied"] is True
    # Tokens and latency summed across the extract + repair calls.
    assert (run["input_tokens"], run["output_tokens"], run["latency_ms"]) == (200, 100, 14)

    assert (await outbound_bodies(db))[-1] == (
        "Read it: Gulf Foods Trading LLC, 2 lines, total AED 745.76."
    )


async def test_meme_is_declined_without_an_invoice_row(api, db):
    app, client, *_ = api
    provider = FakeExtraction(result=ExtractionResult(classification=Classification.OTHER))

    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, provider)

    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc["status"] == "failed"
    assert doc["classification"] == "other"
    assert await db.pool.fetchval("select count(*) from invoices") == 0

    run = await db.pool.fetchrow("select * from extraction_runs where document_id = $1", doc["id"])
    assert run["outcome"] == "not_invoice"
    assert run["repair_applied"] is False

    assert await outbound_bodies(db) == [REPLY_MEDIA_RECEIVED, REPLY_NOT_INVOICE]


async def test_z_report_is_held_until_m5(api, db):
    app, client, *_ = api
    provider = FakeExtraction(result=ExtractionResult(classification=Classification.Z_REPORT))

    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, provider)

    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc["status"] == "failed"
    assert doc["classification"] == "z_report"
    assert await db.pool.fetchval("select count(*) from invoices") == 0
    assert (
        await db.pool.fetchval(
            "select outcome from extraction_runs where document_id = $1", doc["id"]
        )
        == "z_report"
    )

    assert await outbound_bodies(db) == [REPLY_MEDIA_RECEIVED, REPLY_Z_REPORT]


async def test_provider_down_retries_then_fails_with_one_reply(api, db):
    app, client, *_ = api
    provider = FakeExtraction(extract_error=RuntimeError("provider down"))

    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, provider, release_backoff=True)

    # 3 attempts (db.RETRY_LIMIT), then the job is dead.
    job = await db.pool.fetchrow("select * from jobs where kind = $1", JobKind.EXTRACT_DOCUMENT)
    assert job["status"] == "failed"
    assert job["attempts"] == 3
    assert len(provider.extract_calls) == 3

    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc["status"] == "failed"
    assert doc["classification"] is None  # never classified
    assert await db.pool.fetchval("select count(*) from invoices") == 0
    assert await db.pool.fetchval("select count(*) from extraction_runs") == 0

    # The §5 layer 6 reply goes out exactly once, on the final attempt.
    assert await outbound_bodies(db) == [REPLY_MEDIA_RECEIVED, REPLY_FAILED]


async def test_reextract_of_extracted_document_is_a_noop(api, db):
    app, client, *_ = api
    provider = FakeExtraction(result=invoice_result(good_invoice()))

    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, provider)
    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc["status"] == "extracted"

    await db.enqueue(JobKind.EXTRACT_DOCUMENT, {"document_id": str(doc["id"])})
    await drain_jobs(db, app, provider)

    assert len(provider.extract_calls) == 1  # the second job never hit the provider
    assert await db.pool.fetchval("select count(*) from invoices") == 1
    assert await db.pool.fetchval("select count(*) from extraction_runs") == 1
    assert len(await outbound_bodies(db)) == 2  # ack + summary, no duplicate reply
    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc["status"] == "extracted"


async def test_seeded_supplier_invoice_snaps_lines(api, db):
    """Plan.md §5 layer 4 in the extraction path (WP-22): a fuzzy supplier
    match attaches supplier_id, each line snaps against that supplier's
    catalog, and the snapped flag lands in the persisted checks jsonb -
    without an unknown item ever costing a line its green (M1 rule)."""
    app, client, *_ = api
    supplier_id = await db.pool.fetchval(
        "insert into suppliers (tenant_id, name) values ($1, $2) returning id",
        DEMO_TENANT_ID,
        "Gulf Foods Trading L.L.C.",  # extracted "Gulf Foods Trading LLC" scores 0.96
    )
    item_id = await db.pool.fetchval(
        """
        insert into supplier_items (tenant_id, supplier_id, canonical_name, unit, pack_size,
                                    last_price, last_price_at)
        values ($1, $2, 'Milk Powder 2.5kg', 'sack', '2.5kg', 50.50, now())
        returning id
        """,
        DEMO_TENANT_ID,
        supplier_id,
    )
    provider = FakeExtraction(result=invoice_result(good_invoice()))

    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, provider)

    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc["status"] == "extracted"
    invoice = await db.get_invoice_by_document(str(doc["id"]))
    assert invoice["supplier_id"] == supplier_id
    assert invoice["supplier_name"] == "Gulf Foods Trading LLC"  # raw, not the catalog spelling

    lines = await db.pool.fetch(
        "select * from invoice_lines where invoice_id = $1 order by position", invoice["id"]
    )
    # "MILK PWDR 2.5KG NIDO" snapped to the seeded item; the flag is in checks.
    assert lines[0]["supplier_item_id"] == item_id
    assert lines[0]["checks"]["snapped"] is True
    assert lines[0]["checks"]["status"] == "green"
    # "KARAK TEA DUST" is not in the catalog: snapped False, but the catalog
    # is empty on day one - an unknown item must not flip green to amber.
    assert lines[1]["supplier_item_id"] is None
    assert lines[1]["checks"]["snapped"] is False
    assert lines[1]["checks"]["arith"] == "passed"
    assert lines[1]["checks"]["status"] == "green"
    assert invoice["confidence"]["lines"] == ["green", "green"]

    # Extraction never moves the price baseline (that is confirm's job):
    # the seeded item's last_price is untouched and no history was appended.
    item = await db.pool.fetchrow("select * from supplier_items where id = $1", item_id)
    assert item["last_price"] == Decimal("50.50")
    assert item["prev_price"] is None
    assert await db.pool.fetchval("select count(*) from supplier_item_prices") == 0
