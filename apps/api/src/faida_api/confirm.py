"""WP-21: "OK" / correction parsing and routing - the confirm flow
(plan.md §6 M2, §7.2 C1/C5, §7.3).

An inbound WhatsApp text resolves against the newest awaiting_confirm invoice
whose document traces back to the sender phone (C5 - stateless, no
conversation table; nothing pending falls back to onboarding). "OK" confirms:
the invoice and its document flip to confirmed (C1) and
Database.record_confirmed_prices moves the price baseline (plan.md §5 layer
4). Corrections apply, re-validate, re-snap, re-alert, and re-reply with the
WP-20 composer; the invoice stays awaiting_confirm. Cash invoices are
needs_review and never addressable from chat (M6 owns approvals).

The chat grammar, in full (all keywords case-insensitive):

    OK | okay                          confirm (surrounding whitespace and
                                       punctuation tolerated)
    line <N> qty <number>              correct line N (1-based in chat,
    line <N> price <number>            0-based internally); "unit price" and
    line <N> total <number>            "line total" are accepted spellings
    line <N> name <text>               of price and total
    total <number>                     correct the totals block
    tax <number>
    subtotal <number>
    <edit>[, <edit> | ; <edit> | newline <edit>]...   several in one message
    <K> <any of the above>             pick invoice K from the numbered list
                                       when several are pending ("2 OK")

Numbers are unsigned decimals ("16", "4.50") - negatives, NaN, and anything
else unparseable get the one clarify reply that shows the accepted forms:
never a dead end, never silence.
"""

import datetime
import re
import zoneinfo
from decimal import Decimal
from typing import Literal

import asyncpg
from pydantic import BaseModel, ConfigDict

from .db import Database
from .extraction.pipeline import price_alerts
from .extraction.schema import ExtractedInvoice, ExtractedLine
from .extraction.validate import validate_invoice
from .matching import Row, snap_item
from .replies import (
    REPLY_CLARIFY,
    REPLY_TEXT_ONBOARDING,
    PendingInvoice,
    compose_confirmation_ack,
    compose_disambiguation_reply,
    compose_invoice_reply,
    compose_line_out_of_range,
)

# Branches carry their own timezone; this is the schema default, used when an
# unknown sender's invoice has no branch.
DEFAULT_TIMEZONE = "Asia/Dubai"

# --- parsed shapes ----------------------------------------------------------


class LineFieldEdit(BaseModel):
    """ "line 2 qty 16" - a numeric field on one line."""

    model_config = ConfigDict(extra="forbid")

    line_index: int  # 0-based internally; the chat says "line 1" for index 0
    field: Literal["qty", "unit_price", "line_total"]
    value: Decimal


class LineNameEdit(BaseModel):
    """ "line 2 name Karak Tea Dust" - rename one line."""

    model_config = ConfigDict(extra="forbid")

    line_index: int
    name: str


class TotalsEdit(BaseModel):
    """ "total 745.76" / "tax 35.51" / "subtotal 710.25"."""

    model_config = ConfigDict(extra="forbid")

    field: Literal["subtotal", "tax", "total"]
    value: Decimal


Edit = LineFieldEdit | LineNameEdit | TotalsEdit


class Confirm(BaseModel):
    """An "OK", optionally picking invoice `selector` from the numbered list."""

    model_config = ConfigDict(extra="forbid")

    selector: int | None = None


class Corrections(BaseModel):
    """One or more edits, optionally picking invoice `selector` first."""

    model_config = ConfigDict(extra="forbid")

    selector: int | None = None
    edits: list[Edit]


# --- parser (pure) ----------------------------------------------------------

_OK_RE = re.compile(r"[\W_]*(?:ok|okay)[\W_]*", re.IGNORECASE)
# A leading integer picks from the disambiguation list: "2 OK", "1 line 2 qty 16".
_SELECTOR_RE = re.compile(r"(\d+)[\s.,:;-]+(\S.*)", re.DOTALL)
_SEGMENT_SPLIT_RE = re.compile(r"[\n,;]+")
_LINE_EDIT_RE = re.compile(
    r"line\s+(\d+)\s+(qty|unit[\s_]?price|price|line[\s_]?total|total|name)\s+(.+)",
    re.IGNORECASE,
)
_TOTALS_EDIT_RE = re.compile(r"(subtotal|total|tax)\s+(.+)", re.IGNORECASE)
# Unsigned decimals only: no sign, no NaN, no exponent - anything else clarifies.
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

_LINE_FIELD_MAP: dict[str, Literal["qty", "unit_price", "line_total"]] = {
    "qty": "qty",
    "price": "unit_price",
    "unit price": "unit_price",
    "total": "line_total",
    "line total": "line_total",
}


def parse_reply(text: str) -> Confirm | Corrections | None:
    """Parse one inbound text against the chat grammar. None means
    unparseable - the flow answers with the clarify reply, never silence."""
    stripped = text.strip()
    if not stripped:
        return None
    selector: int | None = None
    body = stripped
    selected = _SELECTOR_RE.fullmatch(stripped)
    if selected is not None:
        selector = int(selected.group(1))
        body = selected.group(2)
    if _OK_RE.fullmatch(body) is not None:
        return Confirm(selector=selector)
    edits = _parse_corrections(body)
    if edits is None:
        return None
    return Corrections(selector=selector, edits=edits)


def _parse_corrections(text: str) -> list[Edit] | None:
    """Split on newlines/commas/semicolons; every segment must parse as one
    edit or the whole message is unparseable (a half-understood correction
    must never half-apply)."""
    edits: list[Edit] = []
    for segment in _SEGMENT_SPLIT_RE.split(text):
        segment = segment.strip()
        if not segment:
            continue
        edit = _parse_edit(segment)
        if edit is None:
            return None
        edits.append(edit)
    return edits or None


def _parse_edit(segment: str) -> Edit | None:
    line_edit = _LINE_EDIT_RE.fullmatch(segment)
    if line_edit is not None:
        n = int(line_edit.group(1))
        if n < 1:
            return None  # chat line numbers are 1-based; "line 0" is a typo
        field = re.sub(r"[\s_]+", " ", line_edit.group(2).casefold())
        value = line_edit.group(3).strip()
        if field == "name":
            return LineNameEdit(line_index=n - 1, name=value) if value else None
        number = _parse_number(value)
        if number is None:
            return None
        return LineFieldEdit(line_index=n - 1, field=_LINE_FIELD_MAP[field], value=number)
    totals_edit = _TOTALS_EDIT_RE.fullmatch(segment)
    if totals_edit is not None:
        number = _parse_number(totals_edit.group(2))
        if number is None:
            return None
        return TotalsEdit(field=totals_edit.group(1).casefold(), value=number)
    return None


def _parse_number(text: str) -> Decimal | None:
    # A sentence-ending "16." or "16!" is still a number; a sign or NaN is not.
    text = text.strip().rstrip(".!?")
    if _NUMBER_RE.fullmatch(text) is None:
        return None
    return Decimal(text)


def apply_edits(invoice: ExtractedInvoice, edits: list[Edit]) -> ExtractedInvoice:
    """Pure merge of parsed edits over an extracted invoice; the input is
    never mutated. Line indices must already be in range."""
    lines: list[ExtractedLine] = list(invoice.lines)
    header: dict[str, Decimal] = {}
    for edit in edits:
        if isinstance(edit, TotalsEdit):
            header[edit.field] = edit.value
        elif isinstance(edit, LineNameEdit):
            lines[edit.line_index] = lines[edit.line_index].model_copy(
                update={"raw_name": edit.name}
            )
        else:
            lines[edit.line_index] = lines[edit.line_index].model_copy(
                update={edit.field: edit.value}
            )
    return invoice.model_copy(update={"lines": lines, **header})


# --- flow (called from the worker's text branch) ----------------------------


async def handle_inbound_text(
    db: Database, from_phone: str | None, text: str, received_at: datetime.datetime
) -> str:
    """Resolve one inbound text per C5 and return the reply to send.
    `received_at` is the wa_messages arrival time of this text: the retry
    guard compares it against invoices.confirmed_at so a re-run job re-sends
    the ack instead of confirming a second invoice."""
    if not from_phone:
        return REPLY_TEXT_ONBOARDING
    parsed = parse_reply(text)

    if isinstance(parsed, Confirm):
        already = await db.latest_confirmed_invoice_for_phone(
            from_phone, confirmed_after=received_at
        )
        if already is not None:
            # This text already confirmed on a previous attempt (the job
            # retried after a failed send): heal the price recording
            # (idempotent) and re-send the ack - never confirm again.
            await db.record_confirmed_prices(str(already["id"]))
            return _ack(already)

    pending = await db.awaiting_confirm_invoices_for_phone(from_phone)
    if not pending:
        if isinstance(parsed, Confirm) and parsed.selector is None:
            last = await db.latest_confirmed_invoice_for_phone(from_phone)
            if last is not None:
                # A duplicate "OK": the ack again, nothing re-recorded.
                return _ack(last)
        return REPLY_TEXT_ONBOARDING
    if parsed is None:
        return REPLY_CLARIFY

    if parsed.selector is not None:
        if not 1 <= parsed.selector <= len(pending):
            return _disambiguation(pending)
        target = pending[parsed.selector - 1]
    elif len(pending) > 1:
        # C5: several pending and no number - list them; the sender resends
        # with the number in front (stateless, nothing to remember).
        return _disambiguation(pending)
    else:
        target = pending[0]

    if isinstance(parsed, Confirm):
        # Ambers still open confirm too - the closing promised "OK to
        # confirm the rest".
        await db.confirm_invoice(str(target["id"]))
        await db.record_confirmed_prices(str(target["id"]))
        return _ack(target)
    return await _apply_correction(db, str(target["id"]), parsed.edits)


async def _apply_correction(db: Database, invoice_id: str, edits: list[Edit]) -> str:
    """Apply parsed edits: re-validate, re-snap against the supplier catalog
    (the pipeline's convention - snapped flags folded into the checks, never
    recomputing status), recompute price alerts the same way the pipeline
    does, persist, and re-reply. Status stays awaiting_confirm."""
    invoice_row = await db.get_invoice(invoice_id)
    line_rows = await db.get_invoice_lines(invoice_id)
    line_count = len(line_rows)
    for edit in edits:
        if isinstance(edit, LineFieldEdit | LineNameEdit) and edit.line_index >= line_count:
            return compose_line_out_of_range(edit.line_index + 1, line_count)

    invoice = apply_edits(_to_extracted(invoice_row, line_rows), edits)
    validation = validate_invoice(invoice)

    snapped_items: list[Row | None] = [None] * len(invoice.lines)
    line_checks = validation.lines
    if invoice_row["supplier_id"] is not None:
        items = await db.list_supplier_items(str(invoice_row["supplier_id"]))
        snapped_items = [snap_item(items, line.raw_name) for line in invoice.lines]
        line_checks = [
            check.model_copy(update={"snapped": item is not None})
            for check, item in zip(line_checks, snapped_items, strict=True)
        ]
        validation = validation.model_copy(update={"lines": line_checks})

    alerts = price_alerts(invoice, snapped_items)
    confidence = {
        "document": validation.document.model_dump(mode="json"),
        "lines": [check.status.value for check in line_checks],
    }
    lines = [
        {
            "position": line_rows[index]["position"],
            "raw_name": line.raw_name,
            "supplier_item_id": str(item["id"]) if item is not None else None,
            "qty": line.qty,
            "unit_price": line.unit_price,
            "line_total": line.line_total,
            "checks": check.model_dump(mode="json"),
        }
        for index, (line, check, item) in enumerate(
            zip(invoice.lines, line_checks, snapped_items, strict=True)
        )
    ]
    await db.apply_invoice_correction(
        invoice_id,
        subtotal=invoice.subtotal,
        tax=invoice.tax,
        total=invoice.total,
        confidence=confidence,
        lines=lines,
    )
    return compose_invoice_reply(invoice, validation, alerts)


def _ack(invoice_row: asyncpg.Record) -> str:
    return compose_confirmation_ack(
        invoice_row["supplier_name"], invoice_row["currency"], invoice_row["total"]
    )


def _disambiguation(pending: list[asyncpg.Record]) -> str:
    return compose_disambiguation_reply(
        [
            PendingInvoice(
                supplier_name=row["supplier_name"],
                currency=row["currency"],
                total=row["total"],
                received_at=_local_time(row["created_at"], row["timezone"]),
            )
            for row in pending
        ]
    )


def _local_time(moment: datetime.datetime, timezone_name: str | None) -> datetime.datetime:
    try:
        return moment.astimezone(zoneinfo.ZoneInfo(timezone_name or DEFAULT_TIMEZONE))
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return moment.astimezone(zoneinfo.ZoneInfo(DEFAULT_TIMEZONE))


def _to_extracted(invoice_row: asyncpg.Record, line_rows: list[asyncpg.Record]) -> ExtractedInvoice:
    """Rebuild the C3 schema shape from the persisted rows so corrections
    run through exactly the validation the pipeline used."""
    return ExtractedInvoice(
        supplier_name=invoice_row["supplier_name"],
        invoice_no=invoice_row["invoice_no"],
        invoice_date=invoice_row["invoice_date"],
        currency=invoice_row["currency"],
        payment_kind=invoice_row["payment_kind"],
        lines=[
            ExtractedLine(
                raw_name=row["raw_name"],
                qty=row["qty"],
                unit=row["unit"],
                pack_size=row["pack_size"],
                unit_price=row["unit_price"],
                line_total=row["line_total"],
            )
            for row in line_rows
        ],
        subtotal=invoice_row["subtotal"],
        tax=invoice_row["tax"],
        total=invoice_row["total"],
    )
