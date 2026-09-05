"""C8 provenance + the audit spine (plan.md §7.2 C8/C9, §8 M5).

Pure tests for the field-path bookkeeping, then the paths a user actually
takes: a photo arrives and every field is marked read-off-the-image; a repair
round re-stamps only the cells that moved; a correction over WhatsApp restamps
only the fields it edited and leaves the rest alone; the same correction
through the review screen records the other door and the same actor discipline;
manual entry marks the whole document as typed; and every confirmation lands
one audit row naming who said OK - exactly one, even when the job retries.
"""

import datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI

from faida_api.api import router as api_router
from faida_api.confirm import chat_actor, edited_field_keys
from faida_api.confirm import parse_reply as _parse
from faida_api.extraction.schema import ExtractedInvoice, ExtractedLine, RepairResult
from faida_api.provenance import (
    ASSERTED_ORIGINS,
    HEADER_FIELDS,
    LINE_FIELDS,
    READ_ORIGINS,
    Origin,
    asserted_fields,
    changed_fields,
    field_keys,
    initial,
    line_key,
    mark,
)
from faida_api.storage import Storage
from faida_api.wa import WhatsAppClient
from faida_api.webhook import router as webhook_router

from .conftest import (
    AUTH,
    DEMO_PHONE,
    DEMO_TENANT_ID,
    TEST_ACTOR,
    FakeExtraction,
    FakeMeta,
    FakeStorage,
    requires_db,
    wa_image_payload,
    wa_text_payload,
    wire_auth,
)
from .test_api import client_for, extracted_invoice
from .test_extraction_flow import drain_jobs, good_invoice, invoice_result, post_webhook

AT = datetime.datetime(2026, 8, 28, 9, 0, tzinfo=datetime.UTC)


@pytest.fixture
def api(settings, db):
    """Webhook + API on the test DB with Meta and storage mocked at the
    transport - the same shape as the other flow modules' fixtures, so both
    doors into a correction can be exercised in one test module."""
    app = FastAPI()
    app.include_router(webhook_router)
    app.include_router(api_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    app.state.wa = WhatsAppClient(settings, transport=FakeMeta().transport())
    app.state.storage = Storage(settings, transport=FakeStorage().transport())
    return app, client_for(app)


def _invoice(**overrides) -> ExtractedInvoice:
    base = ExtractedInvoice(
        supplier_name="Gulf Foods Trading LLC",
        invoice_no="INV-1041",
        invoice_date=datetime.date(2026, 8, 20),
        currency="AED",
        payment_kind="credit",
        lines=[
            ExtractedLine(
                raw_name="MILK PWDR 2.5KG NIDO",
                qty=Decimal("12"),
                unit="sack",
                pack_size="2.5kg",
                unit_price=Decimal("54.50"),
                line_total=Decimal("654.00"),
            ),
            ExtractedLine(
                raw_name="KARAK TEA DUST",
                qty=Decimal("3"),
                unit=None,
                unit_price=Decimal("18.75"),
                line_total=Decimal("56.25"),
            ),
        ],
        subtotal=Decimal("710.25"),
        tax=Decimal("35.51"),
        total=Decimal("745.76"),
    )
    return base.model_copy(update=overrides)


# --- pure: field paths ------------------------------------------------------


def test_every_field_gets_a_key_whether_or_not_it_holds_a_value():
    """A null total must have a key from the start: WP-26 supplies it later as
    `reconstructed`, and a key that only appears once a value does would leave
    the reconstruction indistinguishable from a read."""
    invoice = _invoice(total=None, invoice_date=None)
    keys = field_keys(invoice)

    assert set(HEADER_FIELDS) <= set(keys)
    assert "total" in keys and "invoice_date" in keys
    assert len(keys) == len(HEADER_FIELDS) + 2 * len(LINE_FIELDS)


def test_initial_stamps_every_field_with_one_origin():
    provenance = initial(_invoice(), origin=Origin.EXTRACTED, actor="model:fake", at=AT)

    assert set(provenance) == set(field_keys(_invoice()))
    assert provenance["total"] == {
        "origin": "extracted",
        "actor": "model:fake",
        "at": AT.isoformat(),
    }
    assert provenance[line_key(1, "unit_price")]["origin"] == "extracted"


def test_mark_restamps_only_the_named_fields_and_does_not_mutate():
    before = initial(_invoice(), origin=Origin.EXTRACTED, actor="model:fake", at=AT)

    after = mark(
        before,
        ["total", line_key(0, "qty")],
        origin=Origin.CORRECTED_CHAT,
        actor="whatsapp:+971500000000",
        at=AT,
    )

    assert after["total"]["origin"] == "corrected_chat"
    assert after[line_key(0, "qty")]["actor"] == "whatsapp:+971500000000"
    # Untouched fields keep what they had, and the input is unchanged.
    assert after["subtotal"]["origin"] == "extracted"
    assert after[line_key(1, "qty")]["origin"] == "extracted"
    assert before["total"]["origin"] == "extracted"


def test_the_two_origin_sets_partition_the_vocabulary():
    """C9 leans on this split, so an origin added later cannot fall through
    both sets and quietly count as checkable against a photo."""
    assert READ_ORIGINS | ASSERTED_ORIGINS == set(Origin)
    assert not READ_ORIGINS & ASSERTED_ORIGINS


# --- pure: attributing the repair round -------------------------------------


def test_changed_fields_names_only_what_the_repair_actually_moved():
    """A scoped re-read is asked for qty, unit_price and line_total together
    and routinely hands two of them back unchanged. Only the cell that moved
    was re-read to any effect."""
    before = _invoice()
    after = before.model_copy(
        update={
            "lines": [
                before.lines[0].model_copy(update={"qty": Decimal("12.5")}),
                before.lines[1],
            ]
        }
    )

    assert changed_fields(before, after) == [line_key(0, "qty")]


def test_changed_fields_sees_header_money_and_an_unchanged_document():
    before = _invoice()
    assert changed_fields(before, before) == []

    after = before.model_copy(update={"total": Decimal("745.00"), "tax": Decimal("35.00")})
    assert changed_fields(before, after) == ["tax", "total"]


def test_a_line_the_merge_added_counts_as_changed_throughout():
    before = _invoice()
    after = before.model_copy(update={"lines": [*before.lines, before.lines[0]]})

    assert changed_fields(before, after) == [line_key(2, field) for field in LINE_FIELDS]


# --- pure: the chat grammar's edits map onto field paths --------------------


def test_edited_field_keys_covers_every_edit_shape():
    parsed = _parse("line 1 qty 16, line 2 price 19.00, line 1 name RICE, total 800")

    # The grammar is 1-based in chat, 0-based internally - the keys follow the
    # stored indices, not what the sender typed.
    assert edited_field_keys(parsed.edits) == [
        line_key(0, "qty"),
        line_key(1, "unit_price"),
        line_key(0, "raw_name"),
        "total",
    ]


def test_edited_field_keys_dedupes_repeated_edits_of_one_field():
    parsed = _parse("line 1 qty 16, line 1 qty 18")
    assert edited_field_keys(parsed.edits) == [line_key(0, "qty")]


# --- pure: what C9 will read ------------------------------------------------


def test_asserted_fields_separates_what_a_person_said_from_what_was_read():
    provenance = initial(_invoice(), origin=Origin.EXTRACTED, actor="model:fake", at=AT)
    provenance = mark(provenance, ["total"], origin=Origin.RECONSTRUCTED, actor="c", at=AT)
    provenance = mark(
        provenance, [line_key(0, "qty")], origin=Origin.CORRECTED_SCREEN, actor="console", at=AT
    )
    provenance = mark(
        provenance, [line_key(1, "qty")], origin=Origin.REPAIRED, actor="model:fake", at=AT
    )

    # The repaired field is still something a camera saw; the other two are not.
    assert asserted_fields(provenance) == [line_key(0, "qty"), "total"]


# --- the paths a user takes -------------------------------------------------


@requires_db
async def test_a_forwarded_photo_marks_every_field_read_off_the_image(api, db):
    invoice = await extracted_invoice(api, db)

    provenance = invoice["provenance"]
    assert set(provenance) == set(field_keys(good_invoice()))
    assert {record["origin"] for record in provenance.values()} == {"extracted"}
    # The actor is the model that read it, which is what makes a re-read of the
    # same document attributable to a different model version later.
    assert {record["actor"] for record in provenance.values()} == {"model:fake-model"}


@requires_db
async def test_a_repair_round_restamps_only_the_cells_it_moved(api, db):
    """The repair pass is asked for three cells of the failing line and hands
    back a corrected qty. That cell is `repaired`; the rest of the invoice is
    untouched and stays `extracted`."""
    app, client, *_ = api
    misread = good_invoice()
    misread.lines[0].qty = Decimal("2")  # 2 x 54.50 != 654.00 -> a failed check
    patch = RepairResult(lines={0: misread.lines[0].model_copy(update={"qty": Decimal("12")})})

    await post_webhook(client, wa_image_payload())
    await drain_jobs(db, app, FakeExtraction(result=invoice_result(misread), repair_patch=patch))

    doc = await db.get_document_by_wa_message("wamid.in1")
    invoice = await db.get_invoice_by_document(str(doc["id"]), tenant_id=DEMO_TENANT_ID)
    provenance = invoice["provenance"]

    assert provenance[line_key(0, "qty")]["origin"] == "repaired"
    assert provenance[line_key(0, "unit_price")]["origin"] == "extracted"
    assert provenance[line_key(0, "line_total")]["origin"] == "extracted"
    assert provenance["total"]["origin"] == "extracted"


@requires_db
async def test_a_chat_correction_restamps_only_the_field_it_fixed(api, db):
    app, client, *_ = api
    misread = good_invoice()
    misread.lines[0].qty = Decimal("2")
    await extracted_invoice(api, db, misread)

    await post_webhook(client, wa_text_payload("line 1 qty 12", message_id="wamid.fix1"))
    await drain_jobs(db, app, None)

    doc = await db.get_document_by_wa_message("wamid.in1")
    invoice = await db.get_invoice_by_document(str(doc["id"]), tenant_id=DEMO_TENANT_ID)
    provenance = invoice["provenance"]

    assert provenance[line_key(0, "qty")]["origin"] == "corrected_chat"
    assert provenance[line_key(0, "qty")]["actor"] == f"whatsapp:{DEMO_PHONE}"
    # Everything the sender did not touch keeps the model's reading.
    assert provenance[line_key(0, "unit_price")]["origin"] == "extracted"
    assert provenance[line_key(1, "qty")]["origin"] == "extracted"
    assert provenance["total"]["origin"] == "extracted"

    # And the correction is on the record, with the fields it touched.
    events = await db.audit_events_for_subject(
        "invoice", str(invoice["id"]), tenant_id=DEMO_TENANT_ID
    )
    assert [(event["action"], event["actor"]) for event in events] == [
        ("invoice.corrected", f"whatsapp:{DEMO_PHONE}")
    ]
    # The inbound message id rides along, so a job that retried after a failed
    # send shows as one message twice rather than two separate decisions.
    assert events[0]["detail"] == {"fields": [line_key(0, "qty")], "message_id": "wamid.fix1"}


@requires_db
async def test_the_screen_records_the_other_door(api, db):
    """Same function as chat (one door for everyone), so the only difference
    the record should show is which door and who."""
    _, client, *_ = api
    invoice = await extracted_invoice(api, db)

    resp = await client.patch(
        f"/api/invoices/{invoice['id']}/fields",
        headers=AUTH,
        json={"corrections": [{"field": "qty", "line_index": 0, "value": "11"}]},
    )
    assert resp.status_code == 200

    provenance = resp.json()["provenance"]  # C6 detail carries it for the screen
    assert provenance[line_key(0, "qty")]["origin"] == "corrected_screen"
    assert provenance[line_key(0, "qty")]["actor"] == TEST_ACTOR
    assert provenance["total"]["origin"] == "extracted"

    events = await db.audit_events_for_subject(
        "invoice", str(invoice["id"]), tenant_id=DEMO_TENANT_ID
    )
    assert [(event["action"], event["actor"]) for event in events] == [
        ("invoice.corrected", TEST_ACTOR)
    ]
    # No WhatsApp message behind a screen edit; the key is present and null.
    assert events[0]["detail"] == {"fields": [line_key(0, "qty")], "message_id": None}


@requires_db
async def test_confirming_from_chat_records_who_said_ok_exactly_once(api, db):
    """The retry guard matters here: a job re-running after a failed send
    re-sends the ack, and must not leave a second confirmation in the trail."""
    app, client, *_ = api
    invoice = await extracted_invoice(api, db)

    await post_webhook(client, wa_text_payload("OK", message_id="wamid.ok1"))
    await drain_jobs(db, app, None)
    # A duplicate OK from the same sender: acked again, never re-recorded.
    await post_webhook(client, wa_text_payload("OK", message_id="wamid.ok2"))
    await drain_jobs(db, app, None)

    events = await db.audit_events_for_subject(
        "invoice", str(invoice["id"]), tenant_id=DEMO_TENANT_ID
    )
    assert [(event["action"], event["actor"]) for event in events] == [
        ("invoice.confirmed", f"whatsapp:{DEMO_PHONE}")
    ]
    assert events[0]["detail"] == {"from_status": "awaiting_confirm"}
    assert events[0]["tenant_id"] is not None


@requires_db
async def test_approving_a_cash_hold_from_the_screen_is_recorded_with_its_reason(api, db):
    """The cash gate is the one approval PRD §21 calls non-negotiable, and from
    WP-74 the approve door is that gate - so it is the one confirmation that
    most needs a name and a reason against it, and the plain confirm refuses
    to record it at all."""
    _, client, *_ = api
    cash = good_invoice()
    cash.payment_kind = "cash"
    invoice = await extracted_invoice(api, db, cash)
    assert invoice["status"] == "needs_review"

    resp = await client.post(f"/api/invoices/{invoice['id']}/confirm", headers=AUTH)
    assert resp.status_code == 409
    resp = await client.post(
        f"/api/invoices/{invoice['id']}/approve",
        headers=AUTH,
        json={"reason": "Paid from the till, slip attached"},
    )
    assert resp.status_code == 200, resp.text

    events = await db.audit_events_for_subject(
        "invoice", str(invoice["id"]), tenant_id=DEMO_TENANT_ID
    )
    assert [(event["action"], event["actor"]) for event in events] == [
        ("invoice.cash_approved", TEST_ACTOR)
    ]
    assert events[0]["detail"]["from_status"] == "needs_review"
    assert events[0]["detail"]["reason"] == "Paid from the till, slip attached"
    assert events[0]["detail"]["total"] == "745.76"


@requires_db
async def test_manual_entry_marks_the_whole_document_as_typed(api, db):
    """WP-34's no-AI path: no camera saw any of this, and the record says so
    rather than leaving it looking like a read."""
    _, client, *_ = api

    resp = await client.post(
        "/api/invoices/manual",
        headers=AUTH,
        json={
            "supplier_name": "Deira Cold Store",
            "invoice_no": "T-0084417",
            "invoice_date": "2026-08-23",
            "total": "100.00",
            "lines": [
                {"raw_name": "LABAN 1L", "qty": "10", "unit_price": "10.00", "line_total": "100.00"}
            ],
        },
    )
    assert resp.status_code == 201

    detail = resp.json()
    assert {record["origin"] for record in detail["provenance"].values()} == {"manual"}
    assert {record["actor"] for record in detail["provenance"].values()} == {TEST_ACTOR}

    events = await db.audit_events_for_subject("invoice", detail["id"], tenant_id=DEMO_TENANT_ID)
    assert [(event["action"], event["actor"]) for event in events] == [
        ("invoice.created_by_hand", TEST_ACTOR)
    ]


@requires_db
async def test_chat_actor_names_the_phone_that_sent_the_message():
    assert chat_actor("971509772702") == "whatsapp:971509772702"
