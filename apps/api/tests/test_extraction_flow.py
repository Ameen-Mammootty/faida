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
from faida_api.extraction.schema import (
    Classification,
    ExtractedInvoice,
    ExtractedLine,
    ExtractionResult,
    RepairResult,
)
from faida_api.replies import (
    CASH_HOLD_NOTE,
    CLOSING_ALL_GREEN,
    CLOSING_WITH_AMBERS,
    REPLY_EXTRACTION_FAILED,
    REPLY_MEDIA_RECEIVED,
    REPLY_NOT_INVOICE,
    REPLY_Z_REPORT,
    compose_duplicate_hold_reply,
    render_duplicate_note,
)
from faida_api.storage import Storage
from faida_api.wa import WhatsAppClient
from faida_api.webhook import router as webhook_router
from faida_api.worker import run_one_job

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


async def seed_supplier_with_items(db, items: list[dict]) -> tuple[str, dict[str, str]]:
    """Seed the Gulf Foods supplier (the extracted 'Gulf Foods Trading LLC'
    fuzzy-matches it at 0.96) plus catalog items with optional last_price;
    returns (supplier_id, {canonical_name: item_id})."""
    supplier_id = await db.pool.fetchval(
        "insert into suppliers (tenant_id, name) values ($1, $2) returning id",
        DEMO_TENANT_ID,
        "Gulf Foods Trading L.L.C.",
    )
    item_ids: dict[str, str] = {}
    for item in items:
        item_ids[item["canonical_name"]] = await db.pool.fetchval(
            """
            insert into supplier_items (tenant_id, supplier_id, canonical_name, unit,
                                        pack_size, last_price, last_price_at)
            values ($1, $2, $3, $4, $5, $6, now())
            returning id
            """,
            DEMO_TENANT_ID,
            supplier_id,
            item["canonical_name"],
            item.get("unit"),
            item.get("pack_size"),
            item.get("last_price"),
        )
    return supplier_id, item_ids


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

    # Draft invoice: header fields, Decimal money, derived confidence. The
    # reply asks for an OK, so the invoice awaits it (C1, WP-21 confirms it).
    invoice = await db.get_invoice_by_document(str(doc["id"]), tenant_id=DEMO_TENANT_ID)
    assert invoice["status"] == "awaiting_confirm"
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

    # Exactly two outbound messages: the ack, then compose_invoice_reply's
    # output - summary plus the confirm prompt (WP-20 composer swap).
    bodies = await outbound_bodies(db)
    assert bodies == [
        REPLY_MEDIA_RECEIVED,
        "Read it: Gulf Foods Trading LLC, 2 lines, total AED 745.76, dated 20 Aug 2026.\n"
        "Reply OK to confirm.",
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
    invoice = await db.get_invoice_by_document(str(doc["id"]), tenant_id=DEMO_TENANT_ID)
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
        "Read it: Gulf Foods Trading LLC, 2 lines, total AED 745.76, dated 20 Aug 2026.\n"
        "Reply OK to confirm."
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
    assert await outbound_bodies(db) == [REPLY_MEDIA_RECEIVED, REPLY_EXTRACTION_FAILED]


async def test_truncated_read_fails_loudly_and_persists_no_partial_invoice(api, db):
    """WP-19 acceptance: a simulated truncated response is a failure, never a
    shorter answer - no draft invoice whose header still reconciles, document
    failed, one honest reply. The provider raises on stop_reason='max_tokens'
    (test_anthropic_provider), so the flow sees exactly this error shape."""
    app, client, *_ = api
    provider = FakeExtraction(
        extract_error=ValueError(
            "output truncated at the 16000-token ceiling "
            "(stop_reason='max_tokens'): refusing a partial read"
        )
    )

    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, provider, release_backoff=True)

    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc["status"] == "failed"
    assert await db.pool.fetchval("select count(*) from invoices") == 0
    assert await db.pool.fetchval("select count(*) from invoice_lines") == 0
    assert await outbound_bodies(db) == [REPLY_MEDIA_RECEIVED, REPLY_EXTRACTION_FAILED]


async def test_reextract_of_extracted_document_is_a_noop(api, db):
    app, client, *_ = api
    provider = FakeExtraction(result=invoice_result(good_invoice()))

    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, provider)
    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc["status"] == "extracted"

    # The retry shape the worker actually produces: the same job row queued
    # again (a second row per document is refused by the 0018 index).
    await db.pool.execute(
        "update jobs set status = 'queued', run_after = now() where kind = $1",
        JobKind.EXTRACT_DOCUMENT,
    )
    await drain_jobs(db, app, provider)

    assert len(provider.extract_calls) == 1  # the second run never hit the provider
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
    supplier_id, item_ids = await seed_supplier_with_items(
        db,
        [
            {
                "canonical_name": "Milk Powder 2.5kg",
                "unit": "sack",
                "pack_size": "2.5kg",
                "last_price": Decimal("50.50"),
            }
        ],
    )
    item_id = item_ids["Milk Powder 2.5kg"]
    provider = FakeExtraction(result=invoice_result(good_invoice()))

    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, provider)

    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc["status"] == "extracted"
    invoice = await db.get_invoice_by_document(str(doc["id"]), tenant_id=DEMO_TENANT_ID)
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


async def test_price_alert_fires_in_the_extraction_reply(api, db):
    """WP-23 (plan.md §6 M2, the demo's money moment): every snapped line
    whose price moved by >= 5% and >= AED 0.25 alerts in the extraction reply,
    largest absolute move first, falling prices included - and the baseline
    stays untouched until confirm."""
    app, client, *_ = api
    _, item_ids = await seed_supplier_with_items(
        db,
        [
            {
                "canonical_name": "Milk Powder 2.5kg",
                "unit": "sack",
                "pack_size": "2.5kg",
                "last_price": Decimal("51.90"),  # extracted 54.50: up 2.60 (5.01%)
            },
            {
                "canonical_name": "Karak Tea Dust",
                "last_price": Decimal("22.00"),  # extracted 18.75: down 3.25 (14.8%)
            },
        ],
    )
    provider = FakeExtraction(result=invoice_result(good_invoice()))

    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, provider)

    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc["status"] == "extracted"
    invoice = await db.get_invoice_by_document(str(doc["id"]), tenant_id=DEMO_TENANT_ID)
    assert invoice["status"] == "awaiting_confirm"

    # Alerts ordered by absolute delta descending: karak's 3.25 (a falling
    # price - still signal) before milk's 2.60, regardless of line order.
    assert (await outbound_bodies(db))[-1] == (
        "Read it: Gulf Foods Trading LLC, 2 lines, total AED 745.76, dated 20 Aug 2026.\n"
        "Karak Tea Dust down AED 3.25 (22.00 to 18.75) since your last purchase.\n"
        "Milk Powder 2.5kg up AED 2.60 (51.90 to 54.50) since your last purchase.\n"
        "Reply OK to confirm."
    )

    # The baseline rule: alerting must not move last_price/prev_price or
    # append history - only confirm does (record_confirmed_prices, WP-21).
    for name, last in (("Milk Powder 2.5kg", "51.90"), ("Karak Tea Dust", "22.00")):
        item = await db.pool.fetchrow("select * from supplier_items where id = $1", item_ids[name])
        assert item["last_price"] == Decimal(last)
        assert item["prev_price"] is None
    assert await db.pool.fetchval("select count(*) from supplier_item_prices") == 0


async def test_no_alert_when_either_threshold_is_unmet(api, db):
    """Both thresholds must hold (plan.md §6 M2): a 1.9% move fails the pct
    leg even at AED 1.00, and a 5% move on a cheap item fails the abs leg -
    neither line alerts even though both snapped."""
    app, client, *_ = api
    await seed_supplier_with_items(
        db,
        [
            {
                "canonical_name": "Milk Powder 2.5kg",
                "unit": "sack",
                "pack_size": "2.5kg",
                "last_price": Decimal("53.50"),  # extracted 54.50: 1.00 but only 1.9%
            },
            {
                "canonical_name": "Paratha Wrap",
                "last_price": Decimal("0.80"),  # extracted 0.84: 5.0% but only 0.04
            },
        ],
    )
    invoice = ExtractedInvoice(
        supplier_name="Gulf Foods Trading LLC",
        invoice_no="INV-2044",
        invoice_date=datetime.date(2026, 8, 20),
        currency="AED",
        payment_kind="credit",
        lines=[
            _line("MILK PWDR 2.5KG NIDO", "12", "54.50", "654.00", pack_size="2.5kg"),
            _line("PARATHA WRAP", "20", "0.84", "16.80"),
        ],
        subtotal=Decimal("670.80"),
        tax=Decimal("33.54"),
        total=Decimal("704.34"),
    )
    provider = FakeExtraction(result=invoice_result(invoice))

    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, provider)

    doc = await db.get_document_by_wa_message("wamid.in1")
    row = await db.get_invoice_by_document(str(doc["id"]), tenant_id=DEMO_TENANT_ID)
    lines = await db.pool.fetch(
        "select * from invoice_lines where invoice_id = $1 order by position", row["id"]
    )
    # Both lines snapped - the silence is the thresholds, not a missed match.
    assert all(line["supplier_item_id"] is not None for line in lines)

    assert (await outbound_bodies(db))[-1] == (
        "Read it: Gulf Foods Trading LLC, 2 lines, total AED 704.34, dated 20 Aug 2026.\n"
        "Reply OK to confirm."
    )


async def test_cash_invoice_is_held_for_review(api, db):
    """WP-24 (PRD §21): payment_kind cash persists as needs_review and the
    reply notes the owner-approval hold instead of inviting an OK - the
    document itself still extracts normally."""
    app, client, *_ = api
    cash = good_invoice()
    cash.payment_kind = "cash"
    provider = FakeExtraction(result=invoice_result(cash))

    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, provider)

    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc["status"] == "extracted"
    assert doc["classification"] == "invoice"
    row = await db.get_invoice_by_document(str(doc["id"]), tenant_id=DEMO_TENANT_ID)
    assert row["status"] == "needs_review"
    assert row["payment_kind"] == "cash"

    reply = (await outbound_bodies(db))[-1]
    assert reply == (
        "Read it: Gulf Foods Trading LLC, 2 lines, total AED 745.76, dated 20 Aug 2026.\n"
        + CASH_HOLD_NOTE
    )
    assert CLOSING_ALL_GREEN not in reply  # a cash invoice cannot confirm from chat


async def test_unrepaired_failure_asks_the_amber_question(api, db):
    """Plan.md §5 layer 5: a line still failing after the one repair round
    stays amber and gets its specific question in the reply - never silence."""
    app, client, *_ = api
    misread = good_invoice()
    misread.lines[1].line_total = Decimal("65.25")  # 3 x 18.75 != 65.25
    # FakeExtraction's default repair patch is empty: the re-read fixes nothing.
    provider = FakeExtraction(result=invoice_result(misread))

    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, provider)

    assert len(provider.repair_calls) == 1  # repair ran and could not fix it

    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc["status"] == "extracted"
    invoice = await db.get_invoice_by_document(str(doc["id"]), tenant_id=DEMO_TENANT_ID)
    assert invoice["status"] == "awaiting_confirm"
    assert invoice["confidence"]["lines"] == ["green", "amber"]

    reply = (await outbound_bodies(db))[-1]
    assert (
        "Line 2: the math doesn't add up (3 x 18.75 = 56.25 but the line says 65.25) "
        "- which is right?"
    ) in reply
    assert reply.splitlines()[-1] == CLOSING_WITH_AMBERS


async def test_printed_currency_is_stored_and_replied_as_iso_code(api, db):
    """Found live 2026-08-24: a real cash invoice printed 'dirhams', the model
    copied it as printed (C3), and the reply said 'total dirhams 402.00'. The
    ISO code is derived once in the pipeline, so the row and the reply agree."""
    app, client, fake_meta, fake_storage = api
    printed = good_invoice().model_copy(update={"currency": "dirhams"})
    provider = FakeExtraction(result=invoice_result(printed))

    assert (await post_webhook(client, wa_image_payload())).status_code == 200
    await drain_jobs(db, app, provider)

    doc = await db.get_document_by_wa_message("wamid.in1")
    invoice = await db.get_invoice_by_document(str(doc["id"]), tenant_id=DEMO_TENANT_ID)
    assert invoice["currency"] == "AED"
    reply = (await outbound_bodies(db))[-1]
    assert "total AED 745.76" in reply
    assert "dirhams" not in reply


# --- WP-44: duplicate invoice hold ------------------------------------------


async def test_same_paper_twice_is_held_naming_the_first(api, db):
    app, client, *_ = api
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(good_invoice())))
    await post_webhook(client, wa_image_payload(message_id="wamid.dup2"))
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(good_invoice())))

    rows = await db.pool.fetch("select * from invoices order by created_at, id")
    assert [row["status"] for row in rows] == ["awaiting_confirm", "needs_review"]
    # The hold is recorded, not just spoken: the copy names the paper it copies,
    # and the original names nothing. That pointer is what the review screen
    # reads, and what the dismiss door keys on - so a bug that set it on every
    # invoice, or on none, is caught right here.
    assert rows[1]["duplicate_of_invoice_id"] == rows[0]["id"]
    assert rows[0]["duplicate_of_invoice_id"] is None
    # Both papers stay recorded - held, never dropped - and only the first is
    # reachable from chat (C5 lists awaiting_confirm only).
    assert (await outbound_bodies(db))[-1] == compose_duplicate_hold_reply(
        "Gulf Foods Trading LLC",
        "INV-1041",
        "AED",
        Decimal("745.76"),
        rows[0]["created_at"].date(),
    )


async def test_similar_paper_gets_a_note_never_a_hold(api, db):
    app, client, *_ = api
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(good_invoice())))
    # Same supplier, same day, same total - but a different invoice number:
    # plausibly a second delivery, so it proceeds with a note, never a hold.
    second = good_invoice().model_copy(update={"invoice_no": "INV-2077"})
    await post_webhook(client, wa_image_payload(message_id="wamid.sim2"))
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(second)))

    rows = await db.pool.fetch("select * from invoices order by created_at, id")
    assert [row["status"] for row in rows] == ["awaiting_confirm", "awaiting_confirm"]
    reply = (await outbound_bodies(db))[-1]
    assert reply.splitlines()[-1] == render_duplicate_note(
        "Gulf Foods Trading LLC", "INV-1041", rows[0]["created_at"].date()
    )
    assert reply.splitlines()[-2] == CLOSING_ALL_GREEN


async def test_another_suppliers_same_number_is_not_held(api, db):
    app, client, *_ = api
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(good_invoice())))
    other = good_invoice().model_copy(update={"supplier_name": "Al Madina Trading"})
    await post_webhook(client, wa_image_payload(message_id="wamid.oth2"))
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(other)))

    reply = (await outbound_bodies(db))[-1]
    assert "already recorded" not in reply
    assert "Note:" not in reply
    statuses = await db.pool.fetch("select status from invoices")
    assert [row["status"] for row in statuses] == ["awaiting_confirm", "awaiting_confirm"]
