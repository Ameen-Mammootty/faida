"""Pipeline orchestration for the `extract_document` job (plan.md §5, WP-13).

Wires the pure modules together: fetch the stored original, one structured
extract call (layer 1), deterministic validation (layer 2), the scoped repair
round (layer 3), supplier matching + item snapping + price alerts (layer 4,
WP-22/WP-23), then persistence, the C1 document transitions, and one reply
from the WP-20 composer (replies.py). Cash invoices are held as needs_review
(WP-24); layer 4's baseline update runs on confirm only
(Database.record_confirmed_prices).
"""

import logging

import asyncpg

from ..contracts import DocumentStatus, InvoiceStatus
from ..db import RETRY_LIMIT, Database
from ..matching import Row, match_supplier, snap_item
from ..replies import (
    DEFAULT_CURRENCY,
    REPLY_EXTRACTION_FAILED,
    REPLY_NOT_INVOICE,
    REPLY_Z_REPORT,
    PriceAlert,
    compose_cash_hold_reply,
    compose_invoice_reply,
)
from ..storage import Storage
from ..wa import WhatsAppClient
from .constants import PRICE_ALERT_MIN_ABS, PRICE_ALERT_MIN_PCT
from .provider import ExtractionProvider, ProviderUsage
from .repair import repair_invoice
from .schema import Classification, ExtractedInvoice
from .validate import validate_invoice

logger = logging.getLogger(__name__)


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
                await _reply(db, wa, from_phone, REPLY_EXTRACTION_FAILED)
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
    """Layers 2-4, then persistence: validate, one scoped repair round when
    anything failed, supplier memory + price alerts, then draft invoice +
    lines + document transition in one transaction. Money stays Decimal end
    to end (C4). Returns the composed extraction reply."""
    validation = validate_invoice(extracted)
    outcome = await repair_invoice(provider, image, doc["mime"], extracted, validation)
    invoice, validation = outcome.invoice, outcome.validation

    # Supplier memory (plan.md §5 layer 4, WP-22): match the supplier for the
    # tenant, then fuzzy-snap each line against that supplier's catalog. Never
    # blocks extraction - on any failure the draft persists unsnapped.
    supplier = None
    snapped_items: list[Row | None] = [None] * len(invoice.lines)
    try:
        suppliers = await db.list_suppliers(str(doc["tenant_id"]))
        supplier = match_supplier(suppliers, invoice.supplier_name)
        if supplier is not None:
            items = await db.list_supplier_items(str(supplier["id"]))
            snapped_items = [snap_item(items, line.raw_name) for line in invoice.lines]
    except Exception:
        logger.exception(
            "supplier matching failed for document %s; persisting unsnapped", doc["id"]
        )
        supplier, snapped_items = None, [None] * len(invoice.lines)

    # With a matched supplier every line carries snapped True/False in its
    # persisted check; without one snapping never ran, so None stays (neutral
    # per validate.py). Statuses are NOT recomputed: in M1 an unsnapped line
    # keeps its green arithmetic - the catalog is empty on day one, unknown
    # items are normal (they self-build on confirm).
    line_checks = validation.lines
    if supplier is not None:
        line_checks = [
            check.model_copy(update={"snapped": item is not None})
            for check, item in zip(line_checks, snapped_items, strict=True)
        ]
        # The composer sees exactly what persists, snapped flags included.
        validation = validation.model_copy(update={"lines": line_checks})

    alerts = _price_alerts(invoice, snapped_items)

    # Derived confidence, never self-reported (plan.md §5 layer 5): the
    # document-level check plus the per-line green/amber statuses.
    confidence = {
        "document": validation.document.model_dump(mode="json"),
        "lines": [check.status.value for check in line_checks],
    }
    lines = [
        {
            "position": index,
            "raw_name": line.raw_name,
            "supplier_item_id": str(item["id"]) if item is not None else None,
            "qty": line.qty,
            "unit": line.unit,
            "unit_price": line.unit_price,
            "line_total": line.line_total,
            "pack_size": line.pack_size,
            "checks": check.model_dump(mode="json"),
        }
        for index, (line, check, item) in enumerate(
            zip(invoice.lines, line_checks, snapped_items, strict=True)
        )
    ]

    # WP-24 (PRD §21): a cash invoice is held for the owner's approval and
    # cannot confirm from chat; everything else goes straight to awaiting the
    # "OK" the reply asks for (C1 permits draft -> awaiting_confirm, and the
    # insert takes the post-transition status directly).
    if invoice.payment_kind == "cash":
        status = InvoiceStatus.NEEDS_REVIEW
        reply = compose_cash_hold_reply(invoice, validation, alerts)
    else:
        status = InvoiceStatus.AWAITING_CONFIRM
        reply = compose_invoice_reply(invoice, validation, alerts)

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
        status=status,
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
    return reply


def _price_alerts(invoice: ExtractedInvoice, snapped_items: list[Row | None]) -> list[PriceAlert]:
    """WP-23 (plan.md §6 M2, the demo's money moment): one alert per snapped
    line whose extracted unit_price moved from the item's last_price by both
    >= PRICE_ALERT_MIN_ABS and >= PRICE_ALERT_MIN_PCT of it - either
    direction, falling prices are signal too. Ordered by absolute delta
    descending. The baseline itself moves only on confirm
    (Database.record_confirmed_prices), never here."""
    alerts: list[PriceAlert] = []
    for line, item in zip(invoice.lines, snapped_items, strict=True):
        if item is None or line.unit_price is None or item["last_price"] is None:
            continue
        last = item["last_price"]
        delta = abs(line.unit_price - last)
        if delta >= PRICE_ALERT_MIN_ABS and delta >= PRICE_ALERT_MIN_PCT * last:
            alerts.append(
                PriceAlert(
                    item_name=item["canonical_name"],
                    prev_price=last,
                    new_price=line.unit_price,
                    currency=invoice.currency or DEFAULT_CURRENCY,
                )
            )
    alerts.sort(key=lambda alert: alert.delta, reverse=True)
    return alerts


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
