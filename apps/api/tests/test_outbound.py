"""M10 WP-102: what leaves the building, and what Meta says happened to it.

Two halves of the same fact. The send is a *template*, which is the only kind
of message Meta accepts outside the 24-hour service window - and a brief at
07:00 to a phone that wrote nothing yesterday is always outside it. The record
is the outbound `wa_messages` row plus Meta's receipts stamped onto it, so
"the owner says nothing arrived" is answered by reading one row instead of by
guessing (C15.4, decomposition §3.1).

The Graph API is mocked at the transport layer as everywhere else: the tests
assert on the JSON Meta was actually handed, never on how the client built it.
"""

import datetime
import uuid

import httpx
import pytest

from faida_api.wa import WhatsAppClient

from .conftest import DEMO_PHONE, DEMO_TENANT_ID, FakeMeta, requires_db
from .test_flow import api as flow_api
from .test_flow import post_webhook
from .test_webhook_pure import UNDELIVERABLE, wa_status_payload

#: The webhook app the flow tests build (webhook router, the test DB, Meta and
#: storage mocked); rebinding it under the local name registers it here.
api = flow_api

TEMPLATE = "faida_daily_brief"
LANGUAGE = "en"
RECIPIENT_ID = "11111111-1111-4111-8111-111111111111"
BRIEF_DATE = "2026-09-01"
CARD_PATH = f"{DEMO_TENANT_ID}/briefs/{BRIEF_DATE}/{RECIPIENT_ID}.png"

#: The decomposition's own sample values (§3.1), which are the five the
#: template was submitted with.
PARAMETERS = [
    "Sales loaded to Mon 31 Aug, yesterday.",
    "AED 9,493 on Mon 31 Aug",
    "AED 67,471 (25-31 Aug loaded)",
    "AED 18,342 at the latest prices",
    "32.6% of the AED 56,294 costed (84% of sales)",
]


@pytest.fixture
async def wa(settings):
    """A real client over a fake Meta. No database: the wire shape is a pure
    fact about the client."""
    fake = FakeMeta()
    client = WhatsAppClient(settings, transport=fake.transport())
    yield client, fake
    await client.close()


async def _record(db, message_id: str, **overrides) -> None:
    fields = {
        "template": TEMPLATE,
        "language": LANGUAGE,
        "parameters": PARAMETERS,
        "tenant_id": DEMO_TENANT_ID,
        "recipient_id": RECIPIENT_ID,
        "brief_date": BRIEF_DATE,
        "rehearsal": False,
        "card_path": CARD_PATH,
    }
    fields.update(overrides)
    await db.record_outbound_template(message_id, DEMO_PHONE, **fields)


async def _row(db, message_id: str):
    return await db.pool.fetchrow("select * from wa_messages where message_id = $1", message_id)


# --- the send ---------------------------------------------------------------


async def test_a_template_send_is_the_documented_json(wa):
    """The body component carries one text parameter per value, in order:
    that order is the template's `{{1}}`..`{{5}}`, and Meta answers 132000
    when it is not."""
    client, fake = wa
    message_id = await client.send_template(DEMO_PHONE, TEMPLATE, LANGUAGE, PARAMETERS)

    assert message_id == "wamid.out1"
    assert fake.sent == [
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": DEMO_PHONE,
            "type": "template",
            "template": {
                "name": TEMPLATE,
                "language": {"code": LANGUAGE},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": value} for value in PARAMETERS],
                    }
                ],
            },
        }
    ]


async def test_the_picture_header_comes_before_the_body(wa):
    """Meta reads `components` in order, so the header the card is uploaded
    for has to be first (P15)."""
    client, fake = wa
    await client.send_template(
        DEMO_PHONE, TEMPLATE, LANGUAGE, PARAMETERS, header_image_id="media-up1"
    )

    components = fake.sent[0]["template"]["components"]
    assert components[0] == {
        "type": "header",
        "parameters": [{"type": "image", "image": {"id": "media-up1"}}],
    }
    assert components[1]["type"] == "body"
    assert len(components) == 2


async def test_meta_down_raises_and_sends_nothing(wa):
    """A 500 is the retryable morning: the caller decides, exactly as it does
    for a free-text send."""
    client, fake = wa
    fake.fail_sends = True

    with pytest.raises(httpx.HTTPStatusError) as refused:
        await client.send_template(DEMO_PHONE, TEMPLATE, LANGUAGE, PARAMETERS)

    assert "500" in str(refused.value)
    assert fake.sent == []


@pytest.mark.parametrize("code", [132001, 132000])
async def test_a_numbered_refusal_names_its_number(wa, code):
    """The two refusals that are not outages - the template is not approved
    (132001), or it was edited to a different variable count (132000) - put
    Meta's own code in the exception, because the status alone would send
    the founder to the wrong place."""
    client, fake = wa
    fake.template_error = code

    with pytest.raises(httpx.HTTPStatusError) as refused:
        await client.send_template(DEMO_PHONE, TEMPLATE, LANGUAGE, PARAMETERS)

    said = str(refused.value)
    assert str(code) in said
    assert fake.ERRORS[code][0] in said
    assert fake.ERRORS[code][1] in said
    assert fake.sent == []


async def test_an_upload_hands_meta_the_file_and_returns_its_id(wa):
    """The card is drawn fresh each morning, so there is nothing to link to:
    the bytes go up multipart and come back as an id the header can name."""
    client, fake = wa
    media_id = await client.upload_media(b"\x89PNG\r\n\x1a\nfake", "image/png")

    assert media_id == "media-up1"
    assert fake.uploads == [
        {
            "messaging_product": "whatsapp",
            "type": "image/png",
            "file": b"\x89PNG\r\n\x1a\nfake",
            "filename": "upload.png",
        }
    ]


async def test_a_refused_upload_raises_before_anything_is_sent(wa):
    client, fake = wa
    fake.fail_uploads = True

    with pytest.raises(httpx.HTTPStatusError) as refused:
        await client.upload_media(b"bytes", "image/png")

    assert "Media upload error" in str(refused.value)
    assert fake.uploads == [] and fake.sent == []


# --- the record -------------------------------------------------------------


@requires_db
async def test_the_record_says_what_was_sent_and_which_morning_it_was(db):
    await _record(db, "wamid.brief1")

    row = await _row(db, "wamid.brief1")
    assert row["direction"] == "out"
    assert row["msg_type"] == "template"
    assert row["status"] == "sent"
    assert row["to_phone"] == DEMO_PHONE
    assert row["payload"] == {
        "template": TEMPLATE,
        "language": LANGUAGE,
        "parameters": PARAMETERS,
        "card_path": CARD_PATH,
        "tenant_id": DEMO_TENANT_ID,
        "recipient_id": RECIPIENT_ID,
        "brief_date": BRIEF_DATE,
        "rehearsal": False,
        "error": None,
    }


@requires_db
async def test_a_rehearsal_and_a_card_less_send_are_on_the_record_too(db):
    """The founder's `--send --to` proof at some other hour is marked, so it
    is never read as that morning's brief."""
    await _record(db, "wamid.rehearse", rehearsal=True, card_path=None)

    payload = (await _row(db, "wamid.rehearse"))["payload"]
    assert payload["rehearsal"] is True
    assert payload["card_path"] is None


@requires_db
async def test_an_id_and_a_date_are_written_as_text(db):
    """The recipient's id comes out of Postgres as a `uuid.UUID` and the
    morning as a `datetime.date`; neither survives the jsonb encoder on its
    own, and this write happens after Meta has taken the message - so it
    coerces rather than raising into C15.3's one expensive failure."""
    await db.record_outbound_template(
        "wamid.typed",
        DEMO_PHONE,
        template=TEMPLATE,
        language=LANGUAGE,
        parameters=PARAMETERS,
        tenant_id=uuid.UUID(DEMO_TENANT_ID),
        recipient_id=uuid.UUID(RECIPIENT_ID),
        brief_date=datetime.date(2026, 9, 1),
        rehearsal=False,
    )

    payload = (await _row(db, "wamid.typed"))["payload"]
    assert payload["tenant_id"] == DEMO_TENANT_ID
    assert payload["recipient_id"] == RECIPIENT_ID
    assert payload["brief_date"] == BRIEF_DATE


@requires_db
async def test_a_receipt_moves_the_row_forward_and_never_back(db):
    await _record(db, "wamid.brief1")

    assert await db.stamp_outbound_status("wamid.brief1", "delivered") is True
    assert await db.stamp_outbound_status("wamid.brief1", "read") is True
    assert (await _row(db, "wamid.brief1"))["status"] == "read"

    # Meta re-delivers receipts, and late: neither a repeat nor an earlier
    # one may walk the row backwards.
    assert await db.stamp_outbound_status("wamid.brief1", "delivered") is False
    assert await db.stamp_outbound_status("wamid.brief1", "read") is False
    assert await db.stamp_outbound_status("wamid.brief1", "sent") is False
    assert (await _row(db, "wamid.brief1"))["status"] == "read"


@requires_db
async def test_failed_is_terminal_and_keeps_metas_reason(db):
    await _record(db, "wamid.brief1")
    assert await db.stamp_outbound_status("wamid.brief1", "delivered") is True

    assert await db.stamp_outbound_status("wamid.brief1", "failed", UNDELIVERABLE) is True
    row = await _row(db, "wamid.brief1")
    assert row["status"] == "failed"
    assert row["payload"]["error"] == UNDELIVERABLE
    # The rest of the record is untouched: what was sent is still on the row.
    assert row["payload"]["parameters"] == PARAMETERS

    assert await db.stamp_outbound_status("wamid.brief1", "read") is False
    assert await db.stamp_outbound_status("wamid.brief1", "delivered") is False
    assert (await _row(db, "wamid.brief1"))["status"] == "failed"


@requires_db
async def test_a_status_this_order_does_not_know_is_ignored(db):
    await _record(db, "wamid.brief1")
    assert await db.stamp_outbound_status("wamid.brief1", "warehoused") is False
    assert (await _row(db, "wamid.brief1"))["status"] == "sent"


@requires_db
async def test_a_receipt_that_beats_the_record_loses_nothing(db):
    """Meta's receipt can reach the webhook before we have finished writing
    what we sent. The receipt leaves a stub; the record completes it, keeping
    the further-along status and the error the receipt carried."""
    assert (
        await db.stamp_outbound_status("wamid.race", "failed", UNDELIVERABLE, to_phone=DEMO_PHONE)
        is True
    )
    stub = await _row(db, "wamid.race")
    assert stub["direction"] == "out"
    assert stub["msg_type"] == "unknown"
    assert stub["status"] == "failed"
    assert stub["to_phone"] == DEMO_PHONE
    assert stub["payload"] == {"stub": True, "error": UNDELIVERABLE}

    await _record(db, "wamid.race")

    row = await _row(db, "wamid.race")
    assert row["msg_type"] == "template"
    assert row["status"] == "failed"  # the receipt is further along than our own 'sent'
    assert row["payload"]["parameters"] == PARAMETERS
    assert row["payload"]["brief_date"] == BRIEF_DATE
    assert row["payload"]["error"] == UNDELIVERABLE
    assert "stub" not in row["payload"]


@requires_db
async def test_a_plain_receipt_that_beats_the_record_leaves_a_clean_row(db):
    """The ordinary race - a `delivered` a few hundred milliseconds early -
    ends with exactly the record's own shape, no error and no stub flag."""
    assert await db.stamp_outbound_status("wamid.race2", "delivered", to_phone=DEMO_PHONE) is True
    await _record(db, "wamid.race2")

    row = await _row(db, "wamid.race2")
    assert row["status"] == "delivered"
    assert row["payload"]["error"] is None
    assert "stub" not in row["payload"]
    assert row["to_phone"] == DEMO_PHONE


# --- the webhook ------------------------------------------------------------


@requires_db
async def test_the_webhook_stamps_a_receipt_and_enqueues_nothing(api, db):
    app, client, *_ = api
    await _record(db, "wamid.brief1")

    response = await post_webhook(client, wa_status_payload("wamid.brief1", "delivered"))
    assert response.status_code == 200
    assert (await _row(db, "wamid.brief1"))["status"] == "delivered"

    response = await post_webhook(
        client, wa_status_payload("wamid.brief1", "failed", errors=[UNDELIVERABLE])
    )
    assert response.status_code == 200
    row = await _row(db, "wamid.brief1")
    assert row["status"] == "failed"
    assert row["payload"]["error"] == UNDELIVERABLE

    # A receipt is not a message: nothing to do, so nothing queued.
    assert await db.pool.fetchval("select count(*) from jobs") == 0


@requires_db
async def test_the_webhook_stubs_a_receipt_for_a_message_it_has_not_recorded(api, db):
    app, client, *_ = api

    response = await post_webhook(
        client, wa_status_payload("wamid.unknown", "read", recipient="971500009999")
    )
    assert response.status_code == 200

    row = await _row(db, "wamid.unknown")
    assert row["direction"] == "out"
    assert row["msg_type"] == "unknown"
    assert row["status"] == "read"
    assert row["to_phone"] == "971500009999"
    assert await db.pool.fetchval("select count(*) from jobs") == 0
