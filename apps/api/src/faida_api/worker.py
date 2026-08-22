"""Background worker: claims jobs from the Postgres queue and processes them.
Runs as an asyncio task inside the API process — a broker is banned until
volume proves the need (plan §3)."""

import asyncio
import hashlib
import logging

from .contracts import MEDIA_TYPES, JobKind
from .db import Database
from .extraction.pipeline import extract_document
from .extraction.provider import ExtractionProvider
from .storage import Storage
from .wa import WhatsAppClient

logger = logging.getLogger(__name__)

REPLY_MEDIA_RECEIVED = "Got it — invoice received and saved. I'll reply with the details here soon."
REPLY_TEXT = "Hi! Forward a supplier invoice photo here and I'll read it for you."
REPLY_UNSUPPORTED = (
    "I can only read photos or PDF invoices for now — please forward the invoice as a photo."
)


async def process_wa_message(
    db: Database, wa: WhatsAppClient, storage: Storage, payload: dict
) -> None:
    msg_row = await db.get_inbound_message(payload["message_id"])
    if msg_row is None:
        logger.warning("job for unknown message %s", payload["message_id"])
        return

    raw = msg_row["payload"]
    from_phone = msg_row["from_phone"]
    msg_type = msg_row["msg_type"]

    # Branch is resolved from the sender phone number, never from document text.
    branch = await db.branch_for_phone(from_phone) if from_phone else None
    tenant_id = str(branch["tenant_id"]) if branch else await db.default_tenant_id()
    branch_id = str(branch["id"]) if branch else None
    if tenant_id is None:
        raise RuntimeError("no tenant seeded; run supabase/seed.sql")

    if msg_type in MEDIA_TYPES:
        document_id = await _ingest_media(
            db, wa, storage, raw, msg_row["message_id"], tenant_id, branch_id
        )
        # C2: the pipeline runs as a second job; the ack below stays immediate.
        await db.enqueue(JobKind.EXTRACT_DOCUMENT, {"document_id": document_id})
        reply = REPLY_MEDIA_RECEIVED
    elif msg_type == "text":
        reply = REPLY_TEXT
    else:
        reply = REPLY_UNSUPPORTED

    if from_phone:
        out_id = await wa.send_text(from_phone, reply)
        await db.record_outbound_message(out_id, from_phone, reply)


async def _ingest_media(
    db: Database,
    wa: WhatsAppClient,
    storage: Storage,
    raw_msg: dict,
    wa_message_id: str,
    tenant_id: str,
    branch_id: str | None,
) -> str:
    """Download media (URLs expire — do it promptly), hash it, store the immutable
    original, record the document. Idempotent so job retries are safe. Returns
    the document id."""
    existing = await db.get_document_by_wa_message(wa_message_id)
    if existing is not None and existing["storage_path"] is not None:
        return str(existing["id"])  # fully ingested on a previous attempt

    msg_type = raw_msg["type"]
    media_id = raw_msg.get(msg_type, {}).get("id")
    if not media_id:
        raise ValueError(f"media message {wa_message_id} has no media id")

    data, mime = await wa.get_media(media_id)
    sha256 = hashlib.sha256(data).hexdigest()

    if existing is None:
        document_id = await db.insert_document(tenant_id, branch_id, wa_message_id, mime, sha256)
    else:
        document_id = str(existing["id"])

    path = f"{tenant_id}/documents/{document_id}/original"
    await storage.put(path, data, mime)
    await db.set_document_storage_path(document_id, path)
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
