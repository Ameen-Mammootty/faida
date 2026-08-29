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
    AmbiguousDateEdit,
    Confirm,
    Corrections,
    CurrencyEdit,
    DateEdit,
    InvoiceNoEdit,
    LineFieldEdit,
    LineNameEdit,
    LinePackSizeEdit,
    MissingVatRateEdit,
    ReconstructedTotalEdit,
    TotalsEdit,
    apply_edits,
    edited_field_keys,
    parse_reply,
    reconstructed_field_keys,
)
from faida_api.extraction.schema import ExtractedInvoice, ExtractedLine, LineKind
from faida_api.replies import (
    QUESTION_MISSING_DATE,
    QUESTION_MISSING_INVOICE_NO,
    REPLY_CLARIFY,
    REPLY_TEXT_ONBOARDING,
    compose_ambiguous_date_reply,
    compose_total_needed_reply,
    compose_vat_rate_reply,
)
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
from .test_extraction_flow import (
    drain_jobs,
    good_invoice,
    invoice_result,
    outbound_bodies,
    seed_supplier_with_items,
)

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


def test_parse_line_pack_size_accepts_every_spelling():
    expected = Corrections(selector=None, edits=[LinePackSizeEdit(line_index=1, pack_size="5kg")])
    for text in [
        "line 2 pack size 5kg",
        "line 2 pack_size 5kg",
        "line 2 pack 5kg",
        "line 2 size 5kg",
    ]:
        assert parse_reply(text) == expected, text


def test_a_person_can_clear_a_pack_size_they_cannot_vouch_for():
    # The pack is the denominator M5 divides a price by and no arithmetic can
    # check it, so "that is wrong and I do not know the right one" has to be
    # sayable. It clears rather than storing a dash.
    for text in ["line 2 pack size -", "line 2 pack none", "line 2 pack size n/a"]:
        assert parse_reply(text) == Corrections(
            selector=None, edits=[LinePackSizeEdit(line_index=1, pack_size=None)]
        ), text


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


def test_parse_date_edits_use_the_extraction_day_first_rules():
    assert parse_reply("date 5/7/26") == Corrections(
        selector=None, edits=[DateEdit(value=datetime.date(2026, 7, 5))]
    )
    assert parse_reply("invoice date 9 July 2026") == Corrections(
        selector=None, edits=[DateEdit(value=datetime.date(2026, 7, 9))]
    )
    assert parse_reply("2 date 2026-07-05") == Corrections(
        selector=2, edits=[DateEdit(value=datetime.date(2026, 7, 5))]
    )


def test_parse_date_without_a_year_is_ambiguous_not_unparseable():
    # Distinct from None: the flow answers with the year question, not the
    # generic clarify (WP-27: "5/7" with no year is not a date).
    assert parse_reply("date 5/7") == Corrections(
        selector=None, edits=[AmbiguousDateEdit(text="5/7")]
    )
    assert parse_reply("date tomorrow") is None


def test_parse_invoice_no_spellings_keep_the_value_verbatim():
    for text in ("invoice no 4471", "invoice number 4471", "inv no 4471", "invoice # 4471"):
        assert parse_reply(text) == Corrections(
            selector=None, edits=[InvoiceNoEdit(value="4471")]
        ), text
    assert parse_reply("invoice no AAF 2214") == Corrections(
        selector=None, edits=[InvoiceNoEdit(value="AAF 2214")]
    )


def test_apply_edits_sets_date_and_invoice_no():
    invoice = ExtractedInvoice(total=Decimal("6"))
    edited = apply_edits(
        invoice,
        [
            DateEdit(value=datetime.date(2026, 7, 5)),
            InvoiceNoEdit(value="AAF 2214"),
        ],
    )
    assert edited.invoice_date == datetime.date(2026, 7, 5)
    assert edited.invoice_no == "AAF 2214"
    assert invoice.invoice_date is None and invoice.invoice_no is None


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
        invoice_date=datetime.date(2026, 8, 21),
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
        "Read it: Gulf Foods Trading LLC, 2 lines, total AED 745.76, dated 20 Aug 2026.\n"
        "Reply OK to confirm."
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
    # WP-24/M7: a needs_review cash invoice never resolves from chat; the
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
        "Read it: Gulf Foods Trading LLC, 2 lines, total AED 745.76, dated 20 Aug 2026.\n"
        "Reply OK to confirm."
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
        "Read it: Gulf Foods Trading LLC, 2 lines, total AED 745.76, dated 20 Aug 2026.\n"
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


# --- e2e: required-field ambers (WP-25) + dates beyond ISO (WP-27) ----------


@requires_db
async def test_missing_date_is_asked_and_the_answer_lands_via_the_grammar(api, db):
    app, client, *_ = api
    dateless = good_invoice().model_copy(update={"invoice_date": None})
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(dateless)))
    reply = (await outbound_bodies(db))[-1]
    assert QUESTION_MISSING_DATE in reply.splitlines()

    # "5/7" has no year: the specific year question, and nothing applied.
    await post_webhook(client, wa_text_payload("date 5/7", message_id="wamid.amb"))
    await drain_jobs(db, app, None)
    assert (await outbound_bodies(db))[-1] == compose_ambiguous_date_reply("5/7")
    assert (await db.pool.fetchval("select invoice_date from invoices")) is None

    # The full date lands via the correction grammar, read day-first.
    await post_webhook(client, wa_text_payload("date 5/7/26", message_id="wamid.date"))
    await drain_jobs(db, app, None)
    reply = (await outbound_bodies(db))[-1]
    assert "dated 5 Jul 2026" in reply.splitlines()[0]
    assert QUESTION_MISSING_DATE not in reply.splitlines()
    assert (await db.pool.fetchval("select invoice_date from invoices")) == datetime.date(
        2026, 7, 5
    )
    # C8: the corrected date is stamped as a chat correction by its sender.
    provenance = await db.pool.fetchval("select provenance from invoices")
    assert provenance["invoice_date"]["origin"] == "corrected_chat"
    assert provenance["invoice_date"]["actor"] == f"whatsapp:{DEMO_PHONE}"

    # And the invoice proceeds.
    await post_webhook(client, wa_text_payload("OK", message_id="wamid.ok9"))
    await drain_jobs(db, app, None)
    assert (await db.pool.fetchval("select status from invoices")) == "confirmed"


@requires_db
async def test_missing_invoice_no_is_asked_and_corrected(api, db):
    app, client, *_ = api
    numberless = good_invoice().model_copy(update={"invoice_no": None})
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(numberless)))
    assert QUESTION_MISSING_INVOICE_NO in (await outbound_bodies(db))[-1].splitlines()

    await post_webhook(client, wa_text_payload("invoice no INV-1041", message_id="wamid.no1"))
    await drain_jobs(db, app, None)
    reply = (await outbound_bodies(db))[-1]
    assert QUESTION_MISSING_INVOICE_NO not in reply.splitlines()
    assert (await db.pool.fetchval("select invoice_no from invoices")) == "INV-1041"


@requires_db
async def test_correction_keeps_discount_and_charge_lines_in_validation(api, db):
    """The correction path rebuilds the C3 invoice from the rows; line_kind,
    the discount and the rounding must ride along or a correction on a
    discounted invoice re-validates against the wrong identity and fails a
    correct invoice into amber (the WP-18 shape, resurfacing via chat)."""
    app, client, *_ = api
    invoice = ExtractedInvoice(
        supplier_name="Al Karak Sweets",  # not in the seed: snapping stays out of the way
        invoice_no="AKS-9",
        invoice_date=datetime.date(2026, 8, 22),
        currency="AED",
        payment_kind="credit",
        lines=[
            ExtractedLine(
                raw_name="Karak mix",
                qty=Decimal("2"),
                unit_price=Decimal("50.00"),
                line_total=Decimal("100.00"),
            ),
            ExtractedLine(
                raw_name="Chilled delivery",
                line_kind=LineKind.CHARGE,
                qty=Decimal("1"),
                unit_price=Decimal("25.00"),
                line_total=Decimal("25.00"),
            ),
        ],
        subtotal=Decimal("100.00"),
        tax=Decimal("0.00"),
        discount_total=Decimal("10.00"),
        total=Decimal("115.00"),
    )
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(invoice)))
    assert (await outbound_bodies(db))[-1].endswith("Reply OK to confirm.")

    await post_webhook(client, wa_text_payload("line 1 qty 2", message_id="wamid.fix"))
    await drain_jobs(db, app, None)
    reply = (await outbound_bodies(db))[-1]
    assert "don't add up" not in reply
    assert "doesn't match" not in reply
    assert reply.endswith("Reply OK to confirm.")


# --- parser: WP-26 reconstruction and WP-28 currency ------------------------


def test_parse_reconstructed_total_with_a_rate():
    for text in [
        "total 930.00 inc vat 5%",
        "total 930.00 incl vat 5%",
        "total 930.00 including vat 5",
        "TOTAL 930.00 With VAT 5 %",
    ]:
        assert parse_reply(text) == Corrections(
            selector=None,
            edits=[ReconstructedTotalEdit(value=Decimal("930.00"), vat_rate=Decimal("0.05"))],
        ), text


def test_parse_reconstructed_total_without_vat():
    for text in [
        "total 930.00 no vat",
        "total 930.00 without vat",
        "total 930.00 zero vat",
        "total 930.00 excluding vat",
        "total 930.00 inc vat 0%",
    ]:
        assert parse_reply(text) == Corrections(
            selector=None, edits=[ReconstructedTotalEdit(value=Decimal("930.00"), vat_rate=None)]
        ), text


def test_reconstructed_total_carries_the_vat_inside_it():
    inclusive = ReconstructedTotalEdit(value=Decimal("710.25"), vat_rate=Decimal("0.05"))
    assert inclusive.tax == Decimal("33.82")  # 710.25 - 710.25/1.05, to the fil
    assert ReconstructedTotalEdit(value=Decimal("710.25"), vat_rate=None).tax == Decimal("0.00")


def test_parse_inc_vat_without_a_rate_asks_rather_than_guessing():
    assert parse_reply("total 930 inc vat") == Corrections(
        selector=None, edits=[MissingVatRateEdit(total=Decimal("930"))]
    )


def test_a_printed_total_stays_an_ordinary_totals_edit():
    # Read off the page: a correction, not a reconstruction (C8 tells them
    # apart, and only this one is checkable against the photo).
    assert parse_reply("total 976.50") == Corrections(
        selector=None, edits=[TotalsEdit(field="total", value=Decimal("976.50"))]
    )


def test_parse_currency_accepts_codes_and_printed_words():
    for text, expected in [
        ("currency AED", "AED"),
        ("currency usd", "USD"),
        ("currency dirhams", "AED"),
        ("Currency Dhs.", "AED"),
    ]:
        assert parse_reply(text) == Corrections(
            selector=None, edits=[CurrencyEdit(value=expected)]
        ), text


def test_parse_currency_refuses_anything_that_is_not_a_code():
    # An invented currency is worse than a clarify.
    for text in ["currency dollars", "currency 5", "currency united states dollar"]:
        assert parse_reply(text) is None, text


def test_reconstruction_marks_both_total_and_tax_and_only_those():
    edits = [
        LineFieldEdit(line_index=0, field="qty", value=Decimal("12")),
        ReconstructedTotalEdit(value=Decimal("710.25"), vat_rate=Decimal("0.05")),
    ]
    assert edited_field_keys(edits) == ["lines.0.qty", "total", "tax"]
    assert reconstructed_field_keys(edits) == ["total", "tax"]
    # A total read off the page is nobody's reconstruction.
    assert reconstructed_field_keys([TotalsEdit(field="total", value=Decimal("976.50"))]) == []


def test_apply_reconstructed_total_and_currency():
    invoice = ExtractedInvoice(
        supplier_name="Artisan Bakehouse LLC",
        currency="USD",
        lines=[
            ExtractedLine(
                raw_name="Sourdough Loaf",
                qty=Decimal("10"),
                unit_price=Decimal("14.00"),
                line_total=Decimal("140.00"),
            )
        ],
    )
    applied = apply_edits(
        invoice,
        [
            ReconstructedTotalEdit(value=Decimal("140.00"), vat_rate=Decimal("0.05")),
            CurrencyEdit(value="AED"),
        ],
    )
    assert applied.total == Decimal("140.00")
    assert applied.tax == Decimal("6.67")
    assert applied.currency == "AED"
    assert invoice.total is None and invoice.currency == "USD"  # input untouched


# --- e2e: WP-26, a totals block that was never in the frame ------------------


def totals_less_invoice() -> ExtractedInvoice:
    """The 2026-08-25 live shape: every line reads green, and the totals block
    is off the page (Artisan Bakehouse ABL-INV-260709-0517)."""
    return good_invoice().model_copy(update={"subtotal": None, "tax": None, "total": None})


@requires_db
async def test_wp26_a_totals_less_invoice_is_reconstructed_by_asking(api, db):
    app, client, *_ = api
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(totals_less_invoice())))

    # The reply shows the line sum and asks the two facts - and does not offer
    # the "or OK to confirm the rest" that recorded a null total live.
    reply = (await outbound_bodies(db))[-1]
    assert reply.splitlines() == [
        "Read it: Gulf Foods Trading LLC, 2 lines, total unreadable, dated 20 Aug 2026.",
        "I couldn't read the invoice total. The lines come to AED 710.25. Is that the whole "
        "invoice, VAT included? (reply like: total 710.25 inc vat 5%, or total 710.25 no vat, "
        "or the printed total: total 976.50)",
        "Send me the total and I'll finish this one off.",
    ]

    # A bare OK does not confirm: the same question again, never silence and
    # never the generic clarify.
    await post_webhook(client, wa_text_payload("OK", message_id="wamid.ok1"))
    await drain_jobs(db, app, None)
    invoice = await db.pool.fetchrow("select * from invoices")
    assert invoice["status"] == "awaiting_confirm"
    assert invoice["total"] is None
    assert invoice["confirmed_at"] is None
    assert (await outbound_bodies(db))[-1] == compose_total_needed_reply(Decimal("710.25"), "AED")
    assert (await db.pool.fetchval("select count(*) from supplier_item_prices")) == 0

    # "inc vat" with no rate asks for the rate rather than picking one.
    await post_webhook(client, wa_text_payload("total 710.25 inc vat", message_id="wamid.rate"))
    await drain_jobs(db, app, None)
    assert (await outbound_bodies(db))[-1] == compose_vat_rate_reply(Decimal("710.25"))
    assert (await db.pool.fetchval("select total from invoices")) is None

    # The answer lands: the total is stored, the VAT with it, and C4 resolves
    # the treatment it could not derive without a total.
    await post_webhook(client, wa_text_payload("total 710.25 inc vat 5%", message_id="wamid.rec"))
    await drain_jobs(db, app, None)
    invoice = await db.pool.fetchrow("select * from invoices")
    assert invoice["total"] == Decimal("710.25")
    assert invoice["tax"] == Decimal("33.82")
    assert invoice["tax_treatment"] == "inclusive"
    assert invoice["vat_rate"] == Decimal("0.0500")
    assert invoice["confidence"]["document"]["status"] == "green"

    # C8: reconstructed, not extracted - the whole point. Every field the
    # sender did not touch keeps the origin it had.
    provenance = invoice["provenance"]
    assert provenance["total"]["origin"] == "reconstructed"
    assert provenance["tax"]["origin"] == "reconstructed"
    assert provenance["total"]["actor"] == f"whatsapp:{DEMO_PHONE}"
    assert provenance["lines.0.qty"]["origin"] == "extracted"
    assert provenance["invoice_no"]["origin"] == "extracted"

    # The reply is now the ordinary all-green one, and OK confirms.
    assert (await outbound_bodies(db))[-1].splitlines() == [
        "Read it: Gulf Foods Trading LLC, 2 lines, total AED 710.25, dated 20 Aug 2026.",
        "Reply OK to confirm.",
    ]
    await post_webhook(client, wa_text_payload("ok", message_id="wamid.ok2"))
    await drain_jobs(db, app, None)
    invoice = await db.pool.fetchrow("select * from invoices")
    assert invoice["status"] == "confirmed"
    assert (await outbound_bodies(db))[-1] == (
        "Confirmed - Gulf Foods Trading LLC, AED 710.25 recorded. I'll watch these prices for you."
    )
    # C4 net-canonical: the reconstruction said the prices carry VAT, so price
    # memory records them ex-VAT - the treatment travelled with the correction.
    prices = await db.pool.fetch("select price from supplier_item_prices order by price")
    assert [row["price"] for row in prices] == [Decimal("17.857"), Decimal("51.905")]


@requires_db
async def test_wp26_no_vat_reconstruction_reconciles_and_records_as_printed(api, db):
    app, client, *_ = api
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(totals_less_invoice())))

    await post_webhook(client, wa_text_payload("total 710.25 no vat", message_id="wamid.rec"))
    await drain_jobs(db, app, None)
    invoice = await db.pool.fetchrow("select * from invoices")
    assert invoice["total"] == Decimal("710.25")
    assert invoice["tax"] == Decimal("0.00")
    assert invoice["tax_treatment"] == "exclusive"
    assert invoice["provenance"]["total"]["origin"] == "reconstructed"

    await post_webhook(client, wa_text_payload("ok", message_id="wamid.ok"))
    await drain_jobs(db, app, None)
    prices = await db.pool.fetch("select price from supplier_item_prices order by price")
    assert [row["price"] for row in prices] == [Decimal("18.750"), Decimal("54.500")]


@requires_db
async def test_wp26_a_total_read_off_the_page_is_a_correction_not_a_reconstruction(api, db):
    app, client, *_ = api
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(totals_less_invoice())))

    # The sender can read the printed total after all: ordinary chat grammar.
    await post_webhook(client, wa_text_payload("total 745.76", message_id="wamid.fix"))
    await drain_jobs(db, app, None)
    invoice = await db.pool.fetchrow("select * from invoices")
    assert invoice["total"] == Decimal("745.76")
    assert invoice["provenance"]["total"]["origin"] == "corrected_chat"
    # 710.25 + no tax != 745.76, so the totals question comes back rather than
    # anything being quietly reconciled - the tax is off the page too.
    assert "The totals don't add up" in (await outbound_bodies(db))[-1]

    await post_webhook(client, wa_text_payload("tax 35.51", message_id="wamid.tax"))
    await drain_jobs(db, app, None)
    invoice = await db.pool.fetchrow("select * from invoices")
    assert invoice["confidence"]["document"]["status"] == "green"
    assert invoice["provenance"]["tax"]["origin"] == "corrected_chat"


# --- e2e: WP-28, an invoice billed in someone else's money ------------------


def usd_invoice() -> ExtractedInvoice:
    """The 2026-08-28 live shape: Levant Specialty Foods FZCO, billed in USD
    to an AED tenant."""
    return good_invoice().model_copy(update={"currency": "USD"})


@requires_db
async def test_wp28_a_usd_invoice_is_asked_about_and_kept_out_of_price_memory(api, db):
    app, client, *_ = api
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(usd_invoice())))

    assert (await outbound_bodies(db))[-1].splitlines() == [
        "Read it: Gulf Foods Trading LLC, 2 lines, total USD 745.76, dated 20 Aug 2026.",
        "This invoice is in USD, not your usual AED - is that right? I'll record it as printed "
        "and keep it out of your price history. (if it's a misread, reply: currency AED)",
        "Reply with fixes (like: line 4 qty 16) or OK to confirm the rest.",
    ]

    # Confirming is allowed - the invoice itself is real and stores as printed.
    await post_webhook(client, wa_text_payload("OK", message_id="wamid.ok1"))
    await drain_jobs(db, app, None)
    invoice = await db.pool.fetchrow("select * from invoices")
    assert invoice["status"] == "confirmed"
    assert invoice["currency"] == "USD"
    assert invoice["total"] == Decimal("745.76")

    # But the baseline never mixes currency bases: no items, no observations.
    assert (await db.pool.fetchval("select count(*) from supplier_items")) == 0
    assert (await db.pool.fetchval("select count(*) from supplier_item_prices")) == 0
    # The supplier itself is identity, not price, and is still recorded.
    assert (await db.pool.fetchval("select name from suppliers")) == "Gulf Foods Trading LLC"
    # And the ack says so, rather than promising to watch prices it dropped.
    assert (await outbound_bodies(db))[-1] == (
        "Confirmed - Gulf Foods Trading LLC, USD 745.76 recorded. It's in USD, not AED, "
        "so I've kept it out of your price history."
    )


@requires_db
async def test_wp28_an_aed_invoice_replies_exactly_as_before(api, db):
    # The regression guard for every ordinary invoice: byte-identical.
    app, client, *_ = api
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(good_invoice())))
    assert (await outbound_bodies(db))[-1] == (
        "Read it: Gulf Foods Trading LLC, 2 lines, total AED 745.76, dated 20 Aug 2026.\n"
        "Reply OK to confirm."
    )
    await post_webhook(client, wa_text_payload("OK", message_id="wamid.ok1"))
    await drain_jobs(db, app, None)
    assert (await outbound_bodies(db))[-1] == ACK_GULF


@requires_db
async def test_wp28_a_misread_currency_is_corrected_from_chat_and_prices_flow_again(api, db):
    app, client, *_ = api
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(usd_invoice())))

    await post_webhook(client, wa_text_payload("currency AED", message_id="wamid.cur"))
    await drain_jobs(db, app, None)
    invoice = await db.pool.fetchrow("select * from invoices")
    assert invoice["currency"] == "AED"
    assert invoice["provenance"]["currency"]["origin"] == "corrected_chat"
    reply = (await outbound_bodies(db))[-1]
    assert "not your usual AED" not in reply
    assert reply.endswith("Reply OK to confirm.")

    await post_webhook(client, wa_text_payload("OK", message_id="wamid.ok1"))
    await drain_jobs(db, app, None)
    assert (await outbound_bodies(db))[-1] == ACK_GULF
    prices = await db.pool.fetch("select price from supplier_item_prices order by price")
    assert [row["price"] for row in prices] == [Decimal("18.750"), Decimal("54.500")]


@requires_db
async def test_wp28_a_foreign_invoice_raises_no_price_alerts(api, db):
    # The demo's money moment must never subtract two different currencies.
    app, client, *_ = api
    await seed_supplier_with_items(
        db, [{"canonical_name": "MILK PWDR 2.5KG NIDO", "last_price": Decimal("40.00")}]
    )
    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(usd_invoice())))
    reply = (await outbound_bodies(db))[-1]
    assert "since your last purchase" not in reply
    assert "not your usual AED" in reply

    # The same invoice in the tenant's own money does alert.
    await post_webhook(client, wa_image_payload(message_id="wamid.in2"))
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(good_invoice())))
    assert (
        "up AED 14.50 (40.00 to 54.50) since your last purchase." in (await outbound_bodies(db))[-1]
    )


def test_a_pack_size_correction_applies_and_can_clear():
    # The seam derives a pack from the item name when the page prints no pack
    # column. If that derivation is wrong, this is the only way to fix it -
    # no arithmetic will ever catch it (C4 anchors on the line sum).
    invoice = ExtractedInvoice(
        lines=[ExtractedLine(raw_name="RICE BASM 5KG", pack_size="5KG")],
        total=Decimal("67.20"),
    )
    corrected = apply_edits(invoice, [LinePackSizeEdit(line_index=0, pack_size="10kg")])
    assert corrected.lines[0].pack_size == "10kg"
    cleared = apply_edits(invoice, [LinePackSizeEdit(line_index=0, pack_size=None)])
    assert cleared.lines[0].pack_size is None
    # The input is never mutated.
    assert invoice.lines[0].pack_size == "5KG"


def test_a_pack_size_correction_is_attributed_to_the_line_it_changed():
    # C8: the correction names the field it moved, so provenance re-stamps
    # pack_size alone rather than the whole line.
    keys = edited_field_keys([LinePackSizeEdit(line_index=2, pack_size="2kg")])
    assert keys == ["lines.2.pack_size"]
