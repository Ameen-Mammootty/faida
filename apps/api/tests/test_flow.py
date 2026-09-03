"""End-to-end M0 flow against a real Postgres (TEST_DATABASE_URL), with the
Graph API and Supabase Storage mocked at the transport layer:

webhook POST -> dedupe -> raw stored -> job queued -> worker -> media downloaded,
hashed, stored immutably -> document row -> canned reply sent and recorded.
"""

import hashlib
import hmac
import json

import httpx
import pytest

from faida_api.contracts import WA_STATUS_IGNORED_UNKNOWN_SENDER
from faida_api.replies import REPLY_MEDIA_RECEIVED, REPLY_TEXT_ONBOARDING, REPLY_UNKNOWN_SENDER
from faida_api.storage import Storage
from faida_api.wa import WhatsAppClient
from faida_api.webhook import router as webhook_router
from faida_api.worker import run_one_job

from .conftest import (
    DEMO_PHONE,
    TEST_APP_SECRET,
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


async def test_get_verification(api):
    app, client, *_ = api
    r = await client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "12345",
        },
    )
    assert r.status_code == 200 and r.text == "12345"
    r = await client.get(
        "/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "x"},
    )
    assert r.status_code == 403


async def test_unsigned_post_rejected(api):
    app, client, *_ = api
    r = await client.post("/webhook", content=b"{}")
    assert r.status_code == 403


async def test_image_message_full_flow(api, db):
    app, client, fake_meta, fake_storage = api

    r = await post_webhook(client, wa_image_payload())
    assert r.status_code == 200

    # Raw message stored, job queued.
    assert await db.get_inbound_message("wamid.in1") is not None
    assert await db.pool.fetchval("select count(*) from jobs where status='queued'") == 1

    # Worker processes the job.
    assert await run_one_job(db, app.state.wa, app.state.storage) is True

    doc = await db.get_document_by_wa_message("wamid.in1")
    assert doc is not None
    assert doc["source"] == "whatsapp"
    assert doc["status"] == "received"
    assert doc["sha256"] == hashlib.sha256(fake_meta.media_bytes).hexdigest()
    assert str(doc["branch_id"]) == "00000000-0000-0000-0000-000000000011"

    # Original stored immutably at tenant/{id}/documents/{id}/original.
    assert doc["storage_path"] in fake_storage.objects
    assert fake_storage.objects[doc["storage_path"]] == fake_meta.media_bytes

    # Canned reply sent to the sender and recorded outbound.
    assert fake_meta.sent[-1]["to"] == DEMO_PHONE
    assert fake_meta.sent[-1]["text"]["body"] == REPLY_MEDIA_RECEIVED
    out = await db.pool.fetchrow("select * from wa_messages where direction='out'")
    assert out is not None and out["to_phone"] == DEMO_PHONE

    assert await db.pool.fetchval("select count(*) from jobs where status='done'") == 1


async def test_duplicate_delivery_creates_one_document(api, db):
    app, client, fake_meta, fake_storage = api

    await post_webhook(client, wa_image_payload())
    await post_webhook(client, wa_image_payload())  # Meta redelivery

    assert await db.pool.fetchval("select count(*) from wa_messages where direction='in'") == 1
    assert await db.pool.fetchval("select count(*) from jobs") == 1

    while await run_one_job(db, app.state.wa, app.state.storage):
        pass
    assert await db.pool.fetchval("select count(*) from documents") == 1
    assert len(fake_storage.objects) == 1


async def test_text_message_gets_onboarding_reply(api, db):
    app, client, fake_meta, _ = api
    payload = wa_image_payload(message_id="wamid.txt1")
    msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    msg.update({"type": "text", "text": {"body": "hello"}})
    del msg["image"]

    await post_webhook(client, payload)
    assert await run_one_job(db, app.state.wa, app.state.storage) is True
    assert fake_meta.sent[-1]["text"]["body"] == REPLY_TEXT_ONBOARDING
    assert await db.pool.fetchval("select count(*) from documents") == 0


async def test_unknown_sender_is_stamped_and_creates_nothing(api, db):
    """Inverted by WP-72: until M7 an unknown phone fell back to the oldest
    tenant and could feed its books. Now the inbound row is stamped, the phone
    is told once to ask the owner, and no document or job exists for it."""
    app, client, fake_meta, fake_storage = api
    await post_webhook(client, wa_image_payload(message_id="wamid.unk", from_phone="971559999999"))
    assert await run_one_job(db, app.state.wa, app.state.storage) is True
    assert (await db.get_inbound_message("wamid.unk"))["status"] == WA_STATUS_IGNORED_UNKNOWN_SENDER
    assert await db.get_document_by_wa_message("wamid.unk") is None
    assert await db.pool.fetchval("select count(*) from documents") == 0
    assert await db.pool.fetchval("select count(*) from jobs where kind = 'extract_document'") == 0
    assert fake_storage.objects == {}
    assert [m["text"]["body"] for m in fake_meta.sent] == [REPLY_UNKNOWN_SENDER]


async def test_failed_job_requeues_then_fails(api, db):
    app, client, fake_meta, _ = api

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    from faida_api.wa import WhatsAppClient as WAC

    broken_wa = WAC(app.state.settings, transport=httpx.MockTransport(broken))

    await post_webhook(client, wa_image_payload())
    assert await run_one_job(db, broken_wa, app.state.storage) is True
    job = await db.pool.fetchrow("select * from jobs")
    assert job["status"] == "queued" and job["attempts"] == 1
    assert "boom" in job["last_error"] or "500" in job["last_error"]
