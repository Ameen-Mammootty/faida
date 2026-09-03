"""M7 WP-72: the worker fails closed (plan.md §7.2 C2 as amended, §8 M7).

Three rules under test, against a real Postgres with Meta, storage and the
extraction provider mocked at the transport layer like every flow test:

- A job names its tenant, and a handler refuses a row that belongs to
  another one. A job with no tenant, or with the wrong one, fails; it never
  guesses and never touches the row.
- A phone no branch is registered to gets nothing: its inbound row is
  stamped before anything else, it is told once a day to ask the owner to
  add the number, and no document, job or model call exists for it.
- One extract job per document, ever. The retried ack after a failed send
  lands after the first extraction is done, and enqueues nothing.
"""

import httpx
import pytest
from fastapi import FastAPI

from faida_api.contracts import WA_STATUS_IGNORED_UNKNOWN_SENDER, JobKind
from faida_api.replies import REPLY_MEDIA_RECEIVED, REPLY_UNKNOWN_SENDER
from faida_api.storage import Storage
from faida_api.wa import WhatsAppClient
from faida_api.webhook import router as webhook_router
from faida_api.worker import run_one_job

from .conftest import (
    DEMO_PHONE,
    DEMO_TENANT_ID,
    FakeExtraction,
    FakeMeta,
    FakeStorage,
    requires_db,
    wa_image_payload,
)
from .test_extraction_flow import drain_jobs, good_invoice, invoice_result, post_webhook

pytestmark = requires_db

TENANT_A = DEMO_TENANT_ID
BRANCH_A = "00000000-0000-0000-0000-000000000011"
TENANT_B = "b0000000-0000-0000-0000-000000000001"
BRANCH_B = "b0000000-0000-0000-0000-000000000011"
PHONE_B = "971520000000"
UNKNOWN_PHONE = "971559999999"


@pytest.fixture
async def rig(settings, db):
    """The webhook app over the test DB with both tenants seeded: tenant A is
    seed.sql's demo chain, tenant B is another chain whose branch has its own
    registered phone."""
    fake_meta = FakeMeta()
    fake_storage = FakeStorage()

    app = FastAPI()
    app.include_router(webhook_router)
    app.state.settings = settings
    app.state.db = db
    app.state.wa = WhatsAppClient(settings, transport=fake_meta.transport())
    app.state.storage = Storage(settings, transport=fake_storage.transport())

    await db.pool.execute(
        "insert into tenants (id, name, currency) values ($1, 'Other Chain', 'AED')", TENANT_B
    )
    await db.pool.execute(
        "insert into branches (id, tenant_id, name, wa_phone_e164, timezone) "
        "values ($1, $2, 'Elsewhere', $3, 'Asia/Dubai')",
        BRANCH_B,
        TENANT_B,
        PHONE_B,
    )
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return app, client, fake_meta, fake_storage


def broken_wa(app, fake_meta: FakeMeta) -> WhatsAppClient:
    """A Graph API whose message send answers 500; media still downloads, so
    the ingest half of the job succeeds and only the ack fails."""
    working = fake_meta.transport()

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages"):
            return httpx.Response(500, json={"error": "boom"})
        return working.handle_request(request)

    return WhatsAppClient(app.state.settings, transport=httpx.MockTransport(handle))


async def seed_document(db, fake_storage, *, tenant_id: str, branch_id: str | None) -> str:
    """A stored original under one tenant, as the upload endpoint leaves it."""
    document_id = await db.insert_uploaded_document(
        tenant_id=tenant_id, branch_id=branch_id, mime="image/jpeg", sha256="b" * 64
    )
    path = f"{tenant_id}/documents/{document_id}/original"
    fake_storage.objects[path] = b"\xff\xd8other-tenants-paper"
    await db.set_document_storage_path(document_id, path, tenant_id=tenant_id)
    return document_id


async def jobs_of_kind(db, kind: str) -> list:
    return await db.pool.fetch("select * from jobs where kind = $1 order by id", kind)


async def inbound_status(db, message_id: str) -> str:
    return (await db.get_inbound_message(message_id))["status"]


# --- the one security test that matters most ----------------------------------


async def test_job_built_with_tenant_a_against_tenant_b_document_is_refused(rig, db):
    app, client, fake_meta, fake_storage = rig
    document_id = await seed_document(db, fake_storage, tenant_id=TENANT_B, branch_id=BRANCH_B)
    provider = FakeExtraction(result=invoice_result(good_invoice()))

    await db.enqueue_once(
        JobKind.EXTRACT_DOCUMENT,
        {"document_id": document_id, "tenant_id": TENANT_A, "branch_id": BRANCH_A},
    )
    await drain_jobs(db, app, provider, release_backoff=True)

    # The job fails, loudly, on every attempt - and never guesses.
    (job,) = await jobs_of_kind(db, JobKind.EXTRACT_DOCUMENT)
    assert job["status"] == "failed"
    assert TENANT_A in job["last_error"] and document_id in job["last_error"]
    # Tenant B's paper was never touched: no model call, no status change, no
    # invoice, no reply.
    assert provider.extract_calls == []
    doc = await db.get_document(document_id, tenant_id=TENANT_B)
    assert doc["status"] == "received"
    assert await db.get_invoice_by_document(document_id, tenant_id=TENANT_B) is None
    assert await db.pool.fetchval("select count(*) from invoices") == 0
    assert await db.pool.fetchval("select count(*) from extraction_runs") == 0
    assert fake_meta.sent == []


async def test_job_without_a_tenant_is_a_failed_job(rig, db):
    """A job queued before the deploy carries no tenant; the handler refuses
    it rather than reading the row to guess. Same fate for a wrong shape."""
    app, client, fake_meta, fake_storage = rig
    document_id = await seed_document(db, fake_storage, tenant_id=TENANT_A, branch_id=BRANCH_A)
    provider = FakeExtraction(result=invoice_result(good_invoice()))

    await db.enqueue_once(JobKind.EXTRACT_DOCUMENT, {"document_id": document_id})
    await drain_jobs(db, app, provider, release_backoff=True)

    (job,) = await jobs_of_kind(db, JobKind.EXTRACT_DOCUMENT)
    assert job["status"] == "failed"
    assert "tenant" in job["last_error"]
    assert provider.extract_calls == []
    doc = await db.get_document(document_id, tenant_id=TENANT_A)
    assert doc["status"] == "received"
    assert await db.pool.fetchval("select count(*) from invoices") == 0


# --- the unknown sender -------------------------------------------------------


async def test_unknown_phone_is_stamped_answered_once_and_creates_nothing(rig, db):
    app, client, fake_meta, fake_storage = rig

    await post_webhook(client, wa_image_payload(message_id="wamid.unk1", from_phone=UNKNOWN_PHONE))
    assert await run_one_job(db, app.state.wa, app.state.storage) is True

    # The decision is recorded on the inbound row itself.
    assert await inbound_status(db, "wamid.unk1") == WA_STATUS_IGNORED_UNKNOWN_SENDER
    # Exactly one reply, the polite one, recorded outbound like every reply.
    assert [(m["to"], m["text"]["body"]) for m in fake_meta.sent] == [
        (UNKNOWN_PHONE, REPLY_UNKNOWN_SENDER)
    ]
    out = await db.pool.fetch("select * from wa_messages where direction = 'out'")
    assert len(out) == 1 and out[0]["to_phone"] == UNKNOWN_PHONE
    # Nothing else exists for this phone: no document, no stored original, no
    # extract job. The one job is the ingest job, and it succeeded.
    assert await db.pool.fetchval("select count(*) from documents") == 0
    assert fake_storage.objects == {}
    assert await jobs_of_kind(db, JobKind.EXTRACT_DOCUMENT) == []
    (job,) = await jobs_of_kind(db, JobKind.PROCESS_WA_MESSAGE)
    assert job["status"] == "done"


async def test_second_message_from_unknown_phone_inside_24h_is_stamped_and_silent(rig, db):
    app, client, fake_meta, fake_storage = rig

    for message_id in ("wamid.unk1", "wamid.unk2"):
        payload = wa_image_payload(message_id=message_id, from_phone=UNKNOWN_PHONE)
        await post_webhook(client, payload)
        assert await run_one_job(db, app.state.wa, app.state.storage) is True

    assert await inbound_status(db, "wamid.unk1") == WA_STATUS_IGNORED_UNKNOWN_SENDER
    assert await inbound_status(db, "wamid.unk2") == WA_STATUS_IGNORED_UNKNOWN_SENDER
    assert len(fake_meta.sent) == 1
    assert await db.pool.fetchval("select count(*) from documents") == 0
    assert await jobs_of_kind(db, JobKind.EXTRACT_DOCUMENT) == []

    # Once the earlier stamp is older than a day, the phone is told again.
    await db.pool.execute(
        "update wa_messages set created_at = now() - interval '25 hours' where direction = 'in'"
    )
    await post_webhook(client, wa_image_payload(message_id="wamid.unk3", from_phone=UNKNOWN_PHONE))
    assert await run_one_job(db, app.state.wa, app.state.storage) is True
    assert await inbound_status(db, "wamid.unk3") == WA_STATUS_IGNORED_UNKNOWN_SENDER
    assert len(fake_meta.sent) == 2
    assert fake_meta.sent[-1]["text"]["body"] == REPLY_UNKNOWN_SENDER


async def test_unknown_sender_text_gets_the_same_treatment(rig, db):
    """A text from a phone we do not know is not a confirmation of anything:
    stamped, answered once, nothing resolved."""
    app, client, fake_meta, _ = rig
    payload = wa_image_payload(message_id="wamid.unktxt", from_phone=UNKNOWN_PHONE)
    msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    msg.update({"type": "text", "text": {"body": "OK"}})
    del msg["image"]

    await post_webhook(client, payload)
    assert await run_one_job(db, app.state.wa, app.state.storage) is True
    assert await inbound_status(db, "wamid.unktxt") == WA_STATUS_IGNORED_UNKNOWN_SENDER
    assert [m["text"]["body"] for m in fake_meta.sent] == [REPLY_UNKNOWN_SENDER]


async def test_unknown_sender_reply_failure_keeps_the_stamp_and_the_job_succeeds(rig, db):
    app, client, fake_meta, fake_storage = rig

    await post_webhook(client, wa_image_payload(message_id="wamid.unk1", from_phone=UNKNOWN_PHONE))
    assert await run_one_job(db, broken_wa(app, fake_meta), app.state.storage) is True

    assert await inbound_status(db, "wamid.unk1") == WA_STATUS_IGNORED_UNKNOWN_SENDER
    (job,) = await jobs_of_kind(db, JobKind.PROCESS_WA_MESSAGE)
    assert job["status"] == "done" and job["attempts"] == 1 and job["last_error"] is None
    assert await db.pool.fetchval("select count(*) from wa_messages where direction = 'out'") == 0
    assert await db.pool.fetchval("select count(*) from documents") == 0
    assert await jobs_of_kind(db, JobKind.EXTRACT_DOCUMENT) == []
    # Nothing is left in the queue to retry: there is nothing to retry for a
    # phone we do not know.
    assert await db.pool.fetchval("select count(*) from jobs where status = 'queued'") == 0


# --- one extract job per document, ever -------------------------------------


async def test_retried_ack_after_extraction_is_done_enqueues_no_second_extract_job(rig, db):
    """The ack send fails after the extract job is queued, so the ingest job
    retries 30 s later - by which time extraction has finished (about 18 s).
    The retry must re-send the ack and mint nothing."""
    app, client, fake_meta, fake_storage = rig
    provider = FakeExtraction(result=invoice_result(good_invoice()))

    await post_webhook(client, wa_image_payload(message_id="wamid.retry"))
    # Attempt 1: ingest and enqueue succeed, the ack send fails, the job requeues.
    assert await run_one_job(db, broken_wa(app, fake_meta), app.state.storage) is True
    (ingest,) = await jobs_of_kind(db, JobKind.PROCESS_WA_MESSAGE)
    assert ingest["status"] == "queued" and ingest["attempts"] == 1
    (extract,) = await jobs_of_kind(db, JobKind.EXTRACT_DOCUMENT)
    assert extract["status"] == "queued"

    # The extract job runs to done while the ingest job waits out its backoff.
    assert await run_one_job(db, app.state.wa, app.state.storage, provider) is True
    (extract,) = await jobs_of_kind(db, JobKind.EXTRACT_DOCUMENT)
    assert extract["status"] == "done"
    assert len(provider.extract_calls) == 1

    # The retried ack lands after the extraction is done.
    await db.pool.execute("update jobs set run_after = now() where status = 'queued'")
    assert await run_one_job(db, app.state.wa, app.state.storage, provider) is True
    (ingest,) = await jobs_of_kind(db, JobKind.PROCESS_WA_MESSAGE)
    assert ingest["status"] == "done" and ingest["attempts"] == 2
    assert fake_meta.sent[-1]["text"]["body"] == REPLY_MEDIA_RECEIVED

    # Still exactly one extract job, still one read, one invoice, one original.
    assert len(await jobs_of_kind(db, JobKind.EXTRACT_DOCUMENT)) == 1
    assert len(provider.extract_calls) == 1
    assert await db.pool.fetchval("select count(*) from invoices") == 1
    assert await db.pool.fetchval("select count(*) from documents") == 1
    assert len(fake_storage.objects) == 1
    assert await run_one_job(db, app.state.wa, app.state.storage, provider) is False


async def test_enqueue_once_returns_the_id_then_none(rig, db):
    _, _, _, fake_storage = rig
    document_id = await seed_document(db, fake_storage, tenant_id=TENANT_A, branch_id=None)
    payload = {"document_id": document_id, "tenant_id": TENANT_A, "branch_id": None}
    first = await db.enqueue_once(JobKind.EXTRACT_DOCUMENT, payload)
    assert first is not None
    assert await db.enqueue_once(JobKind.EXTRACT_DOCUMENT, payload) is None
    # Whatever the first job's status - the index carries no status filter.
    await db.finish_job(first, ok=True)
    assert await db.enqueue_once(JobKind.EXTRACT_DOCUMENT, payload) is None
    assert len(await jobs_of_kind(db, JobKind.EXTRACT_DOCUMENT)) == 1


# --- the registered phone still works ------------------------------------------


async def test_registered_phones_land_in_their_own_branch_and_the_job_carries_it(rig, db):
    app, client, fake_meta, fake_storage = rig

    await post_webhook(client, wa_image_payload(message_id="wamid.a", from_phone=DEMO_PHONE))
    await post_webhook(client, wa_image_payload(message_id="wamid.b", from_phone=PHONE_B))
    assert await run_one_job(db, app.state.wa, app.state.storage) is True
    assert await run_one_job(db, app.state.wa, app.state.storage) is True

    doc_a = await db.get_document_by_wa_message("wamid.a")
    doc_b = await db.get_document_by_wa_message("wamid.b")
    assert (str(doc_a["tenant_id"]), str(doc_a["branch_id"])) == (TENANT_A, BRANCH_A)
    assert (str(doc_b["tenant_id"]), str(doc_b["branch_id"])) == (TENANT_B, BRANCH_B)
    assert await inbound_status(db, "wamid.a") != WA_STATUS_IGNORED_UNKNOWN_SENDER
    assert await inbound_status(db, "wamid.b") != WA_STATUS_IGNORED_UNKNOWN_SENDER

    jobs = await jobs_of_kind(db, JobKind.EXTRACT_DOCUMENT)
    assert [job["payload"] for job in jobs] == [
        {"document_id": str(doc_a["id"]), "tenant_id": TENANT_A, "branch_id": BRANCH_A},
        {"document_id": str(doc_b["id"]), "tenant_id": TENANT_B, "branch_id": BRANCH_B},
    ]
    assert [m["to"] for m in fake_meta.sent] == [DEMO_PHONE, PHONE_B]
    assert [m["text"]["body"] for m in fake_meta.sent] == [REPLY_MEDIA_RECEIVED] * 2

    # And each extraction runs under its own tenant, all the way to an invoice.
    provider = FakeExtraction(result=invoice_result(good_invoice()))
    await drain_jobs(db, app, provider)
    invoice_a = await db.get_invoice_by_document(str(doc_a["id"]), tenant_id=TENANT_A)
    invoice_b = await db.get_invoice_by_document(str(doc_b["id"]), tenant_id=TENANT_B)
    assert str(invoice_a["tenant_id"]) == TENANT_A and str(invoice_b["tenant_id"]) == TENANT_B
    assert await db.get_invoice_by_document(str(doc_b["id"]), tenant_id=TENANT_A) is None
