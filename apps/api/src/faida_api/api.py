"""WP-30: the C6 web API surface (plan.md §6 M3, §7.2) - the JSON backend the
review screen (WP-31) consumes.

Routes, all under /api and all requiring `Authorization: Bearer <api_token>`:

    GET   /api/invoices                       list, newest first, optional filters
    GET   /api/invoices/{id}                  full detail + signed image URL
    POST  /api/invoices/manual                typed-in invoice, no AI (WP-34)
    PATCH /api/invoices/{id}/fields           apply corrections, re-validate
    POST  /api/invoices/{id}/confirm          confirm (awaiting_confirm or needs_review)
    POST  /api/documents                      manual upload -> extract job
    GET   /api/supplier-items/{id}/prices     price history for the sparkline

POST /api/invoices/manual is the sanctioned WP-34 extension of C6: the
vision-outage fallback's typed path. Body:

    {branch_id?, supplier_name?, invoice_no?, invoice_date?, currency?,
     payment_kind?, subtotal?, tax?, total?,
     lines: [{raw_name, qty?, unit?, pack_size?, unit_price?, line_total?}]}

Money and quantities arrive as unsigned decimal strings (the PATCH
convention); dates as ISO "YYYY-MM-DD". The server builds the C3 invoice
shape, runs the same deterministic validation and supplier snapping the
pipeline runs, and persists through the same helper - no AI anywhere, so
this path survives a revoked Anthropic key (plan.md §6 M3 done-when).
Returns 201 with the standard detail payload.

Access control is the C6 demo scheme: one shared-secret bearer token
(settings.api_token) compared in constant time. An empty setting refuses every
request - fail closed, exactly like the webhook app secret. Real auth is M7.

Money is serialized as strings ("745.76"), never floats: every amount is
Decimal in Python and numeric in Postgres (C4), and a float round-trip could
corrupt the very digits the review screen exists to verify. The same goes for
quantities ("12.000"). WP-31 must treat them as decimal strings.

Corrections reuse the WP-21 chat machinery (confirm.py): the same field set,
the same unsigned-number rule, the same re-validate + re-snap application -
one implementation of "fix a field", whether it arrives by chat or by screen.
"""

import datetime
import hashlib
import hmac
import logging
import uuid
from decimal import Decimal
from typing import Annotated, Literal

import asyncpg
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from .confirm import (
    Edit,
    LineFieldEdit,
    LineNameEdit,
    LinePackSizeEdit,
    TotalsEdit,
    _apply_correction,
    _parse_number,
)
from .contracts import InvoiceStatus, JobKind
from .db import Database
from .extraction.normalize import blank_to_none, normalize_extracted
from .extraction.schema import ExtractedInvoice, ExtractedLine
from .extraction.validate import validate_invoice
from .matching import Row, match_supplier, snap_item
from .provenance import Origin, initial
from .replies import DEFAULT_CURRENCY

logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_MIMES = {"image/jpeg", "image/png", "application/pdf"}
UPLOAD_MAX_BYTES = 10 * 1024 * 1024

_LINE_FIELDS = {"qty", "unit_price", "line_total", "name", "pack_size"}
_HEADER_FIELDS = {"subtotal", "tax", "total"}

# The invoice states the review screen may edit or confirm: awaiting_confirm
# (the normal path) and needs_review (cash holds - the review screen IS the
# cash approval path until M7, plan.md §6 M2).
_EDITABLE_STATUSES = {InvoiceStatus.AWAITING_CONFIRM, InvoiceStatus.NEEDS_REVIEW}


#: C8 actor for the review screen. The demo API is one shared bearer token, so
#: there is no person to name yet - "console" is the honest answer, and it
#: becomes a real user id when M7 brings Supabase Auth. Deliberately not taken
#: from a client-supplied header: a name anyone holding the token can choose
#: looks like identity without being it, which is worse than admitting we do
#: not know yet.
CONSOLE_ACTOR = "console"


def require_api_token(request: Request) -> None:
    """C6 demo auth: one shared-secret bearer token. No configured token means
    no access at all - misconfiguration must fail loudly, never open."""
    expected = request.app.state.settings.api_token
    header = request.headers.get("Authorization") or ""
    provided = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
    if not expected or not provided:
        raise HTTPException(status_code=401, detail="unauthorized")
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="unauthorized")


router = APIRouter(prefix="/api", dependencies=[Depends(require_api_token)])


# --- request bodies ---------------------------------------------------------


class Correction(BaseModel):
    """One field fix: line_index (0-based) targets a line field, null targets
    the totals block. The field set is exactly what the chat grammar accepts
    (confirm.py); values arrive as strings - numbers as unsigned decimals."""

    model_config = ConfigDict(extra="forbid")

    line_index: int | None = None
    field: Literal[
        "qty", "unit_price", "line_total", "name", "pack_size", "subtotal", "tax", "total"
    ]
    value: str


class FieldCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corrections: list[Correction] = Field(min_length=1)


# --- serialization (money as strings, never floats) -------------------------


def _dec(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _iso(value) -> str | None:
    return None if value is None else value.isoformat()


def _invoice_summary(row: asyncpg.Record) -> dict:
    return {
        "id": str(row["id"]),
        "supplier_name": row["supplier_name"],
        "supplier_id": _maybe_str(row["supplier_id"]),
        "invoice_no": row["invoice_no"],
        "invoice_date": _iso(row["invoice_date"]),
        "currency": row["currency"],
        "total": _dec(row["total"]),
        "status": row["status"],
        "created_at": _iso(row["created_at"]),
        "branch_id": _maybe_str(row["branch_id"]),
        "branch_name": row["branch_name"],
        "document_id": str(row["document_id"]),
    }


def _maybe_str(value) -> str | None:
    return None if value is None else str(value)


async def _invoice_detail(request: Request, invoice_id: str) -> dict:
    """The C6 detail payload: header fields, per-line fields, checks,
    confidence, the document, and a short-lived signed image URL (null when
    the document has no stored original)."""
    db: Database = request.app.state.db
    invoice = await db.get_invoice(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    lines = await db.get_invoice_lines(invoice_id)
    document = await db.get_document(str(invoice["document_id"]))

    image_url = None
    if document is not None and document["storage_path"]:
        try:
            image_url = await request.app.state.storage.sign_url(document["storage_path"])
        except Exception:
            # A broken sign call must not sink the whole detail: the screen
            # still shows every field, just without the photo.
            logger.exception("signing image URL failed for document %s", invoice["document_id"])

    return {
        **_invoice_summary(invoice),
        "subtotal": _dec(invoice["subtotal"]),
        "tax": _dec(invoice["tax"]),
        "payment_kind": invoice["payment_kind"],
        "confidence": invoice["confidence"],
        # C8, sanctioned C6 extension: where each field came from, so the
        # screen can show a reconstructed total as reconstructed.
        "provenance": invoice["provenance"],
        "confirmed_at": _iso(invoice["confirmed_at"]),
        "lines": [
            {
                "position": line["position"],
                "raw_name": line["raw_name"],
                "supplier_item_id": _maybe_str(line["supplier_item_id"]),
                "qty": _dec(line["qty"]),
                "unit": line["unit"],
                "pack_size": line["pack_size"],
                "unit_price": _dec(line["unit_price"]),
                "line_total": _dec(line["line_total"]),
                "checks": line["checks"],
            }
            for line in lines
        ],
        "document": None
        if document is None
        else {
            "id": str(document["id"]),
            "status": document["status"],
            "classification": document["classification"],
            "source": document["source"],
            "created_at": _iso(document["created_at"]),
        },
        "image_url": image_url,
    }


# --- invoices ---------------------------------------------------------------


@router.get("/invoices")
async def list_invoices(
    request: Request,
    branch_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
    status: InvoiceStatus | None = None,
) -> dict:
    db: Database = request.app.state.db
    rows = await db.list_invoices(
        branch_id=_maybe_str(branch_id),
        supplier_id=_maybe_str(supplier_id),
        status=None if status is None else status.value,
    )
    return {"invoices": [_invoice_summary(row) for row in rows]}


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: uuid.UUID, request: Request) -> dict:
    return await _invoice_detail(request, str(invoice_id))


@router.patch("/invoices/{invoice_id}/fields")
async def patch_invoice_fields(
    invoice_id: uuid.UUID, body: FieldCorrections, request: Request
) -> dict:
    """Apply field corrections through the WP-21 machinery: re-validate,
    re-snap, persist. Status never changes here - confirming is its own
    endpoint, exactly as in chat."""
    db: Database = request.app.state.db
    invoice = await db.get_invoice(str(invoice_id))
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    if invoice["status"] not in _EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"invoice is {invoice['status']}; only awaiting_confirm or "
            "needs_review invoices can be edited",
        )

    edits = [_to_edit(correction) for correction in body.corrections]
    line_count = len(await db.get_invoice_lines(str(invoice_id)))
    for edit in edits:
        if (
            isinstance(edit, LineFieldEdit | LineNameEdit | LinePackSizeEdit)
            and edit.line_index >= line_count
        ):
            raise HTTPException(
                status_code=422,
                detail=f"line_index {edit.line_index} out of range: "
                f"this invoice has {line_count} lines",
            )

    # The chat reply string is composed but unused: the screen gets the
    # re-validated detail payload instead.
    await _apply_correction(
        db,
        str(invoice_id),
        edits,
        actor=CONSOLE_ACTOR,
        origin=Origin.CORRECTED_SCREEN,
    )
    return await _invoice_detail(request, str(invoice_id))


def _to_edit(correction: Correction) -> Edit:
    """Map one C6 correction onto the confirm.py edit shapes, enforcing the
    same rules as the chat grammar (unsigned decimals, non-empty names)."""
    if correction.field in _HEADER_FIELDS:
        if correction.line_index is not None:
            raise HTTPException(
                status_code=422,
                detail=f"field '{correction.field}' is a header field; line_index must be null "
                "(line totals are field 'line_total')",
            )
        return TotalsEdit(field=correction.field, value=_number(correction))
    if correction.line_index is None or correction.line_index < 0:
        raise HTTPException(
            status_code=422,
            detail=f"field '{correction.field}' needs a line_index (0-based)",
        )
    if correction.field == "name":
        name = correction.value.strip()
        if not name:
            raise HTTPException(status_code=422, detail="a line name cannot be empty")
        return LineNameEdit(line_index=correction.line_index, name=name)
    if correction.field == "pack_size":
        # Blank clears it: "the pack we hold is wrong and I do not know the
        # right one" is a real answer, and the only honest one when a derived
        # pack is wrong. Same placeholder vocabulary the seam uses.
        return LinePackSizeEdit(
            line_index=correction.line_index, pack_size=blank_to_none(correction.value)
        )
    return LineFieldEdit(
        line_index=correction.line_index, field=correction.field, value=_number(correction)
    )


def _number(correction: Correction) -> Decimal:
    value = _parse_number(correction.value)
    if value is None:
        raise HTTPException(
            status_code=422,
            detail=f"'{correction.value}' is not a valid {correction.field}: "
            'send an unsigned decimal string like "16" or "4.50"',
        )
    return value


@router.post("/invoices/{invoice_id}/confirm")
async def confirm_invoice(invoice_id: uuid.UUID, request: Request) -> dict:
    """The chat "OK", from the screen: flip to confirmed (stamping
    confirmed_at) and move the price baseline. Allowed from awaiting_confirm
    and - unlike chat - from needs_review: the review screen is the cash
    approval path until M7 (plan.md §6 M2)."""
    db: Database = request.app.state.db
    invoice = await db.get_invoice(str(invoice_id))
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    if invoice["total"] is None:
        # WP-26, the same rule the chat "OK" obeys: an invoice with no total is
        # not recordable from any door. The screen can supply one - PATCH takes
        # 'total' - so this is a step, not a wall.
        raise HTTPException(
            status_code=409,
            detail="invoice has no total; set the total before confirming",
        )

    if invoice["status"] == InvoiceStatus.AWAITING_CONFIRM:
        confirmed = await db.confirm_invoice(str(invoice_id), actor=CONSOLE_ACTOR)
    elif invoice["status"] == InvoiceStatus.NEEDS_REVIEW:
        confirmed = await db.confirm_reviewed_invoice(str(invoice_id), actor=CONSOLE_ACTOR)
    else:
        confirmed = False
    if not confirmed:
        # Already confirmed, still a draft, or lost a race to another confirm.
        raise HTTPException(
            status_code=409, detail=f"invoice is {invoice['status']}; cannot confirm"
        )

    await db.record_confirmed_prices(str(invoice_id))
    return await _invoice_detail(request, str(invoice_id))


# --- manual entry (WP-34, sanctioned C6 extension) --------------------------


class ManualLine(BaseModel):
    """One typed line. Numbers are unsigned decimal strings (the PATCH
    convention); raw_name must be non-empty."""

    model_config = ConfigDict(extra="forbid")

    raw_name: str
    qty: str | None = None
    unit: str | None = None
    pack_size: str | None = None
    unit_price: str | None = None
    line_total: str | None = None


class ManualInvoice(BaseModel):
    """POST /api/invoices/manual body. Everything optional except at least
    one line - a torn cash receipt often has no invoice number and no printed
    subtotal, and the deterministic checks mark the gaps amber."""

    model_config = ConfigDict(extra="forbid")

    branch_id: str | None = None
    supplier_name: str | None = None
    invoice_no: str | None = None
    invoice_date: datetime.date | None = None
    currency: str | None = None
    payment_kind: Literal["credit", "cash"] | None = None
    subtotal: str | None = None
    tax: str | None = None
    total: str | None = None
    lines: list[ManualLine] = Field(min_length=1)


def _manual_number(value: str | None, field: str) -> Decimal | None:
    """The unsigned-decimal-string rule, shared with PATCH and chat."""
    if value is None:
        return None
    number = _parse_number(value)
    if number is None:
        raise HTTPException(
            status_code=422,
            detail=f"'{value}' is not a valid {field}: "
            'send an unsigned decimal string like "16" or "4.50"',
        )
    return number


def _clean(value: str | None) -> str | None:
    """Trim free-text fields; a blank string means the field was not given."""
    if value is None:
        return None
    return value.strip() or None


def _to_extracted_invoice(body: ManualInvoice) -> ExtractedInvoice:
    """Map the typed body onto the C3 schema, so validation (and every later
    correction) treats a manual invoice exactly like an extracted one."""
    lines: list[ExtractedLine] = []
    for index, line in enumerate(body.lines):
        raw_name = line.raw_name.strip()
        if not raw_name:
            raise HTTPException(status_code=422, detail="a line name cannot be empty")
        n = index + 1
        lines.append(
            ExtractedLine(
                raw_name=raw_name,
                qty=_manual_number(line.qty, f"line {n} qty"),
                unit=_clean(line.unit),
                pack_size=_clean(line.pack_size),
                unit_price=_manual_number(line.unit_price, f"line {n} unit_price"),
                line_total=_manual_number(line.line_total, f"line {n} line_total"),
            )
        )
    # Same seam the pipeline uses. A typed payment_kind is a human's decision
    # and passes through untouched (there are no printed terms to read); the
    # currency still normalizes, so "dirhams" typed by hand becomes AED too.
    return normalize_extracted(
        ExtractedInvoice(
            supplier_name=_clean(body.supplier_name),
            invoice_no=_clean(body.invoice_no),
            invoice_date=body.invoice_date,
            currency=_clean(body.currency),
            payment_kind=body.payment_kind,
            lines=lines,
            subtotal=_manual_number(body.subtotal, "subtotal"),
            tax=_manual_number(body.tax, "tax"),
            total=_manual_number(body.total, "total"),
        )
    )


@router.post("/invoices/manual", status_code=201)
async def create_manual_invoice(body: ManualInvoice, request: Request) -> dict:
    """WP-34's typed fallback: validate + snap + persist a typed invoice
    through the exact machinery the pipeline uses - plan.md §5 layers 2 and 4
    with layer 1 (the AI) absent, so this path survives a revoked Anthropic
    key. The document row is a stub anchor: source 'manual', no stored
    original, and no classification (no model looked at anything)."""
    db: Database = request.app.state.db
    tenant_id = await db.default_tenant_id()
    if tenant_id is None:
        raise HTTPException(status_code=500, detail="no tenant seeded; run supabase/seed.sql")
    if body.branch_id is not None:
        branch = await _get_branch(db, body.branch_id)
        if branch is None or str(branch["tenant_id"]) != tenant_id:
            raise HTTPException(status_code=422, detail=f"unknown branch_id '{body.branch_id}'")

    invoice = _to_extracted_invoice(body)
    validation = validate_invoice(invoice)

    # Supplier memory (plan.md §5 layer 4), the pipeline's convention: match
    # the supplier, snap each line, fold snapped flags into the checks without
    # recomputing status. Deterministic - no AI - and never blocking: on any
    # failure the invoice persists unsnapped.
    supplier = None
    snapped_items: list[Row | None] = [None] * len(invoice.lines)
    try:
        suppliers = await db.list_suppliers(tenant_id)
        supplier = match_supplier(suppliers, invoice.supplier_name)
        if supplier is not None:
            items = await db.list_supplier_items(str(supplier["id"]))
            snapped_items = [snap_item(items, line.raw_name) for line in invoice.lines]
    except Exception:
        logger.exception("supplier matching failed for a manual invoice; persisting unsnapped")
        supplier, snapped_items = None, [None] * len(invoice.lines)

    line_checks = validation.lines
    if supplier is not None:
        line_checks = [
            check.model_copy(update={"snapped": item is not None})
            for check, item in zip(line_checks, snapped_items, strict=True)
        ]

    # Derived confidence, never self-reported (plan.md §5 layer 5) - the same
    # dump the pipeline persists.
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

    # WP-24 (PRD §21) applies to typed invoices too: cash holds for approval.
    status = (
        InvoiceStatus.NEEDS_REVIEW
        if invoice.payment_kind == "cash"
        else InvoiceStatus.AWAITING_CONFIRM
    )

    document_id = await db.insert_manual_document(tenant_id, body.branch_id)
    invoice_id = await db.insert_draft_invoice(
        tenant_id=tenant_id,
        branch_id=body.branch_id,
        document_id=document_id,
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
        # C8: no model ran, so every value here was typed by a person - or
        # derived from what they typed by the same seam a photo goes through
        # (currency word to ISO code, printed terms to cash-or-credit, a pack
        # size read out of the item name). MANUAL is the honest origin for the
        # set: a person supplied the page these came from, and none of it was
        # read off a photo.
        provenance=initial(
            invoice,
            origin=Origin.MANUAL,
            actor=CONSOLE_ACTOR,
            at=datetime.datetime.now(datetime.UTC),
        ),
        lines=lines,
        document_classification=None,
        created_by=CONSOLE_ACTOR,
    )
    return await _invoice_detail(request, invoice_id)


# --- documents (manual upload) ----------------------------------------------


@router.post("/documents", status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile,
    branch_id: Annotated[str | None, Form()] = None,
) -> dict:
    """C6 manual upload - the vision-outage fallback's entry point (WP-34):
    store the immutable original exactly like the WhatsApp path and enqueue
    the same extract job. Tenant is the seeded default until M7 auth."""
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_UPLOAD_MIMES:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported file type '{mime}': send image/jpeg, image/png, "
            "or application/pdf",
        )
    data = await file.read(UPLOAD_MAX_BYTES + 1)
    if len(data) > UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=413, detail=f"file too large: the limit is {UPLOAD_MAX_BYTES} bytes"
        )
    if not data:
        raise HTTPException(status_code=422, detail="empty file")

    db: Database = request.app.state.db
    tenant_id = await db.default_tenant_id()
    if tenant_id is None:
        raise HTTPException(status_code=500, detail="no tenant seeded; run supabase/seed.sql")
    if branch_id is not None:
        branch = await _get_branch(db, branch_id)
        if branch is None or str(branch["tenant_id"]) != tenant_id:
            raise HTTPException(status_code=422, detail=f"unknown branch_id '{branch_id}'")

    sha256 = hashlib.sha256(data).hexdigest()
    document_id = await db.insert_uploaded_document(tenant_id, branch_id, mime, sha256)
    # The immutable path convention, shared with the WhatsApp ingest
    # (worker._ingest_media): never overwritten, never upserted.
    path = f"{tenant_id}/documents/{document_id}/original"
    await request.app.state.storage.put(path, data, mime)
    await db.set_document_storage_path(document_id, path)
    await db.enqueue(JobKind.EXTRACT_DOCUMENT, {"document_id": document_id})
    return {"document_id": document_id}


async def _get_branch(db: Database, branch_id: str) -> asyncpg.Record | None:
    try:
        uuid.UUID(branch_id)
    except ValueError:
        return None
    return await db.get_branch(branch_id)


# --- supplier item price history --------------------------------------------


@router.get("/supplier-items/{item_id}/prices")
async def supplier_item_prices(item_id: uuid.UUID, request: Request) -> dict:
    """The sparkline's data (WP-33): confirmed price observations oldest
    first, plus the item header."""
    db: Database = request.app.state.db
    item = await db.get_supplier_item(str(item_id))
    if item is None:
        raise HTTPException(status_code=404, detail="supplier item not found")
    rows = await db.list_item_prices(str(item_id))
    return {
        "id": str(item["id"]),
        "canonical_name": item["canonical_name"],
        "unit": item["unit"],
        "pack_size": item["pack_size"],
        "last_price": _dec(item["last_price"]),
        "prev_price": _dec(item["prev_price"]),
        "prices": [
            {
                "price": _dec(row["price"]),
                "observed_at": _iso(row["observed_at"]),
                "invoice_id": _maybe_str(row["invoice_id"]),
            }
            for row in rows
        ],
    }
