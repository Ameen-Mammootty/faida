"""WP-21: "OK" / correction parsing and routing - the confirm flow
(plan.md §6 M2, §7.2 C1/C5, §7.3).

An inbound WhatsApp text resolves against the newest awaiting_confirm invoice
whose document traces back to the sender phone (C5 - stateless, no
conversation table; nothing pending falls back to onboarding). "OK" confirms:
the invoice flips to confirmed (C1 - the document stays 'extracted', its
status tracking ingest only) and Database.record_confirmed_prices moves the
price baseline (plan.md §5 layer 4). Corrections apply, re-validate, re-snap,
re-alert, and re-reply with the WP-20 composer; the invoice stays
awaiting_confirm. Cash invoices are needs_review and never addressable from
chat (M7 owns approvals).

The chat grammar, in full (all keywords case-insensitive):

    OK | okay                          confirm (surrounding whitespace and
                                       punctuation tolerated)
    line <N> qty <number>              correct line N (1-based in chat,
    line <N> price <number>            0-based internally); "unit price" and
    line <N> total <number>            "line total" are accepted spellings
    line <N> name <text>               of price and total
    line <N> pack size <text>          the pack on line N ("5kg", "12 pcs");
                                       "pack" and "size" also accepted. A dash
                                       or "none" clears it - the one line field
                                       no arithmetic can check, and sometimes
                                       derived from the item name, so a person
                                       must always be able to correct it
    total <number>                     correct the totals block
    tax <number>
    subtotal <number>
    total <number> inc vat <rate>%     WP-26: the totals block is not on the
    total <number> no vat              page and the sender is saying what it
                                       would have said - <number> is the whole
                                       invoice, with VAT inside it at <rate> or
                                       with none charged. Stored as
                                       `reconstructed` (C8), never as printed
    currency <code>                    the invoice currency (WP-28); an ISO
                                       code or a printed word ("dirhams")
    date <date>                        the invoice date (WP-25); parsed by the
                                       same day-first rules extraction uses
                                       ("5/7/26", "2026-07-05", "9 July 2026");
                                       "invoice date ..." also accepted
    invoice no <text>                  the invoice number (WP-25); "invoice
                                       number" / "inv no" / "invoice #" too
    <edit>[, <edit> | ; <edit> | newline <edit>]...   several in one message
    <K> <any of the above>             pick invoice K from the numbered list
                                       when several are pending ("2 OK")

Numbers are unsigned decimals ("16", "4.50") - negatives, NaN, and anything
else unparseable get the one clarify reply that shows the accepted forms:
never a dead end, never silence. A date-shaped answer with no year ("date
5/7") gets its own reply asking for the year, because parsing it any other
way would be a guess (C3/WP-27), and "inc vat" with no rate gets its own reply
asking for the rate, for the same reason.

A bare "OK" confirms an invoice with open ambers - the reply promised "or OK to
confirm the rest" - but never one with no total (WP-26, founder call
2026-08-28): a missing line quantity is a small hole, while the total is the
invoice's headline number and M5 divides it into plate costs no photograph can
check. That OK gets the totals question again, not a confirmation.
"""

import datetime
import re
import zoneinfo
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

import asyncpg
from pydantic import BaseModel, ConfigDict

from .db import Database
from .extraction.currency import normalize_currency
from .extraction.dates import parse_printed_date
from .extraction.normalize import blank_to_none
from .extraction.pipeline import price_alerts
from .extraction.schema import ExtractedInvoice, ExtractedLine
from .extraction.validate import validate_invoice
from .matching import Row, snap_item
from .provenance import Origin, line_key, mark
from .replies import (
    REPLY_CLARIFY,
    REPLY_TEXT_ONBOARDING,
    PendingInvoice,
    compose_ambiguous_date_reply,
    compose_confirmation_ack,
    compose_disambiguation_reply,
    compose_invoice_reply,
    compose_line_out_of_range,
    compose_total_needed_reply,
    compose_vat_rate_reply,
)

# Branches carry their own timezone; this is the schema default, used when an
# unknown sender's invoice has no branch.
DEFAULT_TIMEZONE = "Asia/Dubai"


def chat_actor(from_phone: str) -> str:
    """C8/M5 actor for someone acting over WhatsApp. Real accounts arrive in
    M7; until then the phone that sent the message is who did it, which is a
    real answer where the alternative is silence."""
    return f"whatsapp:{from_phone}"


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


class LinePackSizeEdit(BaseModel):
    """ "line 2 pack size 5kg" - set or clear the pack on one line.

    The pack size is the number M5 divides a unit price by to reach a cost per
    gram, and it is the one line field no arithmetic can check: C4's identities
    anchor on the line sum, so a wrong pack sits green forever. It is also
    sometimes *derived* rather than read, when the page prints no pack column
    and the pack lives in the item name (`units.pack_size_for`). A value that
    nothing can verify and nobody can edit is a silent wrong number waiting to
    happen, so this is the door: `pack_size` None clears it, which is how a
    person says "that pack is not right, and I do not know the real one".
    """

    model_config = ConfigDict(extra="forbid")

    line_index: int
    pack_size: str | None


class TotalsEdit(BaseModel):
    """ "total 745.76" / "tax 35.51" / "subtotal 710.25"."""

    model_config = ConfigDict(extra="forbid")

    field: Literal["subtotal", "tax", "total"]
    value: Decimal


class ReconstructedTotalEdit(BaseModel):
    """ "total 930.00 inc vat 5%" / "total 930.00 no vat" - WP-26.

    Not a correction of a misread number: the totals block was never in the
    frame, so this is the sender telling us what the invoice adds up to. It
    carries the tax with it, because the two facts arrive together and C4
    cannot resolve the treatment from a total alone - `vat_rate` None means no
    VAT was charged, and the tax stored is 0.
    """

    model_config = ConfigDict(extra="forbid")

    value: Decimal
    vat_rate: Decimal | None  # a fraction: 5% arrives as Decimal("0.05")

    @property
    def tax(self) -> Decimal:
        """The VAT inside `value` at `vat_rate`, to the fil.

        Arithmetic on an asserted fact, not a reading of the page - which is
        exactly what the `reconstructed` origin labels. Stated as
        total - total/(1+r) because the sender said the printed prices already
        include the VAT, so the total is the gross figure."""
        if self.vat_rate is None or self.vat_rate <= 0:
            return Decimal("0.00")
        net = self.value / (1 + self.vat_rate)
        return (self.value - net).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CurrencyEdit(BaseModel):
    """ "currency AED" - the invoice's own currency (WP-28), as an ISO code."""

    model_config = ConfigDict(extra="forbid")

    value: str


class DateEdit(BaseModel):
    """ "date 5/7/26" - the invoice date (WP-25), read by the same day-first
    rules extraction uses (extraction.dates)."""

    model_config = ConfigDict(extra="forbid")

    value: datetime.date


class InvoiceNoEdit(BaseModel):
    """ "invoice no 4471" - the invoice number, kept verbatim."""

    model_config = ConfigDict(extra="forbid")

    value: str


class AmbiguousDateEdit(BaseModel):
    """ "date 5/7" - date-shaped but missing its year. Never applied: the flow
    answers with the year question (compose_ambiguous_date_reply) instead of
    guessing, per C3 (an ambiguous date is not a date)."""

    model_config = ConfigDict(extra="forbid")

    text: str


class MissingVatRateEdit(BaseModel):
    """ "total 930 inc vat" - VAT is in there, but at what rate? Never applied,
    for the same reason as an ambiguous date: the GCC prints five different
    rates and picking one would be a guess stored as a fact."""

    model_config = ConfigDict(extra="forbid")

    total: Decimal


Edit = (
    LineFieldEdit
    | LineNameEdit
    | LinePackSizeEdit
    | TotalsEdit
    | ReconstructedTotalEdit
    | CurrencyEdit
    | DateEdit
    | InvoiceNoEdit
    | AmbiguousDateEdit
    | MissingVatRateEdit
)


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
    r"line\s+(\d+)\s+"
    r"(qty|unit[\s_]?price|price|line[\s_]?total|total|name|pack[\s_]?size|pack|size)\s+(.+)",
    re.IGNORECASE,
)
_TOTALS_EDIT_RE = re.compile(r"(subtotal|total|tax)\s+(.+)", re.IGNORECASE)
# WP-26: "total 930.00 inc vat 5%" / "total 930 including vat 5" / "total 930
# no vat" / "total 930 without vat". The rate is optional in the pattern so a
# rate-less "inc vat" can be *asked about* rather than silently rejected into
# the generic clarify.
_RECONSTRUCTED_TOTAL_RE = re.compile(
    r"total\s+(\d+(?:\.\d+)?)\s+"
    r"(?:(?P<inc>inc|incl|including|includes|with)\s+vat(?:\s+(?P<rate>\d+(?:\.\d+)?)\s*%?)?"
    r"|(?P<none>no|zero|nil|without|excl|excluding)\s+vat)",
    re.IGNORECASE,
)
_CURRENCY_EDIT_RE = re.compile(r"currency\s+(.+)", re.IGNORECASE)
_ISO_CODE_RE = re.compile(r"[A-Za-z]{3}")
_DATE_EDIT_RE = re.compile(r"(?:invoice\s+)?date\s+(.+)", re.IGNORECASE)
_INVOICE_NO_EDIT_RE = re.compile(
    r"(?:invoice|inv)\.?\s*(?:no|number|num|#)\.?\s*:?\s*(.+)", re.IGNORECASE
)
# Unsigned decimals only: no sign, no NaN, no exponent - anything else clarifies.
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

# The chat spellings that mean the pack-size cell. Normalized the same way as
# the numeric field names ("pack_size" and "pack size" both arrive as "pack size").
_PACK_FIELDS = frozenset({"pack size", "pack", "size"})

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
        if field in _PACK_FIELDS:
            # A person clearing a pack ("line 2 pack -") is saying the pack we
            # hold is wrong, which is a real answer and not an empty one.
            return LinePackSizeEdit(line_index=n - 1, pack_size=blank_to_none(value))
        number = _parse_number(value)
        if number is None:
            return None
        return LineFieldEdit(line_index=n - 1, field=_LINE_FIELD_MAP[field], value=number)
    date_edit = _DATE_EDIT_RE.fullmatch(segment)
    if date_edit is not None:
        text = date_edit.group(1).strip()
        parsed = parse_printed_date(text)
        if parsed.date is not None:
            return DateEdit(value=parsed.date)
        if parsed.ambiguous:
            return AmbiguousDateEdit(text=text)
        return None
    number_edit = _INVOICE_NO_EDIT_RE.fullmatch(segment)
    if number_edit is not None:
        value = number_edit.group(1).strip()
        return InvoiceNoEdit(value=value) if value else None
    currency_edit = _CURRENCY_EDIT_RE.fullmatch(segment)
    if currency_edit is not None:
        return _parse_currency(currency_edit.group(1))
    # Before the plain totals rule: "total 930 no vat" would otherwise reach
    # _parse_number as "930 no vat" and clarify.
    reconstructed = _RECONSTRUCTED_TOTAL_RE.fullmatch(segment)
    if reconstructed is not None:
        total = Decimal(reconstructed.group(1))
        if reconstructed.group("none") is not None:
            return ReconstructedTotalEdit(value=total, vat_rate=None)
        rate = reconstructed.group("rate")
        if rate is None:
            return MissingVatRateEdit(total=total)
        percent = Decimal(rate)
        if not 0 <= percent < 100:
            return None
        if percent == 0:
            return ReconstructedTotalEdit(value=total, vat_rate=None)
        return ReconstructedTotalEdit(value=total, vat_rate=percent / Decimal("100"))
    totals_edit = _TOTALS_EDIT_RE.fullmatch(segment)
    if totals_edit is not None:
        number = _parse_number(totals_edit.group(2))
        if number is None:
            return None
        return TotalsEdit(field=totals_edit.group(1).casefold(), value=number)
    return None


def _parse_currency(text: str) -> CurrencyEdit | None:
    """ "currency AED", "currency usd", "currency dirhams" - the printed word
    goes through the same table the pipeline uses (extraction/currency.py), so
    chat and extraction can never disagree about what "Dhs" means. Anything
    that does not land on a three-letter code is refused rather than stored:
    an invented currency is worse than a clarify."""
    code = normalize_currency(text.strip())
    if code is None or _ISO_CODE_RE.fullmatch(code) is None:
        return None
    return CurrencyEdit(value=code.upper())


def _parse_number(text: str) -> Decimal | None:
    # A sentence-ending "16." or "16!" is still a number; a sign or NaN is not.
    text = text.strip().rstrip(".!?")
    if _NUMBER_RE.fullmatch(text) is None:
        return None
    return Decimal(text)


def edited_field_keys(edits: list[Edit]) -> list[str]:
    """The C8 field paths this batch of edits writes to, in order and without
    duplicates. Lives here rather than in provenance.py because it is the chat
    grammar's edit shapes that are being mapped, and provenance.py stays free
    of them."""
    keys: list[str] = []
    for edit in edits:
        if isinstance(edit, TotalsEdit):
            new_keys = [edit.field]
        elif isinstance(edit, ReconstructedTotalEdit):
            # Both, always: the sender asserted the totals block, and the tax
            # is derived from the same sentence as the total.
            new_keys = ["total", "tax"]
        elif isinstance(edit, CurrencyEdit):
            new_keys = ["currency"]
        elif isinstance(edit, DateEdit):
            new_keys = ["invoice_date"]
        elif isinstance(edit, InvoiceNoEdit):
            new_keys = ["invoice_no"]
        elif isinstance(edit, AmbiguousDateEdit | MissingVatRateEdit):
            raise ValueError("an unanswerable edit is asked about, never applied")
        elif isinstance(edit, LineNameEdit):
            new_keys = [line_key(edit.line_index, "raw_name")]
        elif isinstance(edit, LinePackSizeEdit):
            new_keys = [line_key(edit.line_index, "pack_size")]
        else:
            new_keys = [line_key(edit.line_index, edit.field)]
        keys.extend(key for key in new_keys if key not in keys)
    return keys


def reconstructed_field_keys(edits: list[Edit]) -> list[str]:
    """The subset of `edited_field_keys` that no camera ever saw (C8's
    `reconstructed`). A total the sender read off the page is a correction like
    any other; a total assembled from "930 is the whole invoice, VAT included"
    is not, and C9 has to be able to tell them apart four sums downstream."""
    keys: list[str] = []
    for edit in edits:
        if isinstance(edit, ReconstructedTotalEdit):
            keys.extend(key for key in ("total", "tax") if key not in keys)
    return keys


def apply_edits(invoice: ExtractedInvoice, edits: list[Edit]) -> ExtractedInvoice:
    """Pure merge of parsed edits over an extracted invoice; the input is
    never mutated. Line indices must already be in range, and an
    AmbiguousDateEdit must already have been answered by the flow - it
    carries no date to apply."""
    lines: list[ExtractedLine] = list(invoice.lines)
    header: dict[str, object] = {}
    for edit in edits:
        if isinstance(edit, TotalsEdit):
            header[edit.field] = edit.value
        elif isinstance(edit, ReconstructedTotalEdit):
            header["total"] = edit.value
            header["tax"] = edit.tax
        elif isinstance(edit, CurrencyEdit):
            header["currency"] = edit.value
        elif isinstance(edit, DateEdit):
            header["invoice_date"] = edit.value
        elif isinstance(edit, InvoiceNoEdit):
            header["invoice_no"] = edit.value
        elif isinstance(edit, AmbiguousDateEdit | MissingVatRateEdit):
            raise ValueError("an unanswerable edit is asked about, never applied")
        elif isinstance(edit, LineNameEdit):
            lines[edit.line_index] = lines[edit.line_index].model_copy(
                update={"raw_name": edit.name}
            )
        elif isinstance(edit, LinePackSizeEdit):
            lines[edit.line_index] = lines[edit.line_index].model_copy(
                update={"pack_size": edit.pack_size}
            )
        else:
            lines[edit.line_index] = lines[edit.line_index].model_copy(
                update={edit.field: edit.value}
            )
    return invoice.model_copy(update={"lines": lines, **header})


# --- flow (called from the worker's text branch) ----------------------------


async def handle_inbound_text(
    db: Database,
    from_phone: str | None,
    text: str,
    received_at: datetime.datetime,
    *,
    message_id: str | None = None,
) -> str:
    """Resolve one inbound text per C5 and return the reply to send.
    `received_at` is the wa_messages arrival time of this text: the retry
    guard compares it against invoices.confirmed_at so a re-run job re-sends
    the ack instead of confirming a second invoice.

    `message_id` is that text's WhatsApp id, recorded on the audit event. A
    correction has no confirm-style retry guard - re-applying the same edits
    is harmless because the values are identical - so a job that retries after
    a failed send does write a second `invoice.corrected` row. Carrying the
    message id makes those two rows visibly one retried message rather than
    two decisions, which is cheaper and more honest than a dedupe guard for
    something that costs a duplicate line in a log."""
    if not from_phone:
        return REPLY_TEXT_ONBOARDING
    parsed = parse_reply(text)

    if isinstance(parsed, Confirm):
        already = await db.latest_confirmed_invoice_for_phone(
            from_phone, confirmed_after=received_at
        )
        if already is not None:
            # This text already confirmed on a previous attempt (the job
            # retried after a failed send): re-send the ack, never confirm
            # again. The price re-run is idempotent and, since WP-50 made the
            # confirm atomic, has nothing left to heal on a row confirmed by
            # this code - it stays for rows confirmed before that merge.
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
    if isinstance(parsed, Corrections):
        # An answer that is still missing a fact cannot apply anywhere - ask
        # for the missing half before any invoice-picking, since no pick would
        # make "5/7" a date or "inc vat" a rate.
        ambiguous = next((e for e in parsed.edits if isinstance(e, AmbiguousDateEdit)), None)
        if ambiguous is not None:
            return compose_ambiguous_date_reply(ambiguous.text)
        rateless = next((e for e in parsed.edits if isinstance(e, MissingVatRateEdit)), None)
        if rateless is not None:
            return compose_vat_rate_reply(rateless.total)

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
        if target["total"] is None:
            # WP-26: open ambers still confirm - the closing promised "OK to
            # confirm the rest" - but a missing total is not one of them. It is
            # the invoice's headline number, invisible to everything
            # downstream, and by M5 it is a plate cost nobody can check.
            return await _total_needed(db, str(target["id"]))
        # One call, one transaction: the status flip, the audit row and the
        # price baseline commit together or not at all (WP-50).
        await db.confirm_invoice(str(target["id"]), actor=chat_actor(from_phone))
        return _ack(target)
    return await _apply_correction(
        db,
        str(target["id"]),
        parsed.edits,
        actor=chat_actor(from_phone),
        message_id=message_id,
    )


async def _apply_correction(
    db: Database,
    invoice_id: str,
    edits: list[Edit],
    *,
    actor: str,
    origin: Origin = Origin.CORRECTED_CHAT,
    message_id: str | None = None,
) -> str:
    """Apply parsed edits: re-validate, re-snap against the supplier catalog
    (the pipeline's convention - snapped flags folded into the checks, never
    recomputing status), recompute price alerts the same way the pipeline
    does, persist, and re-reply. Status stays awaiting_confirm.

    `actor` and `origin` are C8: the same function serves the chat grammar and
    the review screen's PATCH (one door for both, plan.md §7.2 C8), so the
    caller says which door this correction came through and who was at it. The
    edited fields are re-stamped; every field the edits did not touch keeps the
    origin it already had."""
    invoice_row = await db.get_invoice(invoice_id)
    line_rows = await db.get_invoice_lines(invoice_id)
    line_count = len(line_rows)
    for edit in edits:
        if (
            isinstance(edit, LineFieldEdit | LineNameEdit | LinePackSizeEdit)
            and edit.line_index >= line_count
        ):
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

    tenant_currency = invoice_row["tenant_currency"]
    alerts = price_alerts(invoice, snapped_items, tenant_currency=tenant_currency)
    confidence = {
        "document": validation.document.model_dump(mode="json"),
        "lines": [check.status.value for check in line_checks],
    }
    corrected = edited_field_keys(edits)
    now = datetime.datetime.now(datetime.UTC)
    provenance = mark(
        invoice_row["provenance"] or {},
        corrected,
        origin=origin,
        actor=actor,
        at=now,
    )
    # WP-26: within one message, a total read off the page and a total
    # assembled from answers are both edits and only one of them is checkable
    # against a photo. The reconstructed subset is re-stamped over the door's
    # own origin, so "line 2 qty 16, total 930 inc vat 5%" records each half
    # honestly (C8; C9 reads the difference from M5 onward).
    reconstructed = reconstructed_field_keys(edits)
    if reconstructed:
        provenance = mark(
            provenance, reconstructed, origin=Origin.RECONSTRUCTED, actor=actor, at=now
        )
    lines = [
        {
            "position": line_rows[index]["position"],
            "raw_name": line.raw_name,
            "supplier_item_id": str(item["id"]) if item is not None else None,
            "qty": line.qty,
            "unit": line.unit,
            "pack_size": line.pack_size,
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
        invoice_no=invoice.invoice_no,
        invoice_date=invoice.invoice_date,
        currency=invoice.currency,
        subtotal=invoice.subtotal,
        tax=invoice.tax,
        total=invoice.total,
        # Re-derived by C4 from the corrected arithmetic, exactly as the
        # pipeline derives them on the way in. They have to travel with the
        # correction: the confirm path reads `invoices.tax_treatment` to record
        # price memory net of VAT, so a stale one would store a gross price
        # under a net baseline - the mixed-basis alert C4 exists to prevent.
        tax_treatment=validation.document.tax_treatment,
        vat_rate=validation.document.vat_rate,
        confidence=confidence,
        provenance=provenance,
        lines=lines,
        actor=actor,
        corrected_fields=corrected,
        message_id=message_id,
    )
    return compose_invoice_reply(invoice, validation, alerts, tenant_currency=tenant_currency)


async def _total_needed(db: Database, invoice_id: str) -> str:
    """WP-26's answer to an OK on a totals-less invoice: the same question
    again. The line sum comes from re-running the shipped validator over the
    stored rows rather than summing them here - C4's rule for when a line sum
    exists at all (never, if one line total is unreadable) has one
    implementation, and this is not it."""
    invoice_row = await db.get_invoice(invoice_id)
    line_rows = await db.get_invoice_lines(invoice_id)
    invoice = _to_extracted(invoice_row, line_rows)
    validation = validate_invoice(invoice)
    return compose_total_needed_reply(validation.document.line_sum, invoice.currency)


def _ack(invoice_row: asyncpg.Record) -> str:
    return compose_confirmation_ack(
        invoice_row["supplier_name"],
        invoice_row["currency"],
        invoice_row["total"],
        tenant_currency=invoice_row["tenant_currency"],
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
    run through exactly the validation the pipeline used. line_kind, the
    discount and the rounding must ride along: without them a correction on a
    discounted invoice re-validates against the wrong C4 identity and fails a
    correct invoice into amber."""
    return ExtractedInvoice(
        supplier_name=invoice_row["supplier_name"],
        invoice_no=invoice_row["invoice_no"],
        invoice_date=invoice_row["invoice_date"],
        currency=invoice_row["currency"],
        payment_kind=invoice_row["payment_kind"],
        lines=[
            ExtractedLine(
                raw_name=row["raw_name"],
                line_kind=row["line_kind"],
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
        discount_total=invoice_row["discount_total"],
        rounding_amount=invoice_row["rounding_amount"],
    )
