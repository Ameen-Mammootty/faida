"""Background worker: claims jobs from the Postgres queue and processes them.
Runs as an asyncio task inside the API process - a broker is banned until
volume proves the need (plan §3).

The worker fails closed (M7 WP-72, C2 as amended). `process_wa_message` is
the one resolver: the sender phone maps to a branch and its tenant, and every
job it enqueues carries both. A phone no branch is registered to gets its
inbound row stamped, one polite reply a day, and nothing else - no document,
no job, no model spend, and no fallback to any tenant."""

import asyncio
import datetime
import hashlib
import logging
import time

from .confirm import handle_inbound_text
from .contracts import MEDIA_TYPES, WA_STATUS_IGNORED_UNKNOWN_SENDER, JobKind
from .db import Database
from .extraction.pipeline import extract_document
from .extraction.provider import ExtractionProvider
from .replies import REPLY_MEDIA_RECEIVED, REPLY_UNKNOWN_SENDER, REPLY_UNSUPPORTED_TYPE
from .storage import Storage
from .wa import WhatsAppClient

logger = logging.getLogger(__name__)

# An unknown phone is answered once inside this window, then left alone: a
# phone that keeps forwarding is not helped by hearing the same sentence back
# each time, and the silence is derived from the stamped rows, not remembered.
UNKNOWN_SENDER_SILENCE = datetime.timedelta(hours=24)


async def process_wa_message(
    db: Database, wa: WhatsAppClient, storage: Storage, payload: dict
) -> None:
    """C2's first job and its one resolver: phone to branch and tenant, then
    ingest, then the immediate ack. Everything it enqueues carries the scope
    it resolved here."""
    msg_row = await db.get_inbound_message(payload["message_id"])
    if msg_row is None:
        logger.warning("job for unknown message %s", payload["message_id"])
        return

    raw = msg_row["payload"]
    from_phone = msg_row["from_phone"]
    msg_type = msg_row["msg_type"]

    # Branch is resolved from the sender phone number, never from document
    # text - and never from a default. No branch means no tenant, and no
    # tenant means nothing is created.
    branch = await db.branch_for_phone(from_phone) if from_phone else None
    if branch is None:
        await _ignore_unknown_sender(db, wa, msg_row)
        return
    tenant_id = str(branch["tenant_id"])
    branch_id = str(branch["id"])

    if msg_type in MEDIA_TYPES:
        document_id = await _ingest_media(
            db, wa, storage, raw, msg_row["message_id"], tenant_id, branch_id
        )
        # C2: the pipeline runs as a second job carrying the scope resolved
        # above; the ack below stays immediate. Once per document, ever: a
        # retry of this job after a failed ack lands here again, after the
        # first extraction has already finished, and enqueues nothing.
        await db.enqueue_once(
            JobKind.EXTRACT_DOCUMENT,
            {"document_id": document_id, "tenant_id": tenant_id, "branch_id": branch_id},
        )
        reply = REPLY_MEDIA_RECEIVED
    elif msg_type == "text":
        # WP-21 (C5): the text may confirm or correct an awaiting invoice;
        # onboarding stays the fallback when nothing is pending.
        text = (raw.get("text") or {}).get("body") or ""
        reply = await handle_inbound_text(
            db, from_phone, text, msg_row["created_at"], message_id=msg_row["message_id"]
        )
    else:
        reply = REPLY_UNSUPPORTED_TYPE

    out_id = await wa.send_text(from_phone, reply)
    await db.record_outbound_message(out_id, from_phone, reply)


async def _ignore_unknown_sender(db: Database, wa: WhatsAppClient, msg_row) -> None:
    """A phone no branch is registered to (C2 as amended, D9). The stamp goes
    on the inbound row first, so the decision is recorded before anything
    leaves the building and a retry finds it already made. Then one reply,
    unless another message from the same phone was already stamped inside
    the window - the current message is excluded from that lookup, or the
    first message would silence its own reply. The reply is best-effort: a
    send failure is logged and the job still succeeds, because there is
    nothing to retry for a phone we do not know."""
    message_id = msg_row["message_id"]
    from_phone = msg_row["from_phone"]
    await db.set_inbound_message_status(message_id, WA_STATUS_IGNORED_UNKNOWN_SENDER)
    logger.warning("ignored message %s from unknown sender %s", message_id, from_phone)
    if not from_phone:
        return  # nowhere to send a reply
    already_told = await db.inbound_status_seen_from_phone(
        from_phone,
        WA_STATUS_IGNORED_UNKNOWN_SENDER,
        within=UNKNOWN_SENDER_SILENCE,
        exclude_message_id=message_id,
    )
    if already_told:
        return
    try:
        out_id = await wa.send_text(from_phone, REPLY_UNKNOWN_SENDER)
        await db.record_outbound_message(out_id, from_phone, REPLY_UNKNOWN_SENDER)
    except Exception:
        logger.exception("unknown-sender reply to %s failed; not retried", from_phone)


async def _ingest_media(
    db: Database,
    wa: WhatsAppClient,
    storage: Storage,
    raw_msg: dict,
    wa_message_id: str,
    tenant_id: str,
    branch_id: str,
) -> str:
    """Download media (URLs expire - do it promptly), hash it, store the immutable
    original, record the document. Idempotent so job retries are safe. Returns
    the document id."""
    existing = await db.get_document_by_wa_message(wa_message_id)
    if existing is not None and existing["storage_path"] is not None:
        return str(existing["id"])  # fully ingested on a previous attempt

    msg_type = raw_msg["type"]
    media_id = raw_msg.get(msg_type, {}).get("id")
    if not media_id:
        raise ValueError(f"media message {wa_message_id} has no media id")

    started = time.monotonic()
    data, mime = await wa.get_media(media_id)
    download_ms = int((time.monotonic() - started) * 1000)
    sha256 = hashlib.sha256(data).hexdigest()

    if existing is None:
        document_id = await db.insert_document(tenant_id, branch_id, wa_message_id, mime, sha256)
    else:
        document_id = str(existing["id"])

    # WP-41: per-stage latency, logged once the document id exists.
    logger.info("latency stage=download document=%s elapsed_ms=%d", document_id, download_ms)
    started = time.monotonic()
    path = f"{tenant_id}/documents/{document_id}/original"
    await storage.put(path, data, mime)
    await db.set_document_storage_path(document_id, path, tenant_id=tenant_id)
    logger.info(
        "latency stage=store document=%s elapsed_ms=%d",
        document_id,
        int((time.monotonic() - started) * 1000),
    )
    return document_id


HANDLERS = {
    JobKind.PROCESS_WA_MESSAGE: process_wa_message,
    JobKind.EXTRACT_DOCUMENT: extract_document,
}


async def run_one_job(
    db: Database,
    wa: WhatsAppClient,
    storage: Storage,
    provider: ExtractionProvider | None = None,
) -> bool:
    """Claim and run a single job. Returns False when the queue is empty."""
    job = await db.claim_job()
    if job is None:
        return False
    handler = HANDLERS.get(job["kind"])
    try:
        if handler is None:
            raise ValueError(f"unknown job kind: {job['kind']}")
        if job["kind"] == JobKind.EXTRACT_DOCUMENT:
            # claim_job returns the pre-claim row: this attempt is attempts + 1.
            await handler(db, wa, storage, provider, job["payload"], attempts=job["attempts"] + 1)
        else:
            await handler(db, wa, storage, job["payload"])
        await db.finish_job(job["id"], ok=True)
    except Exception as exc:
        logger.exception("job %s (%s) failed", job["id"], job["kind"])
        await db.finish_job(job["id"], ok=False, error=repr(exc))
    return True


async def worker_loop(
    db: Database,
    wa: WhatsAppClient,
    storage: Storage,
    provider: ExtractionProvider | None,
    stop: asyncio.Event,
    poll_seconds: float,
) -> None:
    logger.info("worker loop started")
    while not stop.is_set():
        try:
            worked = await run_one_job(db, wa, storage, provider)
        except Exception:
            logger.exception("worker loop error")
            worked = False
        if not worked:
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass
    logger.info("worker loop stopped")
