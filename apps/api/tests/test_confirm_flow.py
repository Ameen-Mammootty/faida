"""WP-21: the confirm flow (plan.md §6 M2, C1, C5).

Parser unit tests (pure, no DB) plus the end-to-end paths against a real
Postgres with Meta/storage/provider mocked at the transport layer: full
confirm, correction-then-confirm, nothing pending, cash hold, two-pending
disambiguation, duplicate OK, retry-must-not-double-confirm, and the
permanent M2 gate test (test_m2_gate_price_alert_over_a_week).
"""

import datetime
import hashlib
import hmac
import json
from decimal import Decimal

import httpx
import pytest

from faida_api.confirm import (
    Confirm,
    Corrections,
    LineFieldEdit,
    LineNameEdit,
    TotalsEdit,
    apply_edits,
    parse_reply,
)
from faida_api.extraction.schema import ExtractedInvoice, ExtractedLine
from faida_api.replies import REPLY_CLARIFY, REPLY_TEXT_ONBOARDING
from faida_api.storage import Storage
from faida_api.wa import WhatsAppClient
from faida_api.webhook import router as webhook_router
from faida_api.worker import run_one_job

from .conftest import (
    DEMO_PHONE,
    TEST_APP_SECRET,
    FakeExtraction,
    FakeMeta,
    FakeStorage,
    requires_db,
    wa_image_payload,
)
from .test_extraction_flow import drain_jobs, good_invoice, invoice_result, outbound_bodies

# --- parser: confirms -------------------------------------------------------


def test_parse_ok_variants():
    for text in ["OK", "ok", "okay", "Okay", " ok ", "ok!", "OK.", "\nOK\n", "..ok..", "OKAY!!"]:
        assert parse_reply(text) == Confirm(selector=None), text


def test_parse_ok_with_leading_number_selects_an_invoice():
    assert parse_reply("2 OK") == Confirm(selector=2)
    assert parse_reply("1 ok") == Confirm(selector=1)
    assert parse_reply("1. OK") == Confirm(selector=1)
    assert parse_reply("3, okay") == Confirm(selector=3)


def test_parse_near_misses_are_not_confirms():
    for text in ["okey", "o k", "book", "ok please", "please ok", "okok"]:
        assert not isinstance(parse_reply(text), Confirm), text


# --- parser: corrections ----------------------------------------------------


def test_parse_line_qty():
    assert parse_reply("line 1 qty 16") == Corrections(
        selector=None, edits=[LineFieldEdit(line_index=0, field="qty", value=Decimal("16"))]
    )


def test_parse_line_price_spellings():
    expected = Corrections(
        selector=None,
        edits=[LineFieldEdit(line_index=1, field="unit_price", value=Decimal("4.50"))],
    )
    for text in [
        "line 2 price 4.50",
        "Line 2 Price 4.50",
        "line 2 unit price 4.50",
        "LINE 2 UNIT_PRICE 4.50",
    ]:
        assert parse_reply(text) == expected, text


def test_parse_line_total_spellings():
    expected = Corrections(
        selector=None,
        edits=[LineFieldEdit(line_index=2, field="line_total", value=Decimal("56.25"))],
    )
    for text in ["line 3 total 56.25", "line 3 line total 56.25", "line 3 line_total 56.25"]:
        assert parse_reply(text) == expected, text


def test_parse_line_name_keeps_the_text_verbatim():
    assert parse_reply("line 2 name Karak Tea Dust") == Corrections(
        selector=None, edits=[LineNameEdit(line_index=1, name="Karak Tea Dust")]
    )


def test_parse_totals_block_edits():
    assert parse_reply("total 745.76") == Corrections(
        selector=None, edits=[TotalsEdit(field="total", value=Decimal("745.76"))]
    )
    assert parse_reply("Tax 35.51") == Corrections(
        selector=None, edits=[TotalsEdit(field="tax", value=Decimal("35.51"))]
    )
    assert parse_reply("subtotal 710.25") == Corrections(
        selector=None, edits=[TotalsEdit(field="subtotal", value=Decimal("710.25"))]
    )


def test_parse_multiple_edits_with_mixed_separators():
    assert parse_reply("line 1 qty 16, line 2 price 4.50; total 745.76\ntax 35.51") == Corrections(
        selector=None,
        edits=[
            LineFieldEdit(line_index=0, field="qty", value=Decimal("16")),
            LineFieldEdit(line_index=1, field="unit_price", value=Decimal("4.50")),
            TotalsEdit(field="total", value=Decimal("745.76")),
            TotalsEdit(field="tax", value=Decimal("35.51")),
        ],
    )


def test_parse_selector_with_correction():
    assert parse_reply("2 line 4 qty 16") == Corrections(
        selector=2, edits=[LineFieldEdit(line_index=3, field="qty", value=Decimal("16"))]
    )


def test_parse_tolerates_a_sentence_ending_number():
    assert parse_reply("line 1 qty 16.") == Corrections(
        selector=None, edits=[LineFieldEdit(line_index=0, field="qty", value=Decimal("16"))]
    )


def test_parse_rejects_garbage_negatives_and_nan():
    for text in [
        "",
        "   ",
        "hello",
        "16",
        "2",
        "line 1 qty -5",
        "line 1 price nan",
        "line 1 price NaN",
        "line 1 qty 1e3",
        "line 0 qty 5",
        "line 1 qty",
        "line 1 weight 5",
        "line one qty 5",
        "qty 16",
        "total -1",
        "tax two",
        "ok line 1 qty 5",
        "line 1 name ",
        "total 1,5",
        "line 1 qty 16, and also fix the tax",
    ]:
        assert parse_reply(text) is None, text


def test_apply_edits_merges_and_never_mutates_the_input():
    invoice = ExtractedInvoice(
        lines=[
            ExtractedLine(
                raw_name="a", qty=Decimal("2"), unit_price=Decimal("3"), line_total=Decimal("6")
            )
        ],
        subtotal=Decimal("6"),
        tax=Decimal("0"),
        total=Decimal("6"),
    )
    edited = apply_edits(
        invoice,
        [
            LineFieldEdit(line_index=0, field="qty", value=Decimal("4")),
            LineNameEdit(line_index=0, name="b"),
            TotalsEdit(field="total", value=Decimal("12")),
        ],
    )
    assert edited.lines[0].qty == Decimal("4")
    assert edited.lines[0].raw_name == "b"
    assert edited.lines[0].unit_price == Decimal("3")  # untouched fields survive
    assert edited.total == Decimal("12")
    assert invoice.lines[0].qty == Decimal("2")
    assert invoice.lines[0].raw_name == "a"
    assert invoice.total == Decimal("6")


# --- e2e harness ------------------------------------------------------------


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


def wa_text_payload(
    body: str, message_id: str = "wamid.txt1", from_phone: str = DEMO_PHONE
) -> dict:
    payload = wa_image_payload(message_id=message_id, from_phone=from_phone)
    msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    msg.update({"type": "text", "text": {"body": body}})
    del msg["image"]
    return payload


def madina_invoice() -> ExtractedInvoice:
    """A second supplier's reconciling one-line invoice (4 x 30.00 = 120.00)."""
    return ExtractedInvoice(
        supplier_name="Al Madina Trading",
        invoice_no="AM-77",
        currency="AED",
        payment_kind="credit",
        lines=[
            ExtractedLine(
                raw_name="BASMATI RICE 5KG",
                qty=Decimal("4"),
                unit_price=Decimal("30.00"),
                line_total=Decimal("120.00"),
            )
        ],
        subtotal=Decimal("120.00"),
        tax=Decimal("0.00"),
        total=Decimal("120.00"),
    )


ACK_GULF = (
    "Confirmed - Gulf Foods Trading LLC, AED 745.76 recorded. I'll watch these prices for you."
)
ACK_MADINA = "Confirmed - Al Madina Trading, AED 120.00 recorded. I'll watch these prices for you."


# --- e2e: confirm -----------------------------------------------------------


@requires_db
async def test_full_confirm_flow_records_prices_and_acks(api, db):
    app, client, *_ = api
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(good_invoice())))

    await post_webhook(client, wa_text_payload("OK", message_id="wamid.ok1"))
    await drain_jobs(db, app, None)

    # C1: the invoice is confirmed; the document stays at its ingest terminal.
    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc["status"] == "extracted"
    invoice = await db.get_invoice_by_document(str(doc["id"]))
    assert invoice["status"] == "confirmed"
    assert invoice["confirmed_at"] is not None

    # The catalog self-built and the baseline moved (plan.md §5 layer 4).
    supplier = await db.pool.fetchrow("select * from suppliers")
    assert supplier["name"] == "Gulf Foods Trading LLC"
    items = await db.pool.fetch("select * from supplier_items order by canonical_name")
    assert [item["canonical_name"] for item in items] == ["KARAK TEA DUST", "MILK PWDR 2.5KG NIDO"]
    assert [item["last_price"] for item in items] == [Decimal("18.75"), Decimal("54.50")]
    prices = await db.pool.fetch("select * from supplier_item_prices order by price")
    assert [row["price"] for row in prices] == [Decimal("18.75"), Decimal("54.50")]
    assert all(row["invoice_id"] == invoice["id"] for row in prices)

    # The receipt moment: supplier and total in the ack.
    assert (await outbound_bodies(db))[-1] == ACK_GULF


@requires_db
async def test_correction_rereplies_then_ok_confirms_the_corrected_values(api, db):
    app, client, *_ = api
    misread = good_invoice()
    misread.lines[0].qty = Decimal("2")  # 2 x 54.50 != 654.00; the empty repair leaves it amber
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(misread)))

    assert (
        "Line 1: the math doesn't add up (2 x 54.50 = 109.00 but the line says 654.00) "
        "- which is right?"
    ) in (await outbound_bodies(db))[-1]

    await post_webhook(client, wa_text_payload("line 1 qty 12", message_id="wamid.fix1"))
    await drain_jobs(db, app, None)

    # The re-reply is the composed reply of the corrected, now all-green state.
    assert (await outbound_bodies(db))[-1] == (
        "Read it: Gulf Foods Trading LLC, 2 lines, total AED 745.76.\nReply OK to confirm."
    )
    doc = await db.get_document_by_wa_message("wamid.in1")
    invoice = await db.get_invoice_by_document(str(doc["id"]))
    assert invoice["status"] == "awaiting_confirm"  # corrections never confirm
    assert invoice["confidence"]["lines"] == ["green", "green"]
    assert invoice["confidence"]["document"]["status"] == "green"
    line = await db.pool.fetchrow(
        "select * from invoice_lines where invoice_id = $1 and position = 0", invoice["id"]
    )
    assert line["qty"] == Decimal("12")
    assert line["checks"]["arith"] == "passed"
    assert line["checks"]["status"] == "green"

    await post_webhook(client, wa_text_payload("ok", message_id="wamid.ok1"))
    await drain_jobs(db, app, None)

    invoice = await db.get_invoice_by_document(str(doc["id"]))
    assert invoice["status"] == "confirmed"
    assert (await outbound_bodies(db))[-1] == ACK_GULF
    # The corrected values are what entered the price history.
    prices = await db.pool.fetch("select price from supplier_item_prices order by price")
    assert [row["price"] for row in prices] == [Decimal("18.75"), Decimal("54.50")]


@requires_db
async def test_ok_with_open_ambers_confirms_anyway(api, db):
    # The composer's closing promised "OK to confirm the rest".
    app, client, *_ = api
    misread = good_invoice()
    misread.lines[0].qty = Decimal("2")
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(misread)))

    await post_webhook(client, wa_text_payload("OK", message_id="wamid.ok1"))
    await drain_jobs(db, app, None)

    doc = await db.get_document_by_wa_message("wamid.in1")
    invoice = await db.get_invoice_by_document(str(doc["id"]))
    assert invoice["status"] == "confirmed"
    assert doc["status"] == "extracted"
    assert (await outbound_bodies(db))[-1] == ACK_GULF


@requires_db
async def test_ok_with_nothing_pending_gets_onboarding(api, db):
    app, client, *_ = api
    await post_webhook(client, wa_text_payload("OK"))
    await drain_jobs(db, app, None)
    assert await outbound_bodies(db) == [REPLY_TEXT_ONBOARDING]


@requires_db
async def test_cash_invoice_is_not_addressable_from_chat(api, db):
    # WP-24/M6: a needs_review cash invoice never resolves from chat; the
    # sender falls back to onboarding as if nothing were pending.
    app, client, *_ = api
    cash = good_invoice()
    cash.payment_kind = "cash"
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(cash)))

    await post_webhook(client, wa_text_payload("OK", message_id="wamid.ok1"))
    await drain_jobs(db, app, None)

    assert (await outbound_bodies(db))[-1] == REPLY_TEXT_ONBOARDING
    doc = await db.get_document_by_wa_message("wamid.in1")
    invoice = await db.get_invoice_by_document(str(doc["id"]))
    assert invoice["status"] == "needs_review"
    assert doc["status"] == "extracted"
    assert await db.pool.fetchval("select count(*) from supplier_item_prices") == 0


@requires_db
async def test_unparseable_text_with_a_pending_invoice_gets_the_clarify(api, db):
    app, client, *_ = api
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(good_invoice())))

    await post_webhook(client, wa_text_payload("thanks habibi", message_id="wamid.txt2"))
    await drain_jobs(db, app, None)

    assert (await outbound_bodies(db))[-1] == REPLY_CLARIFY
    doc = await db.get_document_by_wa_message("wamid.in1")
    invoice = await db.get_invoice_by_document(str(doc["id"]))
    assert invoice["status"] == "awaiting_confirm"  # a clarify never confirms


@requires_db
async def test_correction_naming_a_missing_line_points_at_the_count(api, db):
    app, client, *_ = api
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(good_invoice())))

    await post_webhook(client, wa_text_payload("line 9 qty 1", message_id="wamid.fix1"))
    await drain_jobs(db, app, None)

    assert (await outbound_bodies(db))[-1] == (
        "This invoice has 2 lines, so I can't fix line 9 - check the line number and resend."
    )


# --- e2e: several pending (C5 disambiguation) -------------------------------


async def two_pending(client, db, app) -> None:
    """Gulf Foods then Al Madina, creation times pinned so the newest-first
    numbered list is exact (10:05 and 11:30 Dubai time)."""
    await post_webhook(client, wa_image_payload(message_id="wamid.g1"))
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(good_invoice())))
    await post_webhook(client, wa_image_payload(message_id="wamid.m1"))
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(madina_invoice())))
    await db.pool.execute(
        "update invoices set created_at = '2026-08-22 06:05:00+00' "
        "where supplier_name = 'Gulf Foods Trading LLC'"
    )
    await db.pool.execute(
        "update invoices set created_at = '2026-08-22 07:30:00+00' "
        "where supplier_name = 'Al Madina Trading'"
    )


DISAMBIGUATION = (
    "You have 2 invoices waiting - which one?\n"
    "1. Al Madina Trading, AED 120.00, 22 Aug 11:30\n"
    "2. Gulf Foods Trading LLC, AED 745.76, 22 Aug 10:05\n"
    "Reply with the number first, like: 1 OK, or 1 line 2 qty 16."
)


@requires_db
async def test_two_pending_disambiguates_then_the_number_confirms_the_right_one(api, db):
    app, client, *_ = api
    await two_pending(client, db, app)

    # A bare OK and a bare correction both get the numbered list, unapplied.
    await post_webhook(client, wa_text_payload("OK", message_id="wamid.ok1"))
    await drain_jobs(db, app, None)
    assert (await outbound_bodies(db))[-1] == DISAMBIGUATION
    await post_webhook(client, wa_text_payload("line 1 qty 9", message_id="wamid.fix1"))
    await drain_jobs(db, app, None)
    assert (await outbound_bodies(db))[-1] == DISAMBIGUATION

    await post_webhook(client, wa_text_payload("1 OK", message_id="wamid.ok2"))
    await drain_jobs(db, app, None)

    assert (await outbound_bodies(db))[-1] == ACK_MADINA
    madina = await db.pool.fetchrow(
        "select * from invoices where supplier_name = 'Al Madina Trading'"
    )
    gulf = await db.pool.fetchrow(
        "select * from invoices where supplier_name = 'Gulf Foods Trading LLC'"
    )
    assert madina["status"] == "confirmed"
    assert gulf["status"] == "awaiting_confirm"  # the number picked, the other untouched
    prices = await db.pool.fetch("select price from supplier_item_prices")
    assert [row["price"] for row in prices] == [Decimal("30.00")]


@requires_db
async def test_out_of_range_number_gets_the_list_again(api, db):
    app, client, *_ = api
    await two_pending(client, db, app)
    await post_webhook(client, wa_text_payload("9 OK", message_id="wamid.ok1"))
    await drain_jobs(db, app, None)
    assert (await outbound_bodies(db))[-1] == DISAMBIGUATION
    assert await db.pool.fetchval("select count(*) from invoices where status='confirmed'") == 0


@requires_db
async def test_selector_routes_a_correction_to_the_numbered_invoice(api, db):
    app, client, *_ = api
    await two_pending(client, db, app)

    # Number 2 is Gulf Foods; rename its second line - checks stay green.
    await post_webhook(
        client, wa_text_payload("2 line 2 name Karak Chai Mix", message_id="wamid.fix1")
    )
    await drain_jobs(db, app, None)

    assert (await outbound_bodies(db))[-1] == (
        "Read it: Gulf Foods Trading LLC, 2 lines, total AED 745.76.\nReply OK to confirm."
    )
    gulf = await db.pool.fetchrow(
        "select * from invoices where supplier_name = 'Gulf Foods Trading LLC'"
    )
    assert gulf["status"] == "awaiting_confirm"
    line = await db.pool.fetchrow(
        "select * from invoice_lines where invoice_id = $1 and position = 1", gulf["id"]
    )
    assert line["raw_name"] == "Karak Chai Mix"
    madina_line = await db.pool.fetchrow(
        "select * from invoice_lines where invoice_id = "
        "(select id from invoices where supplier_name = 'Al Madina Trading')"
    )
    assert madina_line["raw_name"] == "BASMATI RICE 5KG"  # the other invoice untouched


# --- e2e: idempotency and races ---------------------------------------------


@requires_db
async def test_duplicate_ok_reacks_without_double_recording(api, db):
    app, client, *_ = api
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(good_invoice())))

    await post_webhook(client, wa_text_payload("OK", message_id="wamid.ok1"))
    await drain_jobs(db, app, None)
    await post_webhook(client, wa_text_payload("OK", message_id="wamid.ok2"))
    await drain_jobs(db, app, None)

    bodies = await outbound_bodies(db)
    assert bodies[-1] == bodies[-2] == ACK_GULF  # the ack again, never silence
    # Single price history: record_confirmed_prices stayed idempotent.
    assert await db.pool.fetchval("select count(*) from supplier_item_prices") == 2
    item = await db.pool.fetchrow(
        "select * from supplier_items where canonical_name = 'MILK PWDR 2.5KG NIDO'"
    )
    assert item["last_price"] == Decimal("54.50")
    assert item["prev_price"] is None  # the duplicate did not shift the baseline


@requires_db
async def test_worker_retry_after_failed_send_does_not_confirm_a_second_invoice(api, db):
    app, client, *_ = api
    await two_pending(client, db, app)

    # "1 OK" targets Al Madina (newest). The first attempt confirms it, then
    # the send blows up and the job requeues. On retry Gulf Foods is number 1
    # in the shrunken list - the retry guard must re-ack Al Madina instead of
    # confirming Gulf.
    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    broken_wa = WhatsAppClient(app.state.settings, transport=httpx.MockTransport(broken))

    await post_webhook(client, wa_text_payload("1 OK", message_id="wamid.ok1"))
    assert await run_one_job(db, broken_wa, app.state.storage) is True
    job = await db.pool.fetchrow("select * from jobs order by id desc limit 1")
    assert job["status"] == "queued" and job["attempts"] == 1

    await db.pool.execute("update jobs set run_after = now() where status = 'queued'")
    await drain_jobs(db, app, None)

    madina = await db.pool.fetchrow(
        "select * from invoices where supplier_name = 'Al Madina Trading'"
    )
    gulf = await db.pool.fetchrow(
        "select * from invoices where supplier_name = 'Gulf Foods Trading LLC'"
    )
    assert madina["status"] == "confirmed"
    assert gulf["status"] == "awaiting_confirm"  # never double-confirmed
    bodies = await outbound_bodies(db)
    assert bodies[-1] == ACK_MADINA
    assert bodies.count(ACK_MADINA) == 1  # the failed send recorded nothing
    prices = await db.pool.fetch("select price from supplier_item_prices")
    assert [row["price"] for row in prices] == [Decimal("30.00")]  # Al Madina only, once


# --- e2e: the M2 gate (plan.md §6 M2 "Done when") ---------------------------


@requires_db
async def test_m2_gate_price_alert_over_a_week(api, db):
    """Two invoices from the same supplier a week apart produce a correct
    'up AED X' alert in chat, and 'OK' records it. Permanent from the moment
    it first passed - a regression here is a P0 (plan.md §7.5)."""
    app, client, *_ = api

    week_ago = good_invoice()
    week_ago.invoice_no = "INV-0990"
    week_ago.invoice_date = datetime.date(2026, 8, 13)
    week_ago.lines[0].unit_price = Decimal("50.50")
    week_ago.lines[0].line_total = Decimal("606.00")  # 12 x 50.50
    week_ago.subtotal = Decimal("662.25")
    week_ago.tax = Decimal("33.11")
    week_ago.total = Decimal("695.36")

    await post_webhook(client, wa_image_payload(message_id="wamid.week1"))
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(week_ago)))
    await post_webhook(client, wa_text_payload("OK", message_id="wamid.ok1"))
    await drain_jobs(db, app, None)
    assert (await outbound_bodies(db))[-1] == (
        "Confirmed - Gulf Foods Trading LLC, AED 695.36 recorded. I'll watch these prices for you."
    )

    # Age the first confirm by a week so the history really is a week apart.
    await db.pool.execute(
        "update supplier_item_prices set observed_at = observed_at - interval '7 days'"
    )
    await db.pool.execute(
        "update supplier_items set last_price_at = last_price_at - interval '7 days'"
    )
    await db.pool.execute("update invoices set confirmed_at = confirmed_at - interval '7 days'")

    await post_webhook(client, wa_image_payload(message_id="wamid.week2"))
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(good_invoice())))

    # The money moment: the extraction reply carries the correct alert.
    assert (await outbound_bodies(db))[-1] == (
        "Read it: Gulf Foods Trading LLC, 2 lines, total AED 745.76.\n"
        "MILK PWDR 2.5KG NIDO up AED 4.00 (50.50 to 54.50) since your last purchase.\n"
        "Reply OK to confirm."
    )

    await post_webhook(client, wa_text_payload("OK", message_id="wamid.ok2"))
    await drain_jobs(db, app, None)
    assert (await outbound_bodies(db))[-1] == ACK_GULF

    # History holds both prices; prev/last shifted correctly.
    milk = await db.pool.fetchrow(
        "select * from supplier_items where canonical_name = 'MILK PWDR 2.5KG NIDO'"
    )
    assert milk["prev_price"] == Decimal("50.50")
    assert milk["last_price"] == Decimal("54.50")
    history = await db.pool.fetch(
        "select price from supplier_item_prices where supplier_item_id = $1 order by observed_at",
        milk["id"],
    )
    assert [row["price"] for row in history] == [Decimal("50.50"), Decimal("54.50")]
