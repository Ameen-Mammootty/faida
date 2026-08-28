"""WP-20: the WhatsApp reply composer (plan.md §6 M2, §7.3).

Every message the product sends is a deterministic English template - zero
generation, per plan.md §3 (language decision). Pure functions over the
extraction pipeline's output types (§5 layers 5-6): same inputs, same bytes;
no I/O, no clock, no randomness. Money is Decimal end to end (C4) and always
renders with exactly two decimals in the invoice currency (default AED).

Integration (next wave) swaps the plain M1 constants in pipeline.py and
worker.py for the exports here. WP-21 parses the replies these questions
invite; WP-23 constructs the PriceAlert values this module only renders.
"""

import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .extraction.schema import ExtractedInvoice, ExtractedLine
from .extraction.validate import CheckStatus, FieldStatus, LineCheck, ValidationResult

DEFAULT_CURRENCY = "AED"

# At most this many amber-field questions per reply; the rest overflow to the
# review screen (plan.md §5 layer 5: amber drives one specific question).
MAX_AMBER_QUESTIONS = 3

# --- fixed messages -------------------------------------------------------
# Supersede the WP-13 pipeline.py and M0 worker.py constants at integration.

# Media ack (C2: sent by process_wa_message before extraction runs).
REPLY_MEDIA_RECEIVED = "Got it - invoice received and saved. I'll reply with the details here soon."
# Text onboarding: an inbound text with nothing pending (C5).
REPLY_TEXT_ONBOARDING = "Hi! Forward a supplier invoice photo here and I'll read it for you."
# Unsupported inbound media type.
REPLY_UNSUPPORTED_TYPE = (
    "I can only read photos or PDF invoices for now - please forward the invoice as a photo."
)
# Not-an-invoice decline (memes, chat screenshots).
REPLY_NOT_INVOICE = (
    "That doesn't look like a supplier invoice, so I'll leave it - forward an "
    "invoice photo and I'll read it."
)
# Z-report decline (sales reports arrive M8).
REPLY_Z_REPORT = "I read supplier invoices for now - sales reports are coming soon."
# Extraction failure (plan.md §5 layer 6: one message, never a dead end).
REPLY_EXTRACTION_FAILED = "Couldn't read this one - try a straighter photo, or type the total."

# --- closing lines --------------------------------------------------------

CLOSING_ALL_GREEN = "Reply OK to confirm."
CLOSING_WITH_AMBERS = "Reply with fixes (like: line 4 qty 16) or OK to confirm the rest."
# Cash hold (WP-24, PRD §21): the distinction is captured now; approval UI is M7.
CASH_HOLD_NOTE = "This one is marked cash, so it needs the owner's approval before it's recorded."

OVERFLOW_LINE = "...and {count} more to check on the review screen."


class PriceAlert(BaseModel):
    """One price movement for the extraction reply (the demo's money moment).

    WP-23 computes these against the snapped item's last_price; this module
    only renders them. Falling prices render too - good news is still signal.
    """

    model_config = ConfigDict(extra="forbid")

    item_name: str
    prev_price: Decimal
    new_price: Decimal
    currency: str = DEFAULT_CURRENCY

    @property
    def direction(self) -> Literal["up", "down"]:
        return "up" if self.new_price >= self.prev_price else "down"

    @property
    def delta(self) -> Decimal:
        return abs(self.new_price - self.prev_price)


def render_price_alert(alert: PriceAlert) -> str:
    """E.g. 'Milk Powder 2.5kg up AED 4.00 (50.50 to 54.50) since your last
    purchase.'"""
    return (
        f"{alert.item_name} {alert.direction} {alert.currency} {_money(alert.delta)} "
        f"({_money(alert.prev_price)} to {_money(alert.new_price)}) since your last purchase."
    )


def summary_line(invoice: ExtractedInvoice) -> str:
    """Supplier (or 'supplier unknown'), line count, total (or 'unreadable')."""
    count = len(invoice.lines)
    line_word = "line" if count == 1 else "lines"
    supplier = invoice.supplier_name or "supplier unknown"
    if invoice.total is None:
        total_part = "total unreadable"
    else:
        total_part = f"total {_currency(invoice)} {_money(invoice.total)}"
    return f"Read it: {supplier}, {count} {line_word}, {total_part}."


def compose_invoice_reply(
    invoice: ExtractedInvoice, validation: ValidationResult, alerts: list[PriceAlert]
) -> str:
    """The extraction reply: summary, price alerts, at most
    MAX_AMBER_QUESTIONS amber-field questions (most material first, overflow
    deferred to the review screen), then the confirm prompt."""
    closing = CLOSING_WITH_AMBERS if _has_ambers(validation) else CLOSING_ALL_GREEN
    return _compose(invoice, validation, alerts, closing)


def compose_cash_hold_reply(
    invoice: ExtractedInvoice, validation: ValidationResult, alerts: list[PriceAlert]
) -> str:
    """The extraction reply for a cash invoice held as needs_review (WP-24):
    same body, but the closing notes the owner-approval hold instead of
    inviting an OK - a cash invoice cannot confirm from chat."""
    return _compose(invoice, validation, alerts, CASH_HOLD_NOTE)


# --- internals ------------------------------------------------------------


def _compose(
    invoice: ExtractedInvoice,
    validation: ValidationResult,
    alerts: list[PriceAlert],
    closing: str,
) -> str:
    parts = [summary_line(invoice)]
    parts.extend(render_price_alert(alert) for alert in alerts)
    questions = _amber_questions(invoice, validation)
    parts.extend(questions[:MAX_AMBER_QUESTIONS])
    overflow = len(questions) - MAX_AMBER_QUESTIONS
    if overflow > 0:
        parts.append(OVERFLOW_LINE.format(count=overflow))
    parts.append(closing)
    return "\n".join(parts)


def _has_ambers(validation: ValidationResult) -> bool:
    return validation.document.status is FieldStatus.AMBER or any(
        check.status is FieldStatus.AMBER for check in validation.lines
    )


def _amber_questions(invoice: ExtractedInvoice, validation: ValidationResult) -> list[str]:
    """One specific question per amber item, most material first: the
    document totals block before lines; lines by line_total descending, an
    unreadable line_total treated as most material of all."""
    questions: list[str] = []
    document_question = _document_question(invoice, validation)
    if document_question is not None:
        questions.append(document_question)

    def materiality(check: LineCheck) -> tuple[int, Decimal, int]:
        line_total = invoice.lines[check.line_index].line_total
        if line_total is None:
            return (0, Decimal("0"), check.line_index)
        return (1, -line_total, check.line_index)

    ambers = [check for check in validation.lines if check.status is FieldStatus.AMBER]
    for check in sorted(ambers, key=materiality):
        questions.append(_line_question(invoice.lines[check.line_index], check))
    return questions


def _document_question(invoice: ExtractedInvoice, validation: ValidationResult) -> str | None:
    doc = validation.document
    if doc.status is FieldStatus.GREEN:
        return None
    if invoice.total is None:
        return "I couldn't read the invoice total - what does it say?"
    if doc.arith is CheckStatus.FAILED and doc.expected is not None and doc.extracted is not None:
        # C4 tries both a VAT-exclusive and a VAT-inclusive reading before
        # reaching here, so neither fits and we must not assert which one the
        # invoice meant. State the two figures and let the sender arbitrate.
        line_sum = doc.line_sum if doc.line_sum is not None else doc.expected
        return (
            f"The totals don't add up (the lines come to {_money(line_sum)} "
            f"but the invoice total says {_money(doc.extracted)}) - which is right?"
        )
    if (
        doc.subtotal_check is CheckStatus.FAILED
        and doc.line_sum is not None
        and invoice.subtotal is not None
    ):
        return (
            f"The subtotal doesn't match the lines (they add up to {_money(doc.line_sum)} "
            f"but the subtotal says {_money(invoice.subtotal)}) - which is right?"
        )
    # Amber only because line-level problems taint the totals (failed lines,
    # or unreadable line totals): the line questions carry it - a document
    # question here would spend a slot restating them.
    return None


def _line_question(line: ExtractedLine, check: LineCheck) -> str:
    n = check.line_index + 1
    if (
        check.arith is CheckStatus.FAILED
        and line.qty is not None
        and line.unit_price is not None
        and check.expected is not None
        and check.extracted is not None
    ):
        return (
            f"Line {n}: the math doesn't add up ({_qty(line.qty)} x {_money(line.unit_price)} "
            f"= {_money(check.expected)} but the line says {_money(check.extracted)}) "
            "- which is right?"
        )
    if line.qty is None:
        return f"Line {n}: I couldn't read the quantity - how many were delivered?"
    if line.unit_price is None:
        return f"Line {n}: I couldn't read the unit price - what price was charged?"
    if line.line_total is None:
        return f"Line {n}: I couldn't read the line total - what does it say?"
    # Arithmetic passed but the line stayed amber: the WP-22 snapping hook
    # said this doesn't match the supplier's known items at a plausible price.
    return f'Line {n}: I couldn\'t match "{line.raw_name}" to your usual items - is it right?'


def _currency(invoice: ExtractedInvoice) -> str:
    return invoice.currency or DEFAULT_CURRENCY


def _money(amount: Decimal) -> str:
    """Exactly two decimals, always: Decimal('54.5') renders '54.50'."""
    return f"{amount:.2f}"


def _qty(qty: Decimal) -> str:
    """Quantities are not money: '12' stays '12', '2.5' stays '2.5'."""
    return format(qty.normalize(), "f")


# --- WP-21: confirm-flow messages ------------------------------------------
# Appended for the confirm flow (confirm.py); everything above is WP-20 and
# frozen. Same rules apply: deterministic English templates, zero generation,
# money always rendered with exactly two decimals.

# The one clarify for anything the parser rejects (plan.md §6 M2: never a
# dead end, never silence) - it teaches every accepted form.
REPLY_CLARIFY = (
    "Sorry, I didn't get that. Reply OK to confirm, or send fixes like: "
    "line 1 qty 16, line 2 price 4.50, line 1 name Basmati Rice, or total 745.76."
)

DISAMBIGUATION_FOOTER = "Reply with the number first, like: 1 OK, or 1 line 2 qty 16."

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class PendingInvoice(BaseModel):
    """One row of the C5 disambiguation list (newest first). received_at is
    already in the branch's local timezone - this module renders, it never
    converts."""

    model_config = ConfigDict(extra="forbid")

    supplier_name: str | None
    currency: str | None
    total: Decimal | None
    received_at: datetime.datetime


def compose_confirmation_ack(
    supplier_name: str | None, currency: str | None, total: Decimal | None
) -> str:
    """The receipt moment: what the "OK" bought. Supplier and total when
    readable, with the same fallbacks the summary line uses."""
    supplier = supplier_name or "supplier unknown"
    if total is None:
        return f"Confirmed - {supplier} invoice recorded. I'll watch these prices for you."
    money = f"{currency or DEFAULT_CURRENCY} {_money(total)}"
    return f"Confirmed - {supplier}, {money} recorded. I'll watch these prices for you."


def compose_disambiguation_reply(pending: list[PendingInvoice]) -> str:
    """C5: several invoices awaiting one sender's confirm - a numbered list
    (1 = newest); the sender resends with the number in front. Stateless by
    design: the numbering re-derives from the invoices on every message."""
    count = len(pending)
    invoice_word = "invoice" if count == 1 else "invoices"
    parts = [f"You have {count} {invoice_word} waiting - which one?"]
    for number, invoice in enumerate(pending, start=1):
        supplier = invoice.supplier_name or "supplier unknown"
        if invoice.total is None:
            total_part = "total unreadable"
        else:
            total_part = f"{invoice.currency or DEFAULT_CURRENCY} {_money(invoice.total)}"
        received = invoice.received_at
        stamp = f"{received.day} {_MONTHS[received.month - 1]} {received:%H:%M}"
        parts.append(f"{number}. {supplier}, {total_part}, {stamp}")
    parts.append(DISAMBIGUATION_FOOTER)
    return "\n".join(parts)


def compose_line_out_of_range(n: int, line_count: int) -> str:
    """A correction named a line the invoice doesn't have - point at the real
    count instead of a dead end."""
    line_word = "line" if line_count == 1 else "lines"
    return (
        f"This invoice has {line_count} {line_word}, so I can't fix line {n} - "
        "check the line number and resend."
    )
