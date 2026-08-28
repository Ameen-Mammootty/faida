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

from .extraction.currency import currency_differs
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
# WP-26: with no total there is nothing to confirm. A missing line quantity is
# a small hole; the total is the invoice's headline number, and M5 divides it
# into plate costs where no photograph can catch a null. So the closing does
# not offer the "or OK to confirm the rest" that recorded a null total live on
# 2026-08-25 - it asks for the one number the invoice cannot be filed without.
CLOSING_TOTAL_NEEDED = "Send me the total and I'll finish this one off."

OVERFLOW_LINE = "...and {count} more to check on the review screen."

# WP-25: a missing invoice date or number is asked for, exactly like a failed
# line - never silently stored. The parenthetical teaches the correction form
# (confirm.py parses it) so the answer lands first time.
QUESTION_MISSING_DATE = (
    "I couldn't read the invoice date - what does it say? (reply like: date 5/7/26)"
)
QUESTION_MISSING_INVOICE_NO = (
    "I couldn't read the invoice number - what does it say? (reply like: invoice no 4471)"
)

# WP-28: the invoice is billed in money that is not the tenant's. Stated
# rather than guessed at, because both readings are possible - a genuine
# foreign-currency supplier, or a misread currency word - and only the sender
# knows which. Either way the consequence is named in the same breath: price
# memory is one bare number per item with no currency beside it, so a foreign
# invoice stays out of it (plan.md §2 rule 8 - per-row currency waits for a
# customer who needs multi-currency history).
QUESTION_CURRENCY_MISMATCH = (
    "This invoice is in {invoice_currency}, not your usual {tenant_currency} - is that right? "
    "I'll record it as printed and keep it out of your price history. "
    "(if it's a misread, reply: currency {tenant_currency})"
)

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


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
    """Supplier (or 'supplier unknown'), line count, total (or 'unreadable'),
    and the date when one was read - shown so a derived day-first reading can
    be challenged from the chat instead of discovered on the review screen
    (WP-27: a read date should be confirmable in the reply)."""
    count = len(invoice.lines)
    line_word = "line" if count == 1 else "lines"
    supplier = invoice.supplier_name or "supplier unknown"
    if invoice.total is None:
        total_part = "total unreadable"
    else:
        total_part = f"total {_currency(invoice)} {_money(invoice.total)}"
    dated = invoice.invoice_date
    dated_part = "" if dated is None else f", dated {_date_words(dated)}"
    return f"Read it: {supplier}, {count} {line_word}, {total_part}{dated_part}."


def compose_invoice_reply(
    invoice: ExtractedInvoice,
    validation: ValidationResult,
    alerts: list[PriceAlert],
    *,
    tenant_currency: str | None = None,
) -> str:
    """The extraction reply: summary, price alerts, at most
    MAX_AMBER_QUESTIONS amber-field questions (most material first, overflow
    deferred to the review screen), then the confirm prompt.

    `tenant_currency` is the money this tenant keeps its books in (WP-28); a
    mismatch adds its own question. None means "don't check" - the manual and
    test paths that have no tenant in hand."""
    if invoice.total is None:
        closing = CLOSING_TOTAL_NEEDED
    elif _has_ambers(invoice, validation, tenant_currency):
        closing = CLOSING_WITH_AMBERS
    else:
        closing = CLOSING_ALL_GREEN
    return _compose(invoice, validation, alerts, closing, tenant_currency)


def compose_cash_hold_reply(
    invoice: ExtractedInvoice,
    validation: ValidationResult,
    alerts: list[PriceAlert],
    *,
    tenant_currency: str | None = None,
) -> str:
    """The extraction reply for a cash invoice held as needs_review (WP-24):
    same body, but the closing notes the owner-approval hold instead of
    inviting an OK - a cash invoice cannot confirm from chat. The hold outranks
    WP-26's missing-total closing: this invoice is not confirmable from the
    phone at all, and the total question is already in the body."""
    return _compose(invoice, validation, alerts, CASH_HOLD_NOTE, tenant_currency)


def compose_missing_total_question(line_sum: Decimal | None, currency: str | None) -> str:
    """WP-26: the totals block was off the page (live, 2026-08-25).

    Show the one figure we can prove - the line sum, which every line's own
    arithmetic already checked - and ask the two facts C4 derives from a total
    and cannot derive without one: whether that figure is the whole invoice,
    and whether the prices already carry VAT. The answer forms are spelled out
    because the sender has to reach for one of them; a total assembled from
    them is stored as `reconstructed` (C8), never as a number read off a page.
    """
    if line_sum is None:
        # Some line total is unreadable too, so there is no sum worth showing:
        # ask for the printed figure plainly.
        return "I couldn't read the invoice total - what does it say? (reply like: total 976.50)"
    return f"I couldn't read the invoice total. {_total_facts(line_sum, currency)}"


def compose_total_needed_reply(line_sum: Decimal | None, currency: str | None) -> str:
    """The answer to a bare "OK" on an invoice with no total (WP-26): never
    silence, never the generic clarify, and never a confirmation - the same
    question again, with the reason it is being asked again."""
    if line_sum is None:
        return (
            "I can't record this one without the invoice total - what does it say? "
            "(reply like: total 976.50)"
        )
    return f"I can't record this one without the invoice total.\n{_total_facts(line_sum, currency)}"


def compose_vat_rate_reply(total: Decimal) -> str:
    """ "total 930 inc vat" says VAT is in there without saying how much. The
    GCC prints five different rates, so the rate is asked for rather than
    assumed (the same rule as the year in an ambiguous date)."""
    amount = _money(total)
    return (
        f'"inc vat" needs the rate before I can work out the VAT - send it like: '
        f"total {amount} inc vat 5%."
    )


def _total_facts(line_sum: Decimal, currency: str | None) -> str:
    amount = _money(line_sum)
    return (
        f"The lines come to {currency or DEFAULT_CURRENCY} {amount}. "
        "Is that the whole invoice, VAT included? "
        f"(reply like: total {amount} inc vat 5%, or total {amount} no vat, "
        "or the printed total: total 976.50)"
    )


# --- internals ------------------------------------------------------------


def _compose(
    invoice: ExtractedInvoice,
    validation: ValidationResult,
    alerts: list[PriceAlert],
    closing: str,
    tenant_currency: str | None = None,
) -> str:
    parts = [summary_line(invoice)]
    parts.extend(render_price_alert(alert) for alert in alerts)
    questions = _amber_questions(invoice, validation, tenant_currency)
    parts.extend(questions[:MAX_AMBER_QUESTIONS])
    overflow = len(questions) - MAX_AMBER_QUESTIONS
    if overflow > 0:
        parts.append(OVERFLOW_LINE.format(count=overflow))
    parts.append(closing)
    return "\n".join(parts)


def _has_ambers(
    invoice: ExtractedInvoice, validation: ValidationResult, tenant_currency: str | None = None
) -> bool:
    """Anything the reply will ask about - amber checks, a missing required
    header field (WP-25), or a foreign currency (WP-28) - flips the closing to
    the fixes form."""
    return bool(_amber_questions(invoice, validation, tenant_currency))


def _amber_questions(
    invoice: ExtractedInvoice, validation: ValidationResult, tenant_currency: str | None = None
) -> list[str]:
    """One specific question per amber item, most material first: the
    document totals block before lines; lines by line_total descending, an
    unreadable line_total treated as most material of all."""
    questions: list[str] = []
    document_question = _document_question(invoice, validation)
    if document_question is not None:
        questions.append(document_question)
    # WP-28: ranked directly under the totals block and above the required
    # fields, because it is the one question whose answer decides whether this
    # invoice's prices are allowed to move the baseline at all.
    if currency_differs(invoice.currency, tenant_currency):
        questions.append(
            QUESTION_CURRENCY_MISMATCH.format(
                invoice_currency=invoice.currency, tenant_currency=tenant_currency
            )
        )
    # WP-25: required-field asks sit above the line questions so they can
    # never overflow to the review screen - one document question plus these
    # two is exactly the cap. A null date or number must always be asked for.
    if invoice.invoice_date is None:
        questions.append(QUESTION_MISSING_DATE)
    if invoice.invoice_no is None:
        questions.append(QUESTION_MISSING_INVOICE_NO)

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
        # WP-26: the line sum is the one figure that can be shown here, and
        # validate.py already computed it under C4's rule (None the moment any
        # line total is unreadable) - so there is one implementation of it.
        return compose_missing_total_question(doc.line_sum, invoice.currency)
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


def _date_words(value: datetime.date) -> str:
    """'5 Jul 2026' - words, so there is no digit order to re-litigate."""
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"


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
    "line 1 qty 16, line 2 price 4.50, line 1 name Basmati Rice, total 745.76, "
    "date 5/7/26, invoice no 4471, or currency AED."
)

DISAMBIGUATION_FOOTER = "Reply with the number first, like: 1 OK, or 1 line 2 qty 16."


def compose_ambiguous_date_reply(text: str) -> str:
    """A date-shaped answer with no year ("date 5/7") could be more than one
    date, and a guessed year files the invoice into the wrong week of price
    history - ask for the year instead (C3/WP-27: never guess)."""
    return f'"{text}" needs a year to be a date - send it with the year, like: date 5/7/26.'


class PendingInvoice(BaseModel):
    """One row of the C5 disambiguation list (newest first). received_at is
    already in the branch's local timezone - this module renders, it never
    converts."""

    model_config = ConfigDict(extra="forbid")

    supplier_name: str | None
    currency: str | None
    total: Decimal | None
    received_at: datetime.datetime


PRICE_MEMORY_WATCHING = "I'll watch these prices for you."
# WP-28: the promise above would be a lie on a foreign-currency invoice, whose
# prices never reach the baseline. Saying so is the whole point - a hold the
# sender is not told about is indistinguishable from a bug.
PRICE_MEMORY_HELD = (
    "It's in {invoice_currency}, not {tenant_currency}, so I've kept it out of your price history."
)


def compose_confirmation_ack(
    supplier_name: str | None,
    currency: str | None,
    total: Decimal | None,
    *,
    tenant_currency: str | None = None,
) -> str:
    """The receipt moment: what the "OK" bought. Supplier and total when
    readable, with the same fallbacks the summary line uses."""
    supplier = supplier_name or "supplier unknown"
    if currency_differs(currency, tenant_currency):
        tail = PRICE_MEMORY_HELD.format(invoice_currency=currency, tenant_currency=tenant_currency)
    else:
        tail = PRICE_MEMORY_WATCHING
    if total is None:
        return f"Confirmed - {supplier} invoice recorded. {tail}"
    money = f"{currency or DEFAULT_CURRENCY} {_money(total)}"
    return f"Confirmed - {supplier}, {money} recorded. {tail}"


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
