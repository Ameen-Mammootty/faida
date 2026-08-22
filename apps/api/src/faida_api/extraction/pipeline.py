"""Pipeline orchestration for the `extract_document` job (plan.md §5, WP-13).

Wires the pure modules together: fetch the stored original, one structured
extract call (layer 1), deterministic validation (layer 2), the scoped repair
round (layer 3), then persistence, the C1 document transitions, and one reply.
Replies here are plain M1 English constants; WP-20's composer replaces them
in M2. Layers 4-5 (supplier memory, amber questions) arrive in M2.
"""

import logging

import asyncpg

from ..contracts import DocumentStatus, InvoiceStatus
from ..db import RETRY_LIMIT, Database
from ..storage import Storage
from ..wa import WhatsAppClient
from .provider import ExtractionProvider, ProviderUsage
from .repair import repair_invoice
from .schema import Classification, ExtractedInvoice
from .validate import validate_invoice

logger = logging.getLogger(__name__)

# Plain M1 replies (English-only per plan.md §3); WP-20 owns the M2 templates.
REPLY_INVOICE_SUMMARY = "Read it: {supplier}, {line_count} {line_word}, total {currency} {total}."
REPLY_NOT_INVOICE = (
    "That doesn't look like a supplier invoice, so I'll leave it - forward an "
    "invoice photo and I'll read it."
)
REPLY_Z_REPORT = "I read supplier invoices for now - sales reports are coming soon."
# Plan.md §5 layer 6: the failure path is one message, never a dead end.
REPLY_FAILED = "Couldn't read this one - try a straighter photo, or type the total."


def build_provider(anthropic_api_key: str) -> ExtractionProvider | None:
    """Provider wiring for main.py: the Anthropic implementation when a key is
    configured (passed explicitly, no env magic), else None - extract jobs then
    raise and land in the failure path. The SDK import stays inside this
    package (C3)."""
    if not anthropic_api_key:
        return None
    import anthropic

    from .anthropic_provider import AnthropicExtractionProvider

    return AnthropicExtractionProvider(anthropic.AsyncAnthropic(api_key=anthropic_api_key))


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
    the user is never left hanging (plan.md §5 layer 6)."""
    document_id = payload["document_id"]
    doc = await db.get_document(document_id)
    if doc is None:
        logger.warning("extract job for unknown document %s", document_id)
        return
    if await db.get_invoice_by_document(document_id) is not None:
        return  # a previous attempt completed; retries must not duplicate

    from_phone = await _sender_phone(db, doc)
    await db.set_document_status(document_id, DocumentStatus.PROCESSING)

    try:
        if provider is None:
            raise RuntimeError("no extraction provider configured (anthropic_api_key is empty)")
        if not doc["storage_path"]:
            raise RuntimeError(f"document {document_id} has no stored original")
        image = await storage.get(doc["storage_path"])
        result, usage = await provider.extract(image, doc["mime"])

        if result.classification is Classification.INVOICE:
            if result.invoice is None:
                raise ValueError("provider returned classification 'invoice' with no invoice")
            reply = await _persist_extracted(db, provider, doc, image, result.invoice, usage)
        elif result.classification is Classification.Z_REPORT:
            await db.set_document_status(
                document_id, DocumentStatus.FAILED, Classification.Z_REPORT
            )
            await _record_run(db, document_id, usage, None, applied=False, outcome="z_report")
            reply = REPLY_Z_REPORT
        else:
            await db.set_document_status(document_id, DocumentStatus.FAILED, Classification.OTHER)
            await _record_run(db, document_id, usage, None, applied=False, outcome="not_invoice")
            reply = REPLY_NOT_INVOICE
    except Exception:
        if attempts >= RETRY_LIMIT:
            await db.set_document_status(document_id, DocumentStatus.FAILED)
            if from_phone:
                await _reply(db, wa, from_phone, REPLY_FAILED)
        raise

    if from_phone:
        await _reply(db, wa, from_phone, reply)


async def _persist_extracted(
    db: Database,
    provider: ExtractionProvider,
    doc: asyncpg.Record,
    image: bytes,
    extracted: ExtractedInvoice,
    extract_usage: ProviderUsage,
) -> str:
    """Layers 2-3, then persistence: validate, one scoped repair round when
    anything failed, then draft invoice + lines + document transition in one
    transaction. Money stays Decimal end to end (C4). Returns the summary."""
    validation = validate_invoice(extracted)
    outcome = await repair_invoice(provider, image, doc["mime"], extracted, validation)
    invoice, validation = outcome.invoice, outcome.validation

    # Derived confidence, never self-reported (plan.md §5 layer 5): the
    # document-level check plus the per-line green/amber statuses.
    confidence = {
        "document": validation.document.model_dump(mode="json"),
        "lines": [check.status.value for check in validation.lines],
    }
    lines = [
        {
            "position": index,
            "raw_name": line.raw_name,
            "qty": line.qty,
            "unit": line.unit,
            "unit_price": line.unit_price,
            "line_total": line.line_total,
            "pack_size": line.pack_size,
            "checks": check.model_dump(mode="json"),
        }
        for index, (line, check) in enumerate(zip(invoice.lines, validation.lines, strict=True))
    ]
    await db.insert_draft_invoice(
        tenant_id=str(doc["tenant_id"]),
        branch_id=str(doc["branch_id"]) if doc["branch_id"] else None,
        document_id=str(doc["id"]),
        invoice_no=invoice.invoice_no,
        invoice_date=invoice.invoice_date,
        currency=invoice.currency or "AED",
        subtotal=invoice.subtotal,
        tax=invoice.tax,
        total=invoice.total,
        payment_kind=invoice.payment_kind,
        status=InvoiceStatus.DRAFT,  # awaiting_confirm belongs to the M2 confirm flow
        confidence=confidence,
        lines=lines,
    )
    await _record_run(
        db,
        str(doc["id"]),
        extract_usage,
        outcome.usage,
        applied=outcome.applied,
        outcome="extracted",
    )
    return _summary_reply(invoice)


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


async def _sender_phone(db: Database, doc: asyncpg.Record) -> str | None:
    """WhatsApp documents reply to their sender; upload/manual (M3) have none."""
    if not doc["wa_message_id"]:
        return None
    msg = await db.get_inbound_message(doc["wa_message_id"])
    return msg["from_phone"] if msg else None


async def _reply(db: Database, wa: WhatsAppClient, to_phone: str, body: str) -> None:
    out_id = await wa.send_text(to_phone, body)
    await db.record_outbound_message(out_id, to_phone, body)


def _summary_reply(invoice: ExtractedInvoice) -> str:
    count = len(invoice.lines)
    total = f"{invoice.total:.2f}" if invoice.total is not None else "unreadable"
    return REPLY_INVOICE_SUMMARY.format(
        supplier=invoice.supplier_name or "supplier unknown",
        line_count=count,
        line_word="line" if count == 1 else "lines",
        currency=invoice.currency or "AED",
        total=total,
    )
