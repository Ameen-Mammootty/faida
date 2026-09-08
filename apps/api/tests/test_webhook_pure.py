"""Pure tests: signature verification and payload parsing. No DB, no network."""

import hashlib
import hmac
import json

from faida_api.webhook import extract_messages, extract_statuses, verify_signature

from .conftest import wa_image_payload

SECRET = "s3cret"


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_accepted():
    body = b'{"a": 1}'
    assert verify_signature(body, sign(body), SECRET)


def test_bad_signature_rejected():
    body = b'{"a": 1}'
    assert not verify_signature(body, sign(body, "wrong"), SECRET)
    assert not verify_signature(body + b" ", sign(body), SECRET)
    assert not verify_signature(body, None, SECRET)
    assert not verify_signature(body, "md5=abc", SECRET)


def test_missing_app_secret_fails_closed():
    body = b'{"a": 1}'
    assert not verify_signature(body, sign(body, ""), "")


def test_extract_image_message():
    msgs = extract_messages(wa_image_payload())
    assert len(msgs) == 1
    assert msgs[0]["id"] == "wamid.in1"
    assert msgs[0]["from"] == "971500000000"
    assert msgs[0]["type"] == "image"
    assert msgs[0]["media_id"] == "media-1"


def wa_status_payload(
    message_id: str,
    status: str,
    recipient: str = "971500000000",
    errors: list[dict] | None = None,
) -> dict:
    """Meta's receipt for a message we sent, in the envelope it arrives in
    (M10 WP-102). The same POST as an inbound message, carrying `statuses`
    instead of `messages`."""
    entry: dict = {
        "id": message_id,
        "status": status,
        "timestamp": "1755850001",
        "recipient_id": recipient,
    }
    if errors is not None:
        entry["errors"] = errors
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-id",
                "changes": [
                    {
                        "field": "messages",
                        "value": {"messaging_product": "whatsapp", "statuses": [entry]},
                    }
                ],
            }
        ],
    }


#: Meta's own shape for an undeliverable number, which arrives only as a
#: receipt - there is no synchronous answer that carries it (WP-102).
UNDELIVERABLE = {
    "code": 131026,
    "title": "Message undeliverable",
    "message": "Message undeliverable",
    "error_data": {"details": "Message could not be delivered to the recipient"},
}


def test_status_updates_are_not_messages():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [{"id": "wamid.x", "status": "delivered"}],
                        }
                    }
                ]
            }
        ]
    }
    assert extract_messages(payload) == []


def test_extract_statuses_reads_the_receipts_messages_skips():
    """The other half of the same payload: a delivered and a read carry no
    error, a failed carries Meta's reason (WP-102, C15.4)."""
    delivered = extract_statuses(wa_status_payload("wamid.out1", "delivered"))
    assert delivered == [
        {
            "id": "wamid.out1",
            "status": "delivered",
            "recipient_id": "971500000000",
            "errors": None,
        }
    ]

    read = extract_statuses(wa_status_payload("wamid.out1", "read", recipient="971500000001"))
    assert read[0]["status"] == "read"
    assert read[0]["recipient_id"] == "971500000001"

    failed = extract_statuses(wa_status_payload("wamid.out2", "failed", errors=[UNDELIVERABLE]))
    assert failed[0]["status"] == "failed"
    assert failed[0]["errors"] == [UNDELIVERABLE]


def test_extract_statuses_on_an_inbound_payload_is_empty():
    """An inbound message is not a receipt, exactly as a receipt is not a
    message: the two readers never see each other's entries."""
    assert extract_statuses(wa_image_payload()) == []
    assert extract_messages(wa_status_payload("wamid.out1", "sent")) == []


def test_extract_handles_text_and_unknown_types():
    payload = json.loads(json.dumps(wa_image_payload()))
    msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    msg.update({"type": "text", "text": {"body": "OK"}})
    del msg["image"]
    msgs = extract_messages(payload)
    assert msgs[0]["type"] == "text"
    assert msgs[0]["media_id"] is None
