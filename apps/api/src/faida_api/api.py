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

from . import costing
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
from .extraction import units
from .extraction.currency import currency_differs
from .extraction.normalize import blank_to_none, normalize_extracted
from .extraction.schema import ExtractedInvoice, ExtractedLine
from .extraction.validate import validate_invoice
from .matching import Row, match_supplier, propose_ingredients, snap_item
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
        # WP-44's hold, so the screen can tell a held duplicate from a cash
        # hold - they are the same status. Present on both callers' rows:
        # list_invoices selects it, and get_invoice takes i.*.
        "duplicate_of_invoice_id": _maybe_str(row["duplicate_of_invoice_id"]),
    }


def _invoice_list_row(row: asyncpg.Record) -> dict:
    """The list payload: the summary plus the duplicated invoice's number,
    which arrives on the list query's own join.

    Deliberately NOT folded into `_invoice_summary`. That function is spread
    into the detail payload too, whose row comes from `get_invoice` and has no
    join on it - so a joined column added to the shared serializer raises
    KeyError on every detail request, taking out GET detail, confirm and manual
    entry together. One serializer, two queries: the joined half lives here."""
    return {
        **_invoice_summary(row),
        "duplicate_of_invoice_no": row["duplicate_of_invoice_no"],
    }


def _maybe_str(value) -> str | None:
    return None if value is None else str(value)


def _cost_figure(row: asyncpg.Record) -> dict:
    """One frozen cost, serialized: the figure per base unit, the same figure
    in the unit a person buys in, and the C8 record of how it was made.

    Shared by an invoice line and by a material's price (WP-53, WP-54), because
    a material's price *is* one of those lines - the newest among the packs
    mapped to it - and serializing it twice is how the two would drift.
    """
    cost = row["cost_per_base_unit"]
    basis = row["cost_basis"] or {}
    per_display, display_unit = costing.per_display_unit(cost, row["cost_base_unit"])
    return {
        "per_base_unit": _dec(cost),
        "base_unit": row["cost_base_unit"],
        "per_display_unit": _dec(per_display),
        "display_unit": display_unit,
        "quality": basis.get("quality"),
        "asserted": basis.get("asserted", []),
        "pack": basis.get("pack"),
        "pack_source": basis.get("pack_source"),
    }


def _line_cost(line: asyncpg.Record, *, costed: bool, foreign_currency: bool) -> dict | None:
    """What one gram of this line cost, or the reason there is no such number
    (M5 WP-53).

    Null means the question has not been asked yet: costs are frozen at
    confirm, so an invoice still waiting has none, and a charge line - cool-box
    hire, delivery - never gets one because it is not a thing you cook with.

    Both other answers are a payload, because "no cost" with no reason beside
    it is the dead end this product keeps promising not to be. The cost travels
    with its C9 quality and the pack it was divided by, which is the input
    nothing anywhere cross-checks.
    """
    if line["line_kind"] != "stock_item":
        return None
    if line["cost_per_base_unit"] is not None:
        return {**_cost_figure(line), "blocked": None, "reason": None}
    if not costed:
        return None
    blocked = costing.blocked_reason_for(
        qty=line["qty"],
        unit_price=line["unit_price"],
        pack_size=line["pack_size"],
        raw_name=line["raw_name"],
        unit=line["unit"],
        foreign_currency=foreign_currency,
    )
    if blocked is None:
        return None
    return {
        "per_base_unit": None,
        "base_unit": None,
        "per_display_unit": None,
        "display_unit": None,
        "quality": None,
        "asserted": [],
        "pack": None,
        "pack_source": None,
        "blocked": blocked.value,
        "reason": costing.BLOCKED_REASONS[blocked],
    }


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

    # Costs are frozen at confirm (WP-53), so before that a line is not
    # uncosted, it is simply not costed yet - a different sentence, and the
    # only one that is true.
    costed = invoice["status"] == InvoiceStatus.CONFIRMED
    foreign_currency = currency_differs(invoice["currency"], invoice["tenant_currency"])

    # The paper this one duplicates, so the screen can say which (WP-44 spends
    # this on the WhatsApp sentence; the pointer is what survives). One extra
    # read, and only for a held duplicate - the detail path pays nothing on an
    # ordinary invoice.
    duplicate_of = None
    if invoice["duplicate_of_invoice_id"] is not None:
        original = await db.get_invoice(str(invoice["duplicate_of_invoice_id"]))
        if original is not None:  # the composite FK makes a dangling pointer unreachable
            duplicate_of = {
                "id": str(original["id"]),
                "supplier_name": original["supplier_name"],
                "invoice_no": original["invoice_no"],
                "currency": original["currency"],
                "total": _dec(original["total"]),
                "created_at": _iso(original["created_at"]),
            }

    return {
        **_invoice_summary(invoice),
        "duplicate_of": duplicate_of,
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
                "line_kind": line["line_kind"],
                "checks": line["checks"],
                "cost": _line_cost(line, costed=costed, foreign_currency=foreign_currency),
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
    return {"invoices": [_invoice_list_row(row) for row in rows]}


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
        # Already confirmed, still a draft, or lost a race to another writer.
        # Re-read: see _fresh_status.
        raise HTTPException(
            status_code=409,
            detail=f"invoice is {await _fresh_status(db, str(invoice_id))}; cannot confirm",
        )

    # The price baseline moved inside the same transaction as the status flip
    # (WP-50), so there is nothing to do here but render the result. Two
    # transactions used to leave a confirmed invoice with no prices and this
    # endpoint answering 409 for ever.
    return await _invoice_detail(request, str(invoice_id))


async def _fresh_status(db: Database, invoice_id: str) -> str | None:
    """The invoice's status *now*, for a refusal sentence.

    Both write endpoints read the invoice, run a guarded update, and answer 409
    when the guard refuses. Building that sentence from the earlier read names
    whatever the status was a moment ago, which was near enough while confirm
    raced only against another confirm - and stopped being near enough the
    moment dismiss gave the same row a second door. Two tabs, one dismisses,
    the other confirms, and the screen said "invoice is needs_review; cannot
    confirm" about a row that was nothing of the sort."""
    row = await db.get_invoice(invoice_id)
    return None if row is None else row["status"]


@router.post("/invoices/{invoice_id}/dismiss")
async def dismiss_invoice(invoice_id: uuid.UUID, request: Request) -> dict:
    """The way out of a WP-44 duplicate hold, from the review screen.

    Held duplicates only, never a confirmed invoice, and never the original -
    the original carries no pointer, which is what stops a reviewer dismissing
    it and then the copy and losing the paper entirely. The guard is repeated in
    the single write (db.dismiss_invoice); this endpoint checks first so it can
    say which rule refused.

    The actor is `console`, never taken from the client (C8): a name anyone
    holding the shared token can choose looks like identity without being it."""
    db: Database = request.app.state.db
    invoice = await db.get_invoice(str(invoice_id))
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    if invoice["duplicate_of_invoice_id"] is None:
        raise HTTPException(
            status_code=409,
            detail="invoice is not a held duplicate; only a duplicate copy can be dismissed",
        )

    if not await db.dismiss_invoice(str(invoice_id), actor=CONSOLE_ACTOR):
        status = await _fresh_status(db, str(invoice_id))
        if status == InvoiceStatus.CONFIRMED:
            detail = "invoice is confirmed; a recorded invoice cannot be dismissed"
        elif status == InvoiceStatus.DISMISSED:
            detail = "invoice is already dismissed"
        else:
            detail = f"invoice is {status}; cannot dismiss"
        raise HTTPException(status_code=409, detail=detail)

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


# --- raw materials (M5 WP-52) ------------------------------------------------
#
# One shelf per ingredient. The catalog fills itself from invoices but is
# scoped to a supplier, so the same material bought from two suppliers is two
# rows. These endpoints are how a human joins them - and the joining is never
# automatic: the matcher proposes, a person approves, and every approve,
# reject, remap and unmap lands one audit_events row inside its own
# transaction (C8). A wrong merge corrupts the cost of every menu item using
# that material, and unlike a bad extraction there is no photo to check it
# against, so the actor is the only record of who to ask.


class IngredientMapping(BaseModel):
    """Approve a merge. `ingredient_id` points at an existing material;
    `name` creates one, because the matcher can only propose materials that
    already exist and a fresh tenant has none. `base_unit` is inferred from
    the pack when it can be, and required when it cannot."""

    model_config = ConfigDict(extra="forbid")

    ingredient_id: uuid.UUID | None = None
    name: str | None = None
    base_unit: Literal["g", "ml", "pc"] | None = None


class IngredientCreate(BaseModel):
    """A shelf with nothing on it yet (M6 WP-64). The loader needs this
    because a menu names materials long before an invoice does.

    It sends the recipe row's own measure - "g", "ml", "ea" - rather than a
    base unit, so which shelf a material sits on is decided by `units.py` and
    nowhere else. A browser that guessed "ea" meant pieces would be a second
    unit dictionary, and two dictionaries drift."""

    model_config = ConfigDict(extra="forbid")

    name: str
    unit: str


class IngredientRejection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ingredient_id: uuid.UUID


def _pack_summary(row: asyncpg.Record, cost: asyncpg.Record | None = None) -> dict:
    return {
        "id": row["id"],
        "canonical_name": row["canonical_name"],
        "unit": row["unit"],
        "pack_size": row["pack_size"],
        "supplier_name": row["supplier_name"],
        # What a person said is in one of these, when the invoice never did
        # (WP-55). Shown on the pack so the sentence does not disappear the
        # moment it takes effect.
        "pack_size_override": row["pack_size_override"],
        "last_price": _dec(row["last_price"]),
        "last_price_at": _iso(row["last_price_at"]),
        # What this particular pack most recently worked out at per kilo, which
        # is what makes two suppliers' packs comparable at all - the reason the
        # merge above it is worth making (WP-54).
        "cost": None if cost is None else _material_price(cost),
    }


def blocked_line_reason(line: asyncpg.Record) -> str:
    """Why a confirmed purchase line has no cost, in the WP-55 sentence the
    blocked-cost queue uses - one vocabulary, wherever the line surfaces."""
    blocked = costing.blocked_reason_for(
        qty=line["qty"],
        unit_price=line["unit_price"],
        pack_size=line["pack_size"],
        raw_name=line["raw_name"],
        unit=line["unit"],
        override=line["pack_size_override"],
        foreign_currency=currency_differs(line["currency"], line["tenant_currency"]),
    )
    # Costable on today's inputs but not costed: only a line confirmed before
    # M5 shipped. The next confirm of that product fixes it.
    if blocked is None:
        return "This purchase has not been costed yet."
    return costing.BLOCKED_REASONS[blocked]


def newer_uncosted_summary(line: asyncpg.Record) -> dict:
    """The blocked newer purchase, named (WP-61 amendment 3, D11): which line,
    on which invoice, bought when, and the WP-55 reason it has no cost."""
    return {
        "invoice_line_id": line["invoice_line_id"],
        "invoice_id": line["invoice_id"],
        "position": line["position"],
        "raw_name": line["raw_name"],
        "purchased_on": _iso(line["purchased_on"]),
        "reason": blocked_line_reason(line),
    }


def _material_price(row: asyncpg.Record, stale_line: asyncpg.Record | None = None) -> dict:
    """A material's price per kilo, and the purchase it came from (WP-54).

    Not a stored number: it is the newest costed line among the packs mapped to
    this material **right now**, so unmapping a wrong merge corrects it with
    nothing to rebuild. It carries the invoice line it came from rather than a
    summary-table row, which is a more precise thing for M6 to name as a
    plate's cost snapshot - and it is what lets the screen put the photo one
    click away from the figure.

    `stale_line` is the D11 flag (WP-61 amendment 3): the material's newest
    confirmed purchase could not be costed, so this price is real but not
    current. The figure stays visible with its date; the quality caps at
    *estimated* and the blocked line is named, so the screen can say "the
    newer delivery is the question to answer" instead of showing an old
    number wearing a good label.
    """
    payload = {
        **_cost_figure(row),
        "supplier_name": row["supplier_name"],
        "supplier_item_id": row["supplier_item_id"],
        "product_name": row["canonical_name"],
        "invoice_id": row["invoice_id"],
        "invoice_line_id": row["invoice_line_id"],
        # The printed line position, for the /invoices/<id>#line-<position>
        # anchor contract (design review): the drill lands on the row itself.
        "position": row["position"],
        # The date we ranked by, and separately whether the invoice printed one:
        # "bought on 6 July" and "recorded on 29 August" are different claims.
        "purchased_on": _iso(row["purchased_on"]),
        "invoice_date": _iso(row["invoice_date"]),
        "newer_uncosted": None,
    }
    if stale_line is not None:
        payload["quality"] = costing.Quality.ESTIMATED.value
        payload["newer_uncosted"] = newer_uncosted_summary(stale_line)
    return payload


async def _tenant(db: Database) -> str:
    tenant_id = await db.default_tenant_id()
    if tenant_id is None:
        raise HTTPException(status_code=409, detail="no tenant configured")
    return tenant_id


#: Plain English for a base unit. These strings reach the screen inside refusal
#: messages, and the no-jargon display rule (plan.md §3) applies there too - a
#: consultant reading "measured in ml" has to translate; "by volume" they do not.
MEASURE_WORDS = {"g": "by weight", "ml": "by volume", "pc": "by the piece"}


def _item_base_unit(item: asyncpg.Record) -> str | None:
    """Which base unit this pack reduces to, read from the pack column, then
    from the name (a till receipt prints the pack inside the name and has no
    pack column at all), then from a conversion a person supplied.

    None when none of the three names a measurable pack - a bare carton has no
    dimension until a human says what is in it. Once they have said "one holds
    10 kg" they have also said it is measured by weight, and asking them again
    on the very next screen would be the product not listening (WP-55)."""
    return (
        units.base_unit_of(item["pack_size"])
        or units.base_unit_of(item["canonical_name"])
        or units.base_unit_of(item["pack_size_override"])
    )


@router.get("/ingredients")
async def list_ingredients(request: Request) -> dict:
    """Every raw material, its one price per kilo, and the packs behind it.

    The price is **derived on every read** (WP-54) - the newest costed line
    among the packs mapped to this material right now, by printed invoice date.
    Nothing here is stored, which is why unmapping a wrong merge corrects the
    figure immediately and why there is no refresh anywhere to forget.
    """
    db: Database = request.app.state.db
    tenant_id = await _tenant(db)
    rows = await db.list_ingredients(tenant_id)

    # One query for the whole page. The rows arrive grouped by material with
    # that material's current price first, so the winner is `[0]` rather than a
    # second pass sorting in Python.
    costs: dict[str, list[asyncpg.Record]] = {}
    for cost in await db.list_mapped_pack_costs(tenant_id):
        costs.setdefault(cost["ingredient_id"], []).append(cost)
    by_pack = {cost["supplier_item_id"]: cost for rows_ in costs.values() for cost in rows_}

    # D11 (WP-61 amendment 3): a material whose newest confirmed purchase
    # could not be costed keeps its price visible but capped at *estimated*,
    # with the blocked line named - never an old number wearing a good label.
    stale: dict[str, asyncpg.Record] = {
        line["ingredient_id"]: line
        for line in await db.list_newest_purchases(tenant_id)
        if not line["costed"]
    }

    packs: dict[str, list[dict]] = {}
    for pack in await db.list_mapped_packs(tenant_id):
        packs.setdefault(pack["ingredient_id"], []).append(
            _pack_summary(pack, by_pack.get(pack["id"]))
        )
    return {
        "ingredients": [
            {
                "id": row["id"],
                "name": row["name"],
                "base_unit": row["base_unit"],
                "pack_count": row["pack_count"],
                "price": _material_price(costs[row["id"]][0], stale.get(row["id"]))
                if costs.get(row["id"])
                else None,
                "packs": packs.get(row["id"], []),
            }
            for row in rows
        ]
    }


@router.post("/ingredients", status_code=201)
async def create_ingredient(body: IngredientCreate, request: Request) -> dict:
    """Create a raw material with no pack mapped to it yet (M6 WP-64).

    Until M6, a material could only be born through a merge - there was no
    reason for a shelf nobody had bought anything for. A recipe is that
    reason: the menu says "Saffron" months before an invoice does, and the
    plate that uses it reads *incomplete* naming exactly that missing pack,
    which is the honest answer and the consultant's next task.

    One click per material, never a bulk keystroke - a CSV that mints twelve
    materials in one press is M5's forbidden auto-merge coming in through a
    side door (row 64). The screen enforces the click; this endpoint creates
    exactly one and names its actor."""
    db: Database = request.app.state.db
    tenant_id = await _tenant(db)
    name = _clean(body.name)
    if not name:
        raise HTTPException(status_code=422, detail="a raw material needs a name")
    base_unit = units.measure_base_unit(body.unit)
    if base_unit is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{body.unit.strip()}' does not say whether {name} is measured by "
                "weight (g, kg), by volume (ml, l) or in pieces"
            ),
        )
    try:
        ingredient = await db.create_ingredient(
            tenant_id=tenant_id, name=name, base_unit=base_unit, actor=CONSOLE_ACTOR
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=409, detail=f"a raw material called '{name}' already exists"
        ) from None
    return {
        "id": ingredient["id"],
        "name": ingredient["name"],
        "base_unit": ingredient["base_unit"],
    }


@router.get("/supplier-items/unmapped")
async def list_unmapped_supplier_items(request: Request) -> dict:
    """The consultant's queue: packs with no material yet, **most money
    first**, each carrying what the matcher proposes for it.

    Ranked by spend because that is the order in which a wrong cost hurts.
    Proposals are ranked suggestions and nothing more - approving is a
    keystroke a person makes, never a threshold the code crosses."""
    db: Database = request.app.state.db
    tenant_id = await _tenant(db)
    items = await db.list_unmapped_supplier_items(tenant_id)
    ingredients = await db.list_ingredients(tenant_id)
    rejected = await db.rejected_ingredients_by_item(tenant_id)
    return {
        "items": [
            {
                "id": item["id"],
                "canonical_name": item["canonical_name"],
                "unit": item["unit"],
                "pack_size": item["pack_size"],
                "supplier_id": item["supplier_id"],
                "supplier_name": item["supplier_name"],
                "spend": _dec(item["spend"]),
                "line_count": item["line_count"],
                "base_unit": _item_base_unit(item),
                "proposals": [
                    {"id": row["id"], "name": row["name"], "base_unit": row["base_unit"]}
                    for row in propose_ingredients(
                        ingredients,
                        item["canonical_name"],
                        rejected_ids=rejected.get(item["id"], set()),
                    )
                ],
            }
            for item in items
        ]
    }


@router.post("/supplier-items/{item_id}/ingredient")
async def map_supplier_item(item_id: uuid.UUID, body: IngredientMapping, request: Request) -> dict:
    """Approve the merge (or remap a pack already mapped elsewhere)."""
    db: Database = request.app.state.db
    item = await db.get_supplier_item_for_mapping(str(item_id))
    if item is None:
        raise HTTPException(status_code=404, detail="supplier item not found")

    pack_base_unit = _item_base_unit(item)
    if body.ingredient_id is not None:
        if body.name is not None or body.base_unit is not None:
            raise HTTPException(status_code=422, detail="give an ingredient_id or a name, not both")
        ingredient = await db.get_ingredient(str(body.ingredient_id))
        if ingredient is None:
            raise HTTPException(status_code=404, detail="ingredient not found")
        # Tenancy is enforced by the composite foreign key too (0012); this is
        # the answer with a reason in it, rather than an integrity error.
        if ingredient["tenant_id"] != item["tenant_id"]:
            raise HTTPException(status_code=404, detail="ingredient not found")
        base_unit = ingredient["base_unit"]
        material_name = ingredient["name"]
    else:
        name = _clean(body.name)
        if not name:
            raise HTTPException(status_code=422, detail="give an ingredient_id or a name")
        material_name = name
        # Inferred from the pack when the pack says so, which is the ordinary
        # case; asked for when it does not, rather than picked for the user.
        base_unit = body.base_unit or pack_base_unit
        if base_unit is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"'{item['canonical_name']}' does not say how much is in it, so say whether "
                    f"{name} is measured by weight, by volume or by the piece"
                ),
            )

    # The one refusal that protects every cost above this merge: a material has
    # one dimension, and a millilitre pack on a gram material is wrong in a way
    # no later arithmetic can notice. Only refused when the pack positively
    # disagrees - a bare carton says nothing, and WP-55 blocks its cost anyway.
    if pack_base_unit is not None and pack_base_unit != base_unit:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{item['canonical_name']}' is measured {MEASURE_WORDS[pack_base_unit]}, "
                f"but {material_name} is measured {MEASURE_WORDS[base_unit]}"
            ),
        )

    ingredient = await db.map_supplier_item(
        str(item_id),
        tenant_id=item["tenant_id"],
        ingredient_id=None if body.ingredient_id is None else str(body.ingredient_id),
        name=None if body.ingredient_id is not None else _clean(body.name),
        base_unit=base_unit,
        actor=CONSOLE_ACTOR,
        previous_ingredient_id=item["ingredient_id"],
    )
    return {
        "supplier_item_id": str(item_id),
        "ingredient": {
            "id": ingredient["id"],
            "name": ingredient["name"],
            "base_unit": ingredient["base_unit"],
        },
    }


@router.delete("/supplier-items/{item_id}/ingredient")
async def unmap_supplier_item(item_id: uuid.UUID, request: Request) -> dict:
    """The reverse gear (WP-52). A wrong merge is this milestone's worst case,
    and an approval gate with no undo leaves a consultant asking an engineer."""
    db: Database = request.app.state.db
    item = await db.get_supplier_item_for_mapping(str(item_id))
    if item is None:
        raise HTTPException(status_code=404, detail="supplier item not found")
    if item["ingredient_id"] is None:
        raise HTTPException(status_code=409, detail="supplier item is not mapped")
    await db.unmap_supplier_item(
        str(item_id),
        tenant_id=item["tenant_id"],
        actor=CONSOLE_ACTOR,
        ingredient_id=item["ingredient_id"],
    )
    return {"supplier_item_id": str(item_id), "ingredient": None}


@router.get("/blocked-costs")
async def list_blocked_costs(request: Request) -> dict:
    """The lines this layer could not turn into a cost, each with its own
    reason and what to do about it (M5 WP-55).

    **Derived from the data, not an `issues` table.** The fact is already on
    the line - it has no cost - and asking the same function that refused says
    which of six things went wrong. PRD §24's first-class issue records with
    severity and status are post-MVP; C5's "derived until real usage demands
    more" is the standing precedent.

    Grouped by product, because a carton bought twelve times is one question a
    person answers once, not twelve identical rows that teach them to stop
    reading the list. Most money first, like the mapping queue.
    """
    db: Database = request.app.state.db
    tenant_id = await _tenant(db)
    groups: dict[str, dict] = {}
    for line in await db.list_blocked_costs(tenant_id):
        blocked = costing.blocked_reason_for(
            qty=line["qty"],
            unit_price=line["unit_price"],
            pack_size=line["pack_size"],
            raw_name=line["raw_name"],
            unit=line["unit"],
            override=line["pack_size_override"],
            foreign_currency=currency_differs(line["currency"], line["tenant_currency"]),
        )
        if blocked is None:
            # Costable on today's inputs but not costed: only reachable for a
            # line confirmed before this milestone shipped. Not an issue to put
            # in front of a person - the next confirm of that product fixes it.
            continue
        # A line that never became a catalog row cannot be grouped with
        # anything, and cannot be answered either; it stands on its own.
        key = f"{line['supplier_item_id']}:{blocked.value}"
        if line["supplier_item_id"] is None:
            key = line["invoice_line_id"]
        group = groups.get(key)
        if group is None:
            groups[key] = group = {
                "id": key,
                "supplier_item_id": line["supplier_item_id"],
                "product_name": line["canonical_name"] or line["raw_name"],
                "supplier_name": line["supplier_name"],
                "pack_size": line["pack_size"],
                "unit": line["unit"],
                "pack_size_override": line["pack_size_override"],
                "ingredient_id": line["ingredient_id"],
                "ingredient_name": line["ingredient_name"],
                "blocked": blocked.value,
                "reason": costing.BLOCKED_REASONS[blocked],
                # Only a pack problem has an answer a person can give. A price
                # or a quantity the invoice never showed is not something a
                # conversion supplies, and offering a box to type in would be a
                # promise this screen cannot keep.
                "can_override": (
                    line["supplier_item_id"] is not None and blocked in costing.OVERRIDABLE
                ),
                "line_count": 0,
                "spend": Decimal(0),
                # The newest example, for the drill-through to the photo.
                "invoice_id": line["invoice_id"],
                "invoice_line_id": line["invoice_line_id"],
                "position": line["position"],
                "invoice_date": _iso(line["invoice_date"]),
            }
        group["line_count"] += 1
        group["spend"] += line["line_total"] or Decimal(0)

    ordered = sorted(groups.values(), key=lambda row: (-row["spend"], row["product_name"]))
    return {"blocked": [{**row, "spend": _dec(row["spend"])} for row in ordered]}


class PackSizeOverride(BaseModel):
    """How much is in one of these, said by a person (WP-55). Free text in the
    same forms an invoice prints - "10 kg", "24 x 400 ml" - read by the one
    pack dictionary rather than by a second parser."""

    model_config = ConfigDict(extra="forbid")

    pack_size: str


@router.post("/supplier-items/{item_id}/pack-size")
async def set_pack_size_override(
    item_id: uuid.UUID, body: PackSizeOverride, request: Request
) -> dict:
    """Clear a blocked cost by saying what the invoice never did.

    The refusals here are the point of the endpoint: an answer that is not an
    amount, or that contradicts the material it feeds, would produce a cost
    that is wrong in a way no later arithmetic could notice - and no photograph
    shows a cost per gram."""
    db: Database = request.app.state.db
    item = await db.get_supplier_item_for_mapping(str(item_id))
    if item is None:
        raise HTTPException(status_code=404, detail="supplier item not found")

    printed = _clean(body.pack_size)
    pack = None if printed is None else units.parse(printed)
    base_unit = None if printed is None else units.base_unit_of(printed)
    if pack is None or base_unit is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Say how much is in one of these, as an amount with its unit - "
                "like '10 kg', '750 ml' or '24 x 400 ml'."
            ),
        )
    # The same refusal the approval gate makes, for the same reason: a material
    # has one dimension, and a millilitre conversion feeding a gram material is
    # wrong in a way nothing downstream can see.
    material_unit = item["ingredient_base_unit"]
    if material_unit is not None and material_unit != base_unit:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{printed} is measured {MEASURE_WORDS[base_unit]}, but "
                f"{item['ingredient_name']} is measured {MEASURE_WORDS[material_unit]}"
            ),
        )

    costed = await db.set_pack_size_override(
        str(item_id),
        tenant_id=item["tenant_id"],
        pack_size=printed,
        actor=CONSOLE_ACTOR,
    )
    return {"supplier_item_id": str(item_id), "pack_size": printed, "lines_costed": costed}


@router.post("/supplier-items/{item_id}/ingredient/reject")
async def reject_ingredient(
    item_id: uuid.UUID, body: IngredientRejection, request: Request
) -> dict:
    """Not that material. Nothing else changes: the rejection is the record,
    and the queue stops offering an answer a person already refused."""
    db: Database = request.app.state.db
    item = await db.get_supplier_item_for_mapping(str(item_id))
    if item is None:
        raise HTTPException(status_code=404, detail="supplier item not found")
    ingredient = await db.get_ingredient(str(body.ingredient_id))
    if ingredient is None or ingredient["tenant_id"] != item["tenant_id"]:
        raise HTTPException(status_code=404, detail="ingredient not found")
    await db.reject_ingredient_for_item(
        str(item_id),
        tenant_id=item["tenant_id"],
        ingredient_id=str(body.ingredient_id),
        actor=CONSOLE_ACTOR,
    )
    return {"supplier_item_id": str(item_id), "rejected_ingredient_id": str(body.ingredient_id)}
