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

from ..contracts import DocumentStatus, InvoiceStatus
from ..db import RETRY_LIMIT, Database
from ..matching import Row, match_supplier, normalize, normalize_invoice_no, snap_item
from ..provenance import Origin, changed_fields, initial, mark
from ..replies import (
    DEFAULT_CURRENCY,
    REPLY_EXTRACTION_FAILED,
    REPLY_NOT_INVOICE,
    REPLY_Z_REPORT,
    PriceAlert,
    compose_cash_hold_reply,
    compose_duplicate_hold_reply,
    compose_invoice_reply,
    render_duplicate_note,
)
from ..storage import Storage
from ..wa import WhatsAppClient
from .constants import PRICE_ALERT_MIN_ABS, PRICE_ALERT_MIN_PCT
from .currency import currency_differs
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
    the user is never left hanging (plan.md §5 layer 6)."""
    document_id = payload["document_id"]
    doc = await db.get_document(document_id)
    if doc is None:
        logger.warning("extract job for unknown document %s", document_id)
        return
    if await db.get_invoice_by_document(document_id) is not None:
        return  # a previous attempt completed; invoices_document_uidx is the hard guard

    # WhatsApp documents reply to their sender; upload/manual (M3) have none.
    # The inbound message row also carries the webhook receipt time the WP-41
    # summary line measures from.
    msg = await db.get_inbound_message(doc["wa_message_id"]) if doc["wa_message_id"] else None
    from_phone = msg["from_phone"] if msg else None
    await db.set_document_status(document_id, DocumentStatus.PROCESSING)

    # WP-41: per-stage elapsed ms, provider stages taken from the usage the
    # provider already timed (never re-timed here).
    stage_ms: dict[str, int] = {}
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
                db, provider, doc, image, result.invoice, usage, stage_ms
            )
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
        started = time.monotonic()
        await _reply(db, wa, from_phone, reply)
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
) -> str:
    """Layers 2-4, then persistence: validate, one scoped repair round when
    anything failed, supplier memory + price alerts, then draft invoice +
    lines + document transition in one transaction. Money stays Decimal end
    to end (C4). Returns the composed extraction reply. `stage_ms` (WP-41)
    collects repair/persist elapsed ms for the caller's summary line."""
    if stage_ms is None:
        stage_ms = {}
    # The model copies printed facts (C3); the derivations from them - ISO
    # currency code, cash-or-credit from the printed terms - happen once, at
    # this seam, so the invoice row, price alerts, the cash hold and the reply
    # all agree.
    extracted = normalize_extracted(extracted)
    validation = validate_invoice(extracted)
    outcome = await repair_invoice(provider, image, doc["mime"], extracted, validation)
    invoice, validation = outcome.invoice, outcome.validation
    # Repair latency comes from the provider's own timing (0 = no repair ran).
    stage_ms["repair"] = outcome.usage.latency_ms if outcome.usage is not None else 0
    logger.info("latency stage=repair document=%s elapsed_ms=%d", doc["id"], stage_ms["repair"])

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

    # WP-28: the tenant's own currency decides two things at once - whether
    # the reply asks about this invoice's currency, and whether comparing its
    # prices to a baseline means anything at all.
    tenant_currency = await db.tenant_currency(str(doc["tenant_id"]))
    alerts = price_alerts(invoice, snapped_items, tenant_currency=tenant_currency)

    # Derived confidence, never self-reported (plan.md §5 layer 5): the
    # document-level check plus the per-line green/amber statuses.
    confidence = {
        "document": validation.document.model_dump(mode="json"),
        "lines": [check.status.value for check in line_checks],
    }
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
    lines = [
        {
            "position": index,
            "raw_name": line.raw_name,
            "line_kind": line.line_kind.value,
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
        if invoice.payment_kind == "cash":
            status = InvoiceStatus.NEEDS_REVIEW
            reply = compose_cash_hold_reply(
                invoice, validation, alerts, tenant_currency=tenant_currency
            )
        else:
            status = InvoiceStatus.AWAITING_CONFIRM
            reply = compose_invoice_reply(
                invoice, validation, alerts, tenant_currency=tenant_currency
            )
        if similar is not None:
            note = render_duplicate_note(
                similar["supplier_name"], similar["invoice_no"], similar["created_at"].date()
            )
            reply = f"{reply}\n{note}"

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
        confidence=confidence,
        provenance=provenance,
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
    if supplier_name and row["supplier_name"]:
        return normalize(row["supplier_name"]) == normalize(supplier_name)
    return False


def price_alerts(
    invoice: ExtractedInvoice,
    snapped_items: list[Row | None],
    *,
    tenant_currency: str | None = None,
) -> list[PriceAlert]:
    """WP-23 (plan.md §6 M2, the demo's money moment): one alert per snapped
    line whose extracted unit_price moved from the item's last_price by both
    >= PRICE_ALERT_MIN_ABS and >= PRICE_ALERT_MIN_PCT of it - either
    direction, falling prices are signal too. Ordered by absolute delta
    descending. The baseline itself moves only on confirm
    (Database.record_confirmed_prices), never here.

    WP-28: an invoice billed in another currency raises no alerts at all.
    The baseline is a bare number in the tenant's money, so "USD 75 against a
    baseline of AED 50" is not a price rise, it is two different questions
    subtracted from each other - and this is the one message the demo asks to
    be trusted on."""
    if currency_differs(invoice.currency, tenant_currency):
        return []
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


async def _reply(db: Database, wa: WhatsAppClient, to_phone: str, body: str) -> None:
    out_id = await wa.send_text(to_phone, body)
    await db.record_outbound_message(out_id, to_phone, body)
