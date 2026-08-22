"""Pure tests: signature verification and payload parsing. No DB, no network."""

import hashlib
import hmac
import json

from faida_api.webhook import extract_messages, verify_signature

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


def test_extract_handles_text_and_unknown_types():
    payload = json.loads(json.dumps(wa_image_payload()))
    msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    msg.update({"type": "text", "text": {"body": "OK"}})
    del msg["image"]
    msgs = extract_messages(payload)
    assert msgs[0]["type"] == "text"
    assert msgs[0]["media_id"] is None
