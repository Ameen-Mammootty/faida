"""Pipeline orchestration for the `extract_document` job (plan.md §5, WP-13).

Wires the pure modules together: fetch the stored original, one structured
extract call (layer 1), deterministic validation (layer 2), the scoped repair
round (layer 3), supplier matching + item snapping + price alerts (layer 4,
WP-22/WP-23), then persistence, the C1 document transitions, and one reply
from the WP-20 composer (replies.py). Cash invoices are held as needs_review
(WP-24); layer 4's baseline update runs on confirm only
(Database.record_confirmed_prices).
"""

import datetime
import logging
import time

import asyncpg

from ..contracts import DocumentStatus, InvoiceStatus, JobKind, JobRefused, job_tenant_id
from ..db import RETRY_LIMIT, Database, OwedReply
from ..matching import (
    Row,
    filed_under,
    match_supplier,
    normalize_invoice_no,
    same_name,
)
from ..provenance import Origin, changed_fields, initial, mark
from ..replies import (
    DEFAULT_CURRENCY,
    REPLY_EXTRACTION_FAILED,
    REPLY_NOT_INVOICE,
    REPLY_Z_REPORT,
    SimilarPaper,
    compose_cash_hold_reply,
    compose_duplicate_hold_reply,
    compose_invoice_reply,
)
from ..storage import Storage
from ..wa import WhatsAppClient
from .filing import file_invoice, filed_names
from .normalize import normalize_extracted
from .provider import ExtractionProvider, ProviderUsage
from .repair import repair_invoice
from .schema import Classification, ExtractedInvoice
from .validate import validate_invoice

logger = logging.getLogger(__name__)


def build_provider(
    provider: str, *, anthropic_api_key: str = "", gemini_api_key: str = ""
) -> ExtractionProvider | None:
    """Provider wiring for main.py (provider decision 2026-08-29, Decision
    Log): "gemini" is Gemini 3 Flash, the shipped default; "anthropic" is
    Claude Opus 5, the configured fallback - EXTRACTION_PROVIDER swaps back
    without a deploy. Keys are passed explicitly, no env magic; the selected
    provider without its key yields None - extract jobs then raise and land in
    the failure path. An unknown name raises at boot, loudly, because a typo
    that silently disabled extraction would look identical to a missing key.
    SDK imports stay inside this package (C3)."""
    if provider == "gemini":
        if not gemini_api_key:
            return None
        from google import genai

        from .gemini_provider import GeminiExtractionProvider

        return GeminiExtractionProvider(genai.Client(api_key=gemini_api_key))
    if provider == "anthropic":
        if not anthropic_api_key:
            return None
        import anthropic

        from .anthropic_provider import AnthropicExtractionProvider

        return AnthropicExtractionProvider(anthropic.AsyncAnthropic(api_key=anthropic_api_key))
    raise ValueError(f"unknown extraction provider {provider!r} (gemini or anthropic)")


async def extract_document(
    db: Database,
    wa: WhatsAppClient,
    storage: Storage,
    provider: ExtractionProvider | None,
    payload: dict,
    attempts: int,
) -> None:
    """C2's second job: stored original -> extract -> validate -> repair ->
    draft invoice with checks, under the C1 status machine. `attempts` is the
    current attempt number; provider/transport errors re-raise into the queue
    retry machinery, and on the final attempt the failure path runs first so
    the user is never left hanging (plan.md §5 layer 6).

    The job carries its tenant (C2 as amended, WP-72) and every read here is
    scoped by it. A job with no tenant, or a document that is not in that
    tenant, is refused before anything is touched: no status change, no model
    call, no reply - the job fails with the reason on it, and never guesses."""
    document_id = payload["document_id"]
    tenant_id = job_tenant_id(JobKind.EXTRACT_DOCUMENT, payload)
    doc = await db.get_document(document_id, tenant_id=tenant_id)
    if doc is None:
        raise JobRefused(
            f"extract job names document {document_id} under tenant {tenant_id}, "
            "which has no such document; refusing rather than guessing"
        )
    if await db.get_invoice_by_document(document_id, tenant_id=tenant_id) is not None:
        # A previous attempt read and recorded the paper (invoices_document_uidx
        # is the hard guard). If WhatsApp refused its summary, the summary is
        # still owed: send it now rather than leave the phone in silence.
        await _send_owed_reply(db, wa, document_id)
        return

    # WhatsApp documents reply to their sender; upload/manual (M3) have none.
    # The inbound message row also carries the webhook receipt time the WP-41
    # summary line measures from.
    msg = await db.get_inbound_message(doc["wa_message_id"]) if doc["wa_message_id"] else None
    from_phone = msg["from_phone"] if msg else None
    await db.set_document_status(document_id, DocumentStatus.PROCESSING, tenant_id=tenant_id)

    # WP-41: per-stage elapsed ms, provider stages taken from the usage the
    # provider already timed (never re-timed here).
    stage_ms: dict[str, int] = {}
    # Only a recorded paper owes its reply across attempts; a z-report or a
    # non-invoice writes no invoice, so its retry reads the paper again anyway.
    reply_owed = False
    try:
        if provider is None:
            raise RuntimeError(
                "no extraction provider configured (the selected provider's key is empty)"
            )
        if not doc["storage_path"]:
            raise RuntimeError(f"document {document_id} has no stored original")
        image = await storage.get(doc["storage_path"])
        result, usage = await provider.extract(image, doc["mime"])
        stage_ms["extract"] = usage.latency_ms
        logger.info(
            "latency stage=extract document=%s elapsed_ms=%d", document_id, usage.latency_ms
        )

        if result.classification is Classification.INVOICE:
            if result.invoice is None:
                raise ValueError("provider returned classification 'invoice' with no invoice")
            reply = await _persist_extracted(
                db, provider, doc, image, result.invoice, usage, stage_ms, from_phone=from_phone
            )
            reply_owed = True
        elif result.classification is Classification.Z_REPORT:
            await db.set_document_status(
                document_id, DocumentStatus.FAILED, Classification.Z_REPORT, tenant_id=tenant_id
            )
            await _record_run(db, document_id, usage, None, applied=False, outcome="z_report")
            reply = REPLY_Z_REPORT
        else:
            await db.set_document_status(
                document_id, DocumentStatus.FAILED, Classification.OTHER, tenant_id=tenant_id
            )
            await _record_run(db, document_id, usage, None, applied=False, outcome="not_invoice")
            reply = REPLY_NOT_INVOICE
    except Exception:
        if attempts >= RETRY_LIMIT:
            await db.set_document_status(document_id, DocumentStatus.FAILED, tenant_id=tenant_id)
            if from_phone:
                await _reply(
                    db, wa, from_phone, REPLY_EXTRACTION_FAILED, photo=doc["wa_message_id"]
                )
        raise

    if from_phone:
        started = time.monotonic()
        if reply_owed:
            await _send_owed_reply(db, wa, document_id)
        else:
            await _reply(db, wa, from_phone, reply, photo=doc["wa_message_id"])
        stage_ms["reply"] = int((time.monotonic() - started) * 1000)
        logger.info("latency stage=reply document=%s elapsed_ms=%d", document_id, stage_ms["reply"])

    # WP-41 summary: forward-to-reply from the DB receipt timestamps plus the
    # in-process stage timers - the one grep that proves the ~20 s target.
    # ingest approximates webhook receipt -> document row (queue wait + media
    # download); the download/store stages above carry the precise splits.
    if msg is not None:
        now = datetime.datetime.now(datetime.UTC)
        stage_ms["ingest"] = max(
            int((doc["created_at"] - msg["created_at"]).total_seconds() * 1000), 0
        )
        logger.info(
            "latency document=%s webhook_to_reply_ms=%d "
            "stages=ingest:%d,extract:%d,repair:%d,persist:%d,reply:%d",
            document_id,
            int((now - msg["created_at"]).total_seconds() * 1000),
            stage_ms["ingest"],
            stage_ms.get("extract", 0),
            stage_ms.get("repair", 0),
            stage_ms.get("persist", 0),
            stage_ms.get("reply", 0),
        )


async def _persist_extracted(
    db: Database,
    provider: ExtractionProvider,
    doc: asyncpg.Record,
    image: bytes,
    extracted: ExtractedInvoice,
    extract_usage: ProviderUsage,
    stage_ms: dict[str, int] | None = None,
    *,
    from_phone: str | None = None,
) -> str:
    """Layers 2-4, then persistence: validate, one scoped repair round when
    anything failed, supplier memory + price alerts, then draft invoice +
    lines + document transition in one transaction. Money stays Decimal end
    to end (C4). Returns the composed extraction reply. `stage_ms` (WP-41)
    collects repair/persist elapsed ms for the caller's summary line.

    With a `from_phone`, the reply is also written as owed in the same
    transaction as the invoice, and the caller sends it through
    `_send_owed_reply`, so a send WhatsApp refuses is made by the retry."""
    if stage_ms is None:
        stage_ms = {}
    # The model copies printed facts (C3); the derivations from them - ISO
    # currency code, cash-or-credit from the printed terms - happen once, at
    # this seam, so the invoice row, price alerts, the cash hold and the reply
    # all agree.
    extracted = normalize_extracted(extracted)
    validation = validate_invoice(extracted)
    outcome = await repair_invoice(provider, image, doc["mime"], extracted, validation)
    invoice = outcome.invoice
    # Repair latency comes from the provider's own timing (0 = no repair ran).
    stage_ms["repair"] = outcome.usage.latency_ms if outcome.usage is not None else 0
    logger.info("latency stage=repair document=%s elapsed_ms=%d", doc["id"], stage_ms["repair"])

    # Supplier memory (plan.md §5 layer 4, WP-22): match the supplier for the
    # tenant and fetch its catalog for the filing step below. Never blocks
    # extraction - on any failure the draft persists unsnapped.
    supplier = None
    catalog: list[Row] | None = None
    try:
        suppliers = await db.list_suppliers(tenant_id=str(doc["tenant_id"]))
        supplier = match_supplier(suppliers, invoice.supplier_name)
        if supplier is not None:
            catalog = await db.list_supplier_items(str(supplier["id"]))
    except Exception:
        logger.exception(
            "supplier matching failed for document %s; persisting unsnapped", doc["id"]
        )
        supplier, catalog = None, None

    # WP-28: the tenant's own currency decides two things at once - whether
    # the reply asks about this invoice's currency, and whether comparing its
    # prices to a baseline means anything at all.
    tenant_currency = await db.tenant_currency(str(doc["tenant_id"]))
    # Filing (extraction/filing.py, CONTEXT.md): snap, fold, alerts, derived
    # confidence and the line rows - the one step this door shares with the
    # correction door and the typed path. The composer sees exactly what
    # persists, snapped flags included.
    filed = file_invoice(invoice, catalog=catalog, tenant_currency=tenant_currency)
    validation, snapped_items, alerts = filed.validation, filed.snapped_items, filed.alerts
    # C8: where each value came from. Everything starts as read off the image,
    # then the fields the scoped repair round actually moved are re-stamped -
    # diffed rather than self-reported, because a repair asked for three cells
    # routinely hands back two of them unchanged, and only the one that moved
    # was re-read to any effect.
    now = datetime.datetime.now(datetime.UTC)
    actor = f"model:{extract_usage.model_id}"
    provenance = initial(extracted, origin=Origin.EXTRACTED, actor=actor, at=now)
    if outcome.applied:
        # The repair round's own model id, not the extract call's: they are the
        # same provider today, and attributing a re-read to the wrong model the
        # day that stops being true is exactly the silence C8 exists to close.
        repair_actor = f"model:{outcome.usage.model_id}" if outcome.usage else actor
        provenance = mark(
            provenance,
            changed_fields(extracted, invoice),
            origin=Origin.REPAIRED,
            actor=repair_actor,
            at=now,
        )
    # WP-44: the same paper sent twice is held, never double-counted. Checked
    # against every earlier header for the tenant; a failed check never blocks
    # extraction (same posture as supplier matching above).
    duplicate = similar = None
    try:
        headers = await db.list_invoice_headers_for_tenant(str(doc["tenant_id"]))
        duplicate, similar = find_duplicate(
            headers, str(supplier["id"]) if supplier is not None else None, invoice
        )
    except Exception:
        logger.exception("duplicate check failed for document %s; persisting unheld", doc["id"])

    # WP-24 (PRD §21): a cash invoice is held for the owner's approval and
    # cannot confirm from chat; everything else goes straight to awaiting the
    # "OK" the reply asks for (C1 permits draft -> awaiting_confirm, and the
    # insert takes the post-transition status directly). A duplicate hold
    # (WP-44) outranks both: alerts and questions on a copy are noise.
    if duplicate is not None:
        status = InvoiceStatus.NEEDS_REVIEW
        reply = compose_duplicate_hold_reply(
            duplicate["supplier_name"],
            duplicate["invoice_no"],
            duplicate["currency"],
            duplicate["total"],
            duplicate["created_at"].date(),
        )
    else:
        # WP-87: which supplier's price history this paper moves, said out
        # loud when it is not the name printed on the paper - the one moment
        # before confirm where a wrong booking is still one keystroke to fix.
        # A duplicate hold skips it on purpose: that reply is about a copy
        # nobody is going to record, and a filing note on it is noise. Both
        # notes are the composer's inputs, so the closing stays last.
        booked_under = None
        if supplier is not None:
            booked_under = filed_under(invoice.supplier_name, supplier["name"])
        similar_to = None
        if similar is not None:
            similar_to = SimilarPaper(
                supplier_name=similar["supplier_name"],
                invoice_no=similar["invoice_no"],
                received_on=similar["created_at"].date(),
            )
        if invoice.payment_kind == "cash":
            status = InvoiceStatus.NEEDS_REVIEW
            compose = compose_cash_hold_reply
        else:
            status = InvoiceStatus.AWAITING_CONFIRM
            compose = compose_invoice_reply
        reply = compose(
            invoice,
            validation,
            alerts,
            tenant_currency=tenant_currency,
            booked_under=booked_under,
            similar_to=similar_to,
            item_names=filed_names(snapped_items),
        )

    started = time.monotonic()
    await db.insert_draft_invoice(
        tenant_id=str(doc["tenant_id"]),
        branch_id=str(doc["branch_id"]) if doc["branch_id"] else None,
        document_id=str(doc["id"]),
        supplier_id=str(supplier["id"]) if supplier is not None else None,
        supplier_name=invoice.supplier_name,
        invoice_no=invoice.invoice_no,
        invoice_date=invoice.invoice_date,
        currency=invoice.currency or DEFAULT_CURRENCY,
        subtotal=invoice.subtotal,
        tax=invoice.tax,
        total=invoice.total,
        payment_kind=invoice.payment_kind,
        # Derived by C4 from the arithmetic, not read off the document. Money
        # itself stays exactly as printed; these say how to read it, and the
        # confirm path uses them to record price memory net of VAT.
        tax_treatment=validation.document.tax_treatment,
        vat_rate=validation.document.vat_rate,
        discount_total=invoice.discount_total,
        rounding_amount=invoice.rounding_amount,
        status=status,
        confidence=filed.confidence,
        provenance=provenance,
        lines=filed.rows,
        # The hold, recorded rather than spent on the reply and forgotten. It is
        # what lets the review screen name the paper this one copies, and what
        # the dismiss door keys on - so the original, which carries none, can
        # never be dismissed.
        duplicate_of_invoice_id=str(duplicate["id"]) if duplicate is not None else None,
        owed_reply=(
            OwedReply(from_phone, reply, doc["wa_message_id"]) if from_phone is not None else None
        ),
    )
    await _record_run(
        db,
        str(doc["id"]),
        extract_usage,
        outcome.usage,
        applied=outcome.applied,
        outcome="extracted",
    )
    stage_ms["persist"] = int((time.monotonic() - started) * 1000)
    logger.info("latency stage=persist document=%s elapsed_ms=%d", doc["id"], stage_ms["persist"])
    return reply


def find_duplicate(
    existing: list[Row], supplier_id: str | None, invoice: ExtractedInvoice
) -> tuple[Row | None, Row | None]:
    """WP-44: is this paper already recorded? Pure, so the rule is testable
    without a database.

    Returns (duplicate, similar), each the newest matching header or None.
    Within the same supplier: number + total both matching is a *duplicate*
    (held); the number alone, or the invoice date + total, is merely
    *similar* (noted). All comparisons need both sides present - an absent
    number never equals another absent number (normalize_invoice_no), and a
    null total matches nothing. Totals compare only within one currency:
    USD 745.76 and AED 745.76 are the same digits, not the same money
    (found at integration by WP-28's own test), so a cross-currency pair
    can reach *similar* through its number but never a hold through its
    total.

    Same supplier means matched ids when both rows have one, else equal
    normalized names - a supplier the catalog does not know yet can still
    send the same paper twice."""
    number = normalize_invoice_no(invoice.invoice_no)
    duplicate: Row | None = None
    similar: Row | None = None
    for row in existing:  # newest first, per the query - first hit wins
        if not _same_supplier(row, supplier_id, invoice.supplier_name):
            continue
        number_match = number is not None and normalize_invoice_no(row["invoice_no"]) == number
        total_match = (
            invoice.total is not None
            and row["total"] == invoice.total
            and _same_money(invoice.currency, row["currency"])
        )
        date_match = (
            invoice.invoice_date is not None and row["invoice_date"] == invoice.invoice_date
        )
        if number_match and total_match:
            duplicate = duplicate or row
        elif number_match or (date_match and total_match):
            similar = similar or row
    return duplicate, similar


def _same_money(invoice_currency: str | None, row_currency: str | None) -> bool:
    """Two totals are comparable only in one currency. A side with no
    currency at all stays comparable - an unreadable currency must not
    disable the hold outright."""
    if invoice_currency is None or row_currency is None:
        return True
    return invoice_currency == row_currency


def _same_supplier(row: Row, supplier_id: str | None, supplier_name: str | None) -> bool:
    if supplier_id is not None and row["supplier_id"] is not None:
        return str(row["supplier_id"]) == supplier_id
    # One definition of "the same name" for the whole product (matching.same_name):
    # equal after normalization, and never two empty names.
    return same_name(row["supplier_name"], supplier_name)


async def _record_run(
    db: Database,
    document_id: str,
    extract_usage: ProviderUsage,
    repair_usage: ProviderUsage | None,
    *,
    applied: bool,
    outcome: str,
) -> None:
    """Run metadata (plan.md §5 layer 1): tokens and latency summed across
    the extract and repair calls."""
    input_tokens = extract_usage.input_tokens
    output_tokens = extract_usage.output_tokens
    latency_ms = extract_usage.latency_ms
    if repair_usage is not None:
        input_tokens += repair_usage.input_tokens
        output_tokens += repair_usage.output_tokens
        latency_ms += repair_usage.latency_ms
    await db.insert_extraction_run(
        document_id,
        model_id=extract_usage.model_id,
        prompt_version=extract_usage.prompt_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        repair_applied=applied,
        outcome=outcome,
    )


async def _reply(
    db: Database, wa: WhatsAppClient, to_phone: str, body: str, *, photo: str | None
) -> None:
    """Every reply the pipeline sends is about one paper, so it is sent as a
    quoted reply to that paper's photo (WP-125)."""
    out_id = await wa.send_text(to_phone, body, reply_to=photo)
    await db.record_outbound_message(out_id, to_phone, body, reply_to=photo)


async def _send_owed_reply(db: Database, wa: WhatsAppClient, document_id: str) -> None:
    """Send the summary still owed for a paper, if one is, and record it as
    sent. A refusal raises and leaves it owed for the next attempt. If
    WhatsApp accepts and the record write then fails, the retry sends it once
    more - a repeated summary is the better failure than a lost one, the same
    trade the morning brief makes (C15.3)."""
    owed = await db.get_owed_reply(document_id)
    if owed is None:
        return
    body = owed["payload"]["text"]
    photo = (owed["payload"].get("context") or {}).get("message_id")
    out_id = await wa.send_text(owed["to_phone"], body, reply_to=photo)
    await db.settle_owed_reply(document_id, out_id)
