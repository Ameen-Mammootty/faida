"""Background worker: claims jobs from the Postgres queue and processes them.
Runs as an asyncio task inside the API process - a broker is banned until
volume proves the need (plan §3).

The worker fails closed (M7 WP-72, C2 as amended). `process_wa_message` is
the one resolver: the sender phone maps to a branch and its tenant, and every
job it enqueues carries both. A phone no branch is registered to gets its
inbound row stamped, one polite reply a day, and nothing else - no document,
no job, no model spend, and no fallback to any tenant.

From M10 (WP-103) the loop also owns the one clock in the product. Nothing
here ticked at a wall-clock time before: the queue knew how to hold a job
until `run_after` and nothing ever looked at the calendar. `tick_briefs` is
that look - once a minute, on every pass and before a job is claimed, so a
morning of extraction cannot starve the morning brief - and everything it
decides it decides by enqueuing a `send_brief` job through a unique index, so
two API instances, a restart mid-tick and a catch-up after a deploy all come
to the same one job per recipient per local day (C15.3, C15.5). `send_brief`
is then an ordinary handler: read, compose, send once, record."""

import asyncio
import datetime
import hashlib
import logging
import time
import zoneinfo

import httpx

from . import brief, brief_card, dashboard
from .confirm import handle_inbound_text
from .contracts import (
    MEDIA_TYPES,
    WA_STATUS_IGNORED_BRIEF_RECIPIENT,
    WA_STATUS_IGNORED_REACTION,
    WA_STATUS_IGNORED_UNKNOWN_SENDER,
    JobKind,
    JobRefused,
    job_tenant_id,
)
from .db import Database
from .extraction.pipeline import extract_document
from .extraction.provider import ExtractionProvider
from .replies import (
    DEFAULT_CURRENCY,
    REPLY_BRIEF_RECIPIENT,
    REPLY_MEDIA_RECEIVED,
    REPLY_UNKNOWN_SENDER,
    REPLY_UNSUPPORTED_TYPE,
    Reply,
)
from .storage import Storage
from .wa import WhatsAppClient

logger = logging.getLogger(__name__)

# An unknown phone is answered once inside this window, then left alone: a
# phone that keeps forwarding is not helped by hearing the same sentence back
# each time, and the silence is derived from the stamped rows, not remembered.
# A brief recipient writing back is answered under the same rule and the same
# window, counted separately because it is a different sentence (C15.10).
UNKNOWN_SENDER_SILENCE = datetime.timedelta(hours=24)

#: Past this local hour the day's brief is skipped rather than sent late
#: (C15.5, P11): a "morning brief" at ten at night is noise, and by then
#: tomorrow's is nine hours away. Five hours of grace after the default 07:00
#: covers a deploy and most outages, which is the whole point of the catch-up.
BRIEF_SEND_UNTIL_LOCAL = datetime.time(12, 0)

#: How often the loop looks at the calendar. The queue is polled every two
#: seconds when it is idle and the tick is one small query, so once a minute
#: is the difference between a cheap habit and a pointless one; a brief is due
#: at a minute's resolution and nothing about a morning needs better.
BRIEF_TICK_SECONDS = 60

#: How many price moves the spikes' read lists. The brief prints the three
#: biggest *rises*, and the panel's list holds both directions ranked by the
#: money they moved, so five - the screen's own limit - can come back holding
#: fewer than three rises on a week of falling prices. Ten is the headroom
#: that costs nothing: the same query, a longer slice, three of them printed.
BRIEF_PRICE_MOVES_READ = 10


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

    if msg_type == "reaction":
        # A thumbs-up on one of our replies (or its removal) is a receipt,
        # not a message: stamped and left alone, before the phone is even
        # looked up, so an unknown phone's reaction costs it no reply either.
        await db.set_inbound_message_status(msg_row["message_id"], WA_STATUS_IGNORED_REACTION)
        return

    # Branch is resolved from the sender phone number, never from document
    # text - and never from a default. No branch means no tenant, and no
    # tenant means nothing is created.
    branch = await db.branch_for_phone(from_phone) if from_phone else None
    if branch is None:
        # C15.10: the second lookup, and only ever the second one. A phone
        # that is both a branch's and a brief recipient's is a branch, so the
        # founder's own handset - which is both - keeps forwarding invoices.
        recipient = await db.brief_recipient_for_phone(from_phone) if from_phone else None
        if recipient is None:
            await _ignore_unknown_sender(db, wa, msg_row)
        else:
            await _ignore_brief_recipient(db, wa, msg_row)
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
        # The ack quotes the photo it is about (WP-125), as every reply
        # about a paper does from here on.
        reply = Reply(body=REPLY_MEDIA_RECEIVED, reply_to=msg_row["message_id"])
    elif msg_type == "text":
        # WP-21 (C5): the text may confirm or correct an awaiting invoice;
        # onboarding stays the fallback when nothing is pending.
        text = (raw.get("text") or {}).get("body") or ""
        reply = await handle_inbound_text(
            db, from_phone, text, msg_row["created_at"], message_id=msg_row["message_id"]
        )
    else:
        reply = Reply(body=REPLY_UNSUPPORTED_TYPE)

    out_id = await wa.send_text(from_phone, reply.body, reply_to=reply.reply_to)
    await db.record_outbound_message(out_id, from_phone, reply.body, reply_to=reply.reply_to)


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


async def _ignore_brief_recipient(db: Database, wa: WhatsAppClient, msg_row) -> None:
    """A phone that receives the morning brief and is no branch's (C15.10).

    `_ignore_unknown_sender`'s shape exactly - stamp first, one reply inside
    the 24-hour window, best-effort, nothing created - with one difference
    that is the whole reason it exists: the sentence. This phone is an owner
    writing back to a message we sent, most often "thanks", and the unknown
    sender's answer would tell the owner to ask the owner to add the number.
    The stamp is its own status, so the silence is counted over the replies
    this sentence was actually sent for."""
    message_id = msg_row["message_id"]
    from_phone = msg_row["from_phone"]
    await db.set_inbound_message_status(message_id, WA_STATUS_IGNORED_BRIEF_RECIPIENT)
    logger.info("ignored message %s from brief recipient %s", message_id, from_phone)
    already_told = await db.inbound_status_seen_from_phone(
        from_phone,
        WA_STATUS_IGNORED_BRIEF_RECIPIENT,
        within=UNKNOWN_SENDER_SILENCE,
        exclude_message_id=message_id,
    )
    if already_told:
        return
    try:
        out_id = await wa.send_text(from_phone, REPLY_BRIEF_RECIPIENT)
        await db.record_outbound_message(out_id, from_phone, REPLY_BRIEF_RECIPIENT)
    except Exception:
        logger.exception("brief-recipient reply to %s failed; not retried", from_phone)


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


async def read_brief(db: Database, tenant_id: str, *, today: datetime.date) -> brief.Brief:
    """One morning's brief for one tenant: the two reads of C15.1 and the
    filler over them. The one place those two reads are made, so the job at
    07:00 and the founder's dry run print the same words for the same day.

    The first read is the dashboard's own default window - 28 days ending on
    the newest loaded day - and gives the price spikes and nothing else. The
    second is the month to date, from the first of the newest loaded day's
    month to that day, and gives the four figures, the branch table and the
    items. Two reads and not one because the brief's spikes are a different
    question from its month, and the read is the same function with a
    different window (C15.1); P9's one-read rule was about a screen whose
    blocks must agree with each other, and these two never share a figure.

    `today` is the recipient's own local date (C15.6), so the day named in
    the header is aged the way the phone reading it would age it.

    A tenant with nothing loaded has no month to read: the first read's
    freshness carries no day, the filler answers `quiet` on it, and no
    message is sent (C15.7)."""
    currency = await db.tenant_currency(tenant_id) or DEFAULT_CURRENCY
    window = await dashboard.read_dashboard(
        db, tenant_id, today=today, price_moves_limit=BRIEF_PRICE_MOVES_READ
    )
    sales_through = (window.get("freshness") or {}).get("sales_through")
    if sales_through is None:
        # Nothing is loaded, so there is no month to ask about. Composing the
        # window read against itself is the quiet brief by the filler's own
        # rule (no freshness sentence, no latest day), and keeps "what a quiet
        # brief is" in one place rather than two.
        return brief.compose(window, window, currency=currency)
    newest = datetime.date.fromisoformat(sales_through)
    month = await dashboard.read_dashboard(
        db,
        tenant_id,
        today=today,
        date_from=newest.replace(day=1),
        date_to=newest,
    )
    return brief.compose(month, window, currency=currency)


async def _store_card(storage: Storage, card_path: str, png: bytes) -> None:
    """Put the morning's card in storage, forgiving the one refusal that means
    it is already there.

    Nothing this product stores is ever overwritten (`x-upsert: false`,
    storage.py), so a retry of a job that failed after this step meets its own
    first attempt: Supabase answers 409, or a 400 naming the duplicate. That
    is not a failure here - `brief_card.render_card` is deterministic for the
    same `Brief`, so the object already at that key is byte for byte what this
    attempt would have written, and losing a morning to our own evidence would
    be absurd. Every other refusal raises: storage that is down must stop the
    job before a message goes out with no picture behind it."""
    try:
        await storage.put(card_path, png, "image/png")
    except httpx.HTTPStatusError as exc:
        body = (exc.response.text or "").lower()
        already_there = exc.response.status_code == 409 or (
            exc.response.status_code == 400 and ("already exists" in body or "duplicate" in body)
        )
        if not already_there:
            raise
        logger.info("card already stored at %s; the retry carries on", card_path)


async def send_brief_card(
    wa: WhatsAppClient,
    storage: Storage,
    morning: brief.Brief,
    *,
    phone: str,
    card_path: str,
) -> str:
    """Draw the card, store it, upload it and send the template with it as the
    header. Returns Meta's message id (M10 WP-106, C15.4).

    The one door for a brief that leaves the building: the 07:00 job and the
    founder's rehearsal from the command line both come through here, so the
    picture on the phone, the copy in storage and the header on the message
    cannot drift apart between them. The caller owns the record row, because
    that is the only thing the two doors say differently (a rehearsal sits
    outside the day's key).

    The order is store, upload, send, and it is the order for a reason: the
    evidence exists before the message does. A card stored and never sent is a
    stray object nobody reads; a card sent and never stored is a morning we
    cannot show back to the owner who asks what the picture said. An upload
    Meta refuses raises here, before any message leaves, so a half-sent brief
    is not a thing that can happen (§7's card failure row)."""
    # a. The picture, drawn from the same `Brief` the five parameters came
    #    from, so the card and the text can never quote two mornings.
    png = brief_card.render_card(morning)
    # b. The immutable copy, before anything is sent: what the phone showed
    #    can be opened again (C15.4).
    await _store_card(storage, card_path, png)
    # c. Meta wants the file itself, not a link; a refusal fails the job here.
    media_id = await wa.upload_media(png, "image/png")
    # d. The header component names that media id and comes first (§3.1).
    return await wa.send_template(
        phone,
        brief.TEMPLATE_NAME,
        brief.TEMPLATE_LANGUAGE,
        morning.parameters,
        header_image_id=media_id,
    )


async def send_brief(db: Database, wa: WhatsAppClient, storage: Storage, payload: dict) -> None:
    """One morning, one recipient, one message (C15.1, C15.3, C15.4).

    The job carries its tenant and refuses to run without it (C2), and the
    recipient row is read scoped by that tenant - so a job can never carry one
    chain's figures to another chain's phone, and a recipient row deleted
    between the tick and the send fails the job rather than guessing.

    Everything is composed before anything is sent, so a read that raises
    costs nothing and a retry starts over cleanly. Two guards stand between a
    job and a duplicate morning: the unique index the tick enqueues through,
    and the outbound row this checks for - which is what makes running the
    same payload twice by hand harmless too.

    The one honest limit is named in C15.3 and pinned by a test: if Meta
    accepts the message and the record write then raises, the retry finds no
    row and sends the same brief once more. The alternative - recording before
    sending - would lose a morning instead of repeating one, and a repeated
    brief is the better failure.

    The picture card goes through `send_brief_card`: stored at
    `{tenant_id}/briefs/{brief_date}/{recipient_id}.png` first, uploaded, then
    sent as the template's header, so the evidence of a morning exists before
    the message does and a retry that meets its own stored card carries on
    (WP-106, C15.4)."""
    tenant_id = job_tenant_id(JobKind.SEND_BRIEF, payload)
    recipient_id = str(payload["recipient_id"])
    brief_date = str(payload["brief_date"])
    recipient = await db.get_brief_recipient(recipient_id, tenant_id=tenant_id)
    if recipient is None:
        raise JobRefused(
            f"send_brief job names recipient {recipient_id}, which is not tenant "
            f"{tenant_id}'s (C2): the job fails rather than guessing a phone"
        )
    if recipient["paused_at"] is not None:
        # Paused between the tick and the send: the row is the per-recipient
        # switch, and it is read last, not first.
        logger.info("brief skipped: recipient %s is paused", recipient_id)
        return

    morning = await read_brief(db, tenant_id, today=datetime.date.fromisoformat(brief_date))
    if morning.quiet:
        logger.info("brief skipped: nothing loaded for tenant %s", tenant_id)
        return
    if await db.outbound_brief_exists(recipient_id=recipient_id, brief_date=brief_date):
        logger.info("brief already sent to recipient %s for %s", recipient_id, brief_date)
        return

    card_path = f"{tenant_id}/briefs/{brief_date}/{recipient_id}.png"
    message_id = await send_brief_card(
        wa, storage, morning, phone=recipient["phone_e164"], card_path=card_path
    )
    await db.record_outbound_template(
        message_id,
        recipient["phone_e164"],
        template=brief.TEMPLATE_NAME,
        language=brief.TEMPLATE_LANGUAGE,
        parameters=list(morning.parameters),
        tenant_id=tenant_id,
        recipient_id=recipient_id,
        brief_date=brief_date,
        rehearsal=False,
        card_path=card_path,
    )
    logger.info("brief sent to recipient %s for %s as %s", recipient_id, brief_date, message_id)


async def tick_briefs(
    db: Database, now_utc: datetime.datetime, *, spoken: set | None = None
) -> int:
    """Look at the calendar once and enqueue the mornings that have come
    (C15.5, P1). Returns how many jobs were enqueued.

    This is the whole scheduler: no broker, no timer task, no cron. Each
    active recipient carries its own timezone and its own hour, so the local
    date and the local time are computed here, in Python, with `zoneinfo` -
    and a tenant with two recipients in two timezones has two mornings. The
    job is enqueued against 0022's unique index, which is what makes the tick
    idempotent whether it runs once, twice, or from two instances at the same
    moment.

    A timezone name that does not resolve is logged with its recipient and
    skipped, so one typo cannot silence every other recipient. Past
    `BRIEF_SEND_UNTIL_LOCAL` the day is skipped with one log line per
    recipient per day - `spoken` is what makes it one line and not one a
    minute for five hours - because a morning brief sent in the evening is
    noise (P11). A `send_at_local` later than the cutoff never fires at all,
    which is a row to fix and not a case to code around: the paste file's
    read-back prints each recipient's local time beside its send hour.

    `now_utc` is passed in rather than read here, so a test can put the clock
    where it needs it; a naive value is taken as UTC, which is what its name
    says it is."""
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=datetime.UTC)
    enqueued = 0
    for row in await db.list_active_brief_recipients():
        name = row["timezone"]
        try:
            zone = zoneinfo.ZoneInfo(name)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            logger.warning(
                "brief recipient %s has an unusable timezone %r; skipped", row["id"], name
            )
            continue
        local = now_utc.astimezone(zone)
        if local.time() < row["send_at_local"]:
            continue
        if local.time() >= BRIEF_SEND_UNTIL_LOCAL:
            key = (row["id"], local.date())
            if spoken is None or key not in spoken:
                logger.info(
                    "brief skipped: %s local is past %s for recipient %s; tomorrow's is next",
                    local.strftime("%H:%M"),
                    BRIEF_SEND_UNTIL_LOCAL.strftime("%H:%M"),
                    row["id"],
                )
                if spoken is not None:
                    spoken.add(key)
            continue
        job_id = await db.enqueue_brief_once(
            {
                "tenant_id": row["tenant_id"],
                "recipient_id": row["id"],
                "brief_date": local.date().isoformat(),
            }
        )
        if job_id is not None:
            enqueued += 1
            logger.info(
                "brief queued for recipient %s on %s (job %s)",
                row["id"],
                local.date().isoformat(),
                job_id,
            )
    return enqueued


HANDLERS = {
    JobKind.PROCESS_WA_MESSAGE: process_wa_message,
    JobKind.EXTRACT_DOCUMENT: extract_document,
    JobKind.SEND_BRIEF: send_brief,
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
    *,
    brief_enabled: bool = True,
) -> None:
    """The queue, and from M10 the calendar beside it.

    The tick runs on every pass and *before* a job is claimed, at most once a
    `BRIEF_TICK_SECONDS` by a monotonic clock, so a queue with a morning's
    extraction backlog in it cannot starve the morning brief (C15.5): the loop
    spends one small query a minute and claims a job as it always did. A tick
    that raises is logged and swallowed - a fault in the calendar must never
    stop the queue - and the next pass tries again.

    `brief_enabled` is the kill switch (`BRIEF_ENABLED`, config.py). Its
    default is True so that every caller that predates it keeps working; the
    empty recipient table is the safe state either way."""
    logger.info("worker loop started")
    #: One log line per (recipient, local day) for a morning already past its
    #: cutoff, instead of one a minute for five hours. One small tuple per
    #: recipient per day, for as long as the process lives.
    spoken: set = set()
    last_tick: float | None = None
    while not stop.is_set():
        if brief_enabled and (
            last_tick is None or time.monotonic() - last_tick >= BRIEF_TICK_SECONDS
        ):
            last_tick = time.monotonic()
            try:
                await tick_briefs(db, datetime.datetime.now(datetime.UTC), spoken=spoken)
            except Exception:
                logger.exception("brief tick failed; the queue carries on")
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
