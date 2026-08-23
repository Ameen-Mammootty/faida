"""WP-30: the C6 web API surface (plan.md §6 M3, §7.2) - the JSON backend the
review screen (WP-31) consumes.

Routes, all under /api and all requiring `Authorization: Bearer <api_token>`:

    GET   /api/invoices                       list, newest first, optional filters
    GET   /api/invoices/{id}                  full detail + signed image URL
    PATCH /api/invoices/{id}/fields           apply corrections, re-validate
    POST  /api/invoices/{id}/confirm          confirm (awaiting_confirm or needs_review)
    POST  /api/documents                      manual upload -> extract job
    GET   /api/supplier-items/{id}/prices     price history for the sparkline

Access control is the C6 demo scheme: one shared-secret bearer token
(settings.api_token) compared in constant time. An empty setting refuses every
request - fail closed, exactly like the webhook app secret. Real auth is M6.

Money is serialized as strings ("745.76"), never floats: every amount is
Decimal in Python and numeric in Postgres (C4), and a float round-trip could
corrupt the very digits the review screen exists to verify. The same goes for
quantities ("12.000"). WP-31 must treat them as decimal strings.

Corrections reuse the WP-21 chat machinery (confirm.py): the same field set,
the same unsigned-number rule, the same re-validate + re-snap application -
one implementation of "fix a field", whether it arrives by chat or by screen.
"""

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
    TotalsEdit,
    _apply_correction,
    _parse_number,
)
from .contracts import InvoiceStatus, JobKind
from .db import Database

logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_MIMES = {"image/jpeg", "image/png", "application/pdf"}
UPLOAD_MAX_BYTES = 10 * 1024 * 1024

_LINE_FIELDS = {"qty", "unit_price", "line_total", "name"}
_HEADER_FIELDS = {"subtotal", "tax", "total"}

# The invoice states the review screen may edit or confirm: awaiting_confirm
# (the normal path) and needs_review (cash holds - the review screen IS the
# cash approval path until M6, plan.md §6 M2).
_EDITABLE_STATUSES = {InvoiceStatus.AWAITING_CONFIRM, InvoiceStatus.NEEDS_REVIEW}


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
    field: Literal["qty", "unit_price", "line_total", "name", "subtotal", "tax", "total"]
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
        if isinstance(edit, LineFieldEdit | LineNameEdit) and edit.line_index >= line_count:
            raise HTTPException(
                status_code=422,
                detail=f"line_index {edit.line_index} out of range: "
                f"this invoice has {line_count} lines",
            )

    # The chat reply string is composed but unused: the screen gets the
    # re-validated detail payload instead.
    await _apply_correction(db, str(invoice_id), edits)
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
    approval path until M6 (plan.md §6 M2)."""
    db: Database = request.app.state.db
    invoice = await db.get_invoice(str(invoice_id))
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")

    if invoice["status"] == InvoiceStatus.AWAITING_CONFIRM:
        confirmed = await db.confirm_invoice(str(invoice_id))
    elif invoice["status"] == InvoiceStatus.NEEDS_REVIEW:
        confirmed = await db.confirm_reviewed_invoice(str(invoice_id))
    else:
        confirmed = False
    if not confirmed:
        # Already confirmed, still a draft, or lost a race to another confirm.
        raise HTTPException(
            status_code=409, detail=f"invoice is {invoice['status']}; cannot confirm"
        )

    await db.record_confirmed_prices(str(invoice_id))
    return await _invoice_detail(request, str(invoice_id))


# --- documents (manual upload) ----------------------------------------------


@router.post("/documents", status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile,
    branch_id: Annotated[str | None, Form()] = None,
) -> dict:
    """C6 manual upload - the vision-outage fallback's entry point (WP-34):
    store the immutable original exactly like the WhatsApp path and enqueue
    the same extract job. Tenant is the seeded default until M6 auth."""
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
