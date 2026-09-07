"""WP-20: the WhatsApp reply composer (plan.md §6 M2, §7.3), in the card
look decided with the founder on 2026-09-07 (WP-125).

Every message the product sends is a deterministic English template - zero
generation, per plan.md §3 (language decision). Pure functions over the
extraction pipeline's output types (§5 layers 5-6): same inputs, same bytes;
no I/O, no clock, no randomness. Money is Decimal end to end (C4) and always
renders with exactly two decimals in the invoice currency (default AED).

The look is WhatsApp's own markup, applied through the helpers below and
never inline: bold for the supplier, the total, the field label at the head
of a question and the OK in a closing; code for anything the sender is meant
to type; italic only for the filing note; one blank line between sections
and never a heading without a body. Five icons, fixed, and never alone -
each precedes a word that carries the same meaning, the way the screen pairs
colour with a label. The closing is always the last line, so the filing note
and the duplicate note are inputs to the composer, never appended by a
caller. Every user-supplied name passes through `plain`, so a stray asterisk
in a supplier's name cannot open a bold run.

Integration (next wave) swaps the plain M1 constants in pipeline.py and
worker.py for the exports here. WP-21 parses the replies these questions
invite; WP-23 constructs the PriceAlert values this module only renders.
"""

import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .extraction.currency import currency_differs
from .extraction.schema import ExtractedInvoice, ExtractedLine
from .extraction.validate import CheckStatus, FieldStatus, LineCheck, ValidationResult

DEFAULT_CURRENCY = "AED"

# At most this many amber-field questions per reply; the rest overflow to the
# review screen (plan.md §5 layer 5: amber drives one specific question).
MAX_AMBER_QUESTIONS = 3

# --- markup ---------------------------------------------------------------
# The five icons. Each is always followed by a word that says the same thing
# (colour never carries meaning alone, and neither does a glyph). The last
# two are two code points each - the symbol and the emoji presentation
# selector - so tests compare through these names, never a pasted character.

ICON_DONE = "✅"  # read, confirmed, recorded
ICON_UP = "\U0001f4c8"  # a price up
ICON_DOWN = "\U0001f4c9"  # a price down
ICON_CHECK = "⚠️"  # please check; a note worth checking; a refusal
ICON_HELD = "⏸️"  # held: a cash hold, a duplicate hold

# What WhatsApp reads as formatting. A supplier called "A*B" must not open a
# bold run, so these are stripped from every user-supplied value. The
# underscore stays: WhatsApp italicises only a run that opens at a word start
# and closes at a word end, a name is wrapped whole in *...*, and
# "MILK_PWDR 2.5KG" is an item code that has to survive.
_DELIMITERS = str.maketrans("", "", "*~`")


def bold(text: str) -> str:
    return f"*{text}*"


def italic(text: str) -> str:
    return f"_{text}_"


def code(text: str) -> str:
    return f"`{text}`"


def plain(value: str | None, fallback: str) -> str:
    """A user-supplied value made safe to sit inside or beside markup: the
    delimiter characters gone, whitespace collapsed (a bold run cannot span a
    line break), and the fallback when nothing is left."""
    if value is None:
        return fallback
    cleaned = " ".join(value.translate(_DELIMITERS).split())
    return cleaned or fallback


def _join_sections(sections: list[list[str]]) -> str:
    """Sections separated by one blank line; an empty section is dropped, so
    there is never a heading over nothing and never two blank lines."""
    return "\n\n".join("\n".join(lines) for lines in sections if lines)


UNKNOWN_SUPPLIER = "Supplier unknown"


class Reply(BaseModel):
    """What the worker sends: the words, and the WhatsApp id of the invoice
    photo the words are about, when they are about one. A reply quotes the
    photo it is about and nothing else (WP-125): the read-out, the ack, the
    holds and the refusals quote; onboarding, the clarify and the list of
    waiting papers do not."""

    model_config = ConfigDict(extra="forbid")

    body: str
    reply_to: str | None = None


class SimilarPaper(BaseModel):
    """The weaker WP-44 signal, as one argument: an earlier paper this one
    looks close to but not close enough to hold on."""

    model_config = ConfigDict(extra="forbid")

    supplier_name: str | None
    invoice_no: str | None
    received_on: datetime.date


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
# Extraction failure (plan.md §5 layer 6: one message, never a dead end). The
# way out is the review screen's manual entry, which is where it lives
# (plan.md §2 rule 5): the old "type the total" led to the onboarding reply,
# because a failed document has no invoice for a typed total to land on.
REPLY_EXTRACTION_FAILED = (
    f"{ICON_CHECK} Couldn't read this one - try a straighter photo, "
    "or enter it on the review screen."
)

# WP-72 (C2 as amended): a phone no branch is registered to. Sent once a day
# at most, and it says what to do without saying who else is on the system.
REPLY_UNKNOWN_SENDER = (
    "This number isn't set up yet, so I can't read invoices from it. "
    "Ask the owner to add this number, then forward the invoice again."
)

# --- headings and closing lines --------------------------------------------

READ_IT = f"{ICON_DONE} Read it"
PRICE_MOVES_HEADING = bold("Price moves since your last purchase")
CHECK_HEADING = f"{ICON_CHECK} {bold('Please check')}"

CLOSING_ALL_GREEN = f"Reply {bold('OK')} to confirm."
CLOSING_WITH_AMBERS = (
    f"Reply with fixes, like {code('line 4 qty 16')}, or {bold('OK')} to confirm the rest."
)
# Cash hold (WP-24, PRD §21): the owner approves cash on the review screen,
# with a reason (M7 WP-74); the phone can still correct the paper.
CASH_HOLD_NOTE = (
    f"{ICON_HELD} Marked cash, so it needs the owner's approval before it's recorded. "
    "I'll tell you here once the owner records it."
)
# An "OK" on a cash hold: the same fact, plus the one correction that lifts it
# (WP-74, C5 as amended) - a misread cash must be fixable from the phone that
# sent it, and this is where the sender learns how.
REPLY_CASH_HOLD_OK = (
    f"{CASH_HOLD_NOTE}\nIf it was actually paid on credit, reply {code('payment credit')}."
)


def compose_cash_approved_notice(supplier_name: str | None, invoice_no: str | None) -> str:
    """The branch phone's half of the loop the cash hold opened (WP-74): the
    owner recorded the paper, so the phone that forwarded it hears back, in
    two lines. Sent after the approval has committed and best-effort only:
    Meta accepts free text inside 24 h of the sender's last message, and an
    approval recorded a day later is still an approval - outside the window
    the branch learns nothing until M10's utility template."""
    supplier = bold(plain(supplier_name, UNKNOWN_SUPPLIER))
    return f"{ICON_DONE} Recorded\n{supplier}{_number_part(invoice_no)}, approved by the owner."


# A correction that arrived after the paper stopped being editable (confirmed
# or dismissed under it, from the screen). Rare, and honest: the fix was not
# applied, and the sender is told rather than shown a reply that pretends.
REPLY_CORRECTION_REFUSED = (
    f"{ICON_CHECK} This one is already {{status}}, so I can't change it any more."
)
# WP-26: with no total there is nothing to confirm. A missing line quantity is
# a small hole; the total is the invoice's headline number, and M5 divides it
# into plate costs where no photograph can catch a null. So the closing does
# not offer the "or OK to confirm the rest" that recorded a null total live on
# 2026-08-25 - it asks for the one number the invoice cannot be filed without.
CLOSING_TOTAL_NEEDED = "Send me the total and I'll finish this one off."

OVERFLOW_LINE = "...and {count} more to check on the review screen."

# WP-25: a missing invoice date or number is asked for, exactly like a failed
# line - never silently stored. The example teaches the correction form
# (confirm.py parses it) so the answer lands first time.
QUESTION_MISSING_DATE = (
    f"{bold('Date')}: I couldn't read the invoice date. What does it say? "
    f"Reply like {code('date 5/7/26')}."
)
QUESTION_MISSING_INVOICE_NO = (
    f"{bold('Invoice number')}: I couldn't read it. What does it say? "
    f"Reply like {code('invoice no 4471')}."
)

# WP-28: the invoice is billed in money that is not the tenant's. Stated
# rather than guessed at, because both readings are possible - a genuine
# foreign-currency supplier, or a misread currency word - and only the sender
# knows which. Either way the consequence is named in the same breath: price
# memory is one bare number per item with no currency beside it, so a foreign
# invoice stays out of it (plan.md §2 rule 8 - per-row currency waits for a
# customer who needs multi-currency history).
QUESTION_CURRENCY_MISMATCH = (
    bold("Currency") + ": this invoice is in {invoice_currency}, not your usual {tenant_currency}. "
    "Is that right? I'll record it as printed and keep it out of your price history. "
    "If it's a misread, reply " + code("currency {tenant_currency}") + "."
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

    @property
    def pct_change(self) -> Decimal | None:
        """The move as a share of the old price, signed, to one decimal,
        rounded half up; None on a zero baseline, which has no share."""
        if self.prev_price == 0:
            return None
        change = (self.new_price - self.prev_price) / self.prev_price * 100
        return change.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def render_price_alert(alert: PriceAlert) -> str:
    """E.g. '📈 Milk Powder 2.5kg up AED 4.00 (50.50 to 54.50, +7.9%)'. The
    heading above the alerts says "since your last purchase" once."""
    icon = ICON_UP if alert.direction == "up" else ICON_DOWN
    pct = alert.pct_change
    pct_part = "" if pct is None else f", {_signed_pct(pct)}"
    return (
        f"{icon} {plain(alert.item_name, 'Item')} {alert.direction} "
        f"{alert.currency} {_money(alert.delta)} "
        f"({_money(alert.prev_price)} to {_money(alert.new_price)}{pct_part})"
    )


def summary_block(invoice: ExtractedInvoice, booked_under: str | None = None) -> str:
    """The header: the read-it line, the supplier (or 'Supplier unknown'),
    the invoice number, the date in words and the line count on one line,
    the total, and the filing note when the paper is booked under another
    name. Shown so a derived day-first date reading can be challenged from
    the chat instead of discovered on the review screen (WP-27)."""
    return "\n".join(_summary_lines(invoice, booked_under))


def compose_invoice_reply(
    invoice: ExtractedInvoice,
    validation: ValidationResult,
    alerts: list[PriceAlert],
    *,
    tenant_currency: str | None = None,
    booked_under: str | None = None,
    similar_to: SimilarPaper | None = None,
) -> str:
    """The extraction reply: the header, the price moves, at most
    MAX_AMBER_QUESTIONS amber-field questions (most material first, overflow
    deferred to the review screen), the similar-paper note, then the confirm
    prompt - always last.

    `tenant_currency` is the money this tenant keeps its books in (WP-28); a
    mismatch adds its own question. None means "don't check" - the manual and
    test paths that have no tenant in hand. `booked_under` is the catalog
    name the paper is filed under when that is not the name printed on it
    (WP-87); `similar_to` the earlier paper it looks close to (WP-44)."""
    if invoice.total is None:
        closing = CLOSING_TOTAL_NEEDED
    elif _has_ambers(invoice, validation, tenant_currency):
        closing = CLOSING_WITH_AMBERS
    else:
        closing = CLOSING_ALL_GREEN
    return _compose(invoice, validation, alerts, closing, tenant_currency, booked_under, similar_to)


def compose_cash_hold_reply(
    invoice: ExtractedInvoice,
    validation: ValidationResult,
    alerts: list[PriceAlert],
    *,
    tenant_currency: str | None = None,
    booked_under: str | None = None,
    similar_to: SimilarPaper | None = None,
) -> str:
    """The extraction reply for a cash invoice held as needs_review (WP-24):
    same body, but the closing notes the owner-approval hold instead of
    inviting an OK - a cash invoice cannot confirm from chat. The hold outranks
    WP-26's missing-total closing: this invoice is not confirmable from the
    phone at all, and the total question is already in the body."""
    return _compose(
        invoice, validation, alerts, CASH_HOLD_NOTE, tenant_currency, booked_under, similar_to
    )


def compose_missing_total_question(line_sum: Decimal | None, currency: str | None) -> str:
    """WP-26: the totals block was off the page (live, 2026-08-25).

    Show the one figure we can prove - the line sum, which every line's own
    arithmetic already checked - and ask the two facts C4 derives from a total
    and cannot derive without one: whether that figure is the whole invoice,
    and whether the prices already carry VAT. The answer forms are spelled out
    because the sender has to reach for one of them; a total assembled from
    them is stored as `reconstructed` (C8), never as a number read off a page.
    """
    label = bold("Total")
    if line_sum is None:
        # Some line total is unreadable too, so there is no sum worth showing:
        # ask for the printed figure plainly.
        return f"{label}: I couldn't read it. What does it say? Reply like {code('total 976.50')}."
    return f"{label}: I couldn't read it. {_total_facts(line_sum, currency)}"


def compose_total_needed_reply(line_sum: Decimal | None, currency: str | None) -> str:
    """The answer to a bare "OK" on an invoice with no total (WP-26): never
    silence, never the generic clarify, and never a confirmation - the same
    question again, with the reason it is being asked again."""
    if line_sum is None:
        return (
            "I can't record this one without the invoice total. What does it say? "
            f"Reply like {code('total 976.50')}."
        )
    return f"I can't record this one without the invoice total.\n{_total_facts(line_sum, currency)}"


def compose_vat_rate_reply(total: Decimal) -> str:
    """ "total 930 inc vat" says VAT is in there without saying how much. The
    GCC prints five different rates, so the rate is asked for rather than
    assumed (the same rule as the year in an ambiguous date)."""
    example = code(f"total {_money(total)} inc vat 5%")
    return f'"inc vat" needs the rate before I can work out the VAT. Send it like {example}.'


def _total_facts(line_sum: Decimal, currency: str | None) -> str:
    amount = _money(line_sum)
    return (
        f"The lines come to {currency or DEFAULT_CURRENCY} {amount}. "
        "Is that the whole invoice, VAT included? "
        f"Reply like {code(f'total {amount} inc vat 5%')} or {code(f'total {amount} no vat')}, "
        f"or the printed total, like {code('total 976.50')}."
    )


# --- internals ------------------------------------------------------------


def _compose(
    invoice: ExtractedInvoice,
    validation: ValidationResult,
    alerts: list[PriceAlert],
    closing: str,
    tenant_currency: str | None = None,
    booked_under: str | None = None,
    similar_to: SimilarPaper | None = None,
) -> str:
    sections = [_summary_lines(invoice, booked_under)]
    if alerts:
        sections.append([PRICE_MOVES_HEADING, *(render_price_alert(alert) for alert in alerts)])
    questions = _amber_questions(invoice, validation, tenant_currency)
    if questions:
        check = [CHECK_HEADING, *(f"- {question}" for question in questions[:MAX_AMBER_QUESTIONS])]
        overflow = len(questions) - MAX_AMBER_QUESTIONS
        if overflow > 0:
            check.append(OVERFLOW_LINE.format(count=overflow))
        sections.append(check)
    if similar_to is not None:
        sections.append([render_duplicate_note(similar_to)])
    sections.append([closing])
    return _join_sections(sections)


def _summary_lines(invoice: ExtractedInvoice, booked_under: str | None) -> list[str]:
    lines = [READ_IT, bold(plain(invoice.supplier_name, UNKNOWN_SUPPLIER))]
    meta: list[str] = []
    number = plain(invoice.invoice_no, "")
    if number:
        meta.append(f"Invoice {number}")
    if invoice.invoice_date is not None:
        meta.append(_date_words(invoice.invoice_date))
    count = len(invoice.lines)
    meta.append(f"{count} {'line' if count == 1 else 'lines'}")
    lines.append(" · ".join(meta))
    if invoice.total is None:
        lines.append("Total unreadable")
    else:
        lines.append(f"Total {bold(f'{_currency(invoice)} {_money(invoice.total)}')}")
    if booked_under is not None:
        lines.append(render_booked_under(booked_under))
    return lines


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
    unreadable line_total treated as most material of all. Each is the body
    of one bullet, headed by the field it is about in bold."""
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
            f"{bold('Totals')}: the lines come to {_money(line_sum)} "
            f"but the invoice total says {_money(doc.extracted)}. Which is right?"
        )
    if (
        doc.subtotal_check is CheckStatus.FAILED
        and doc.line_sum is not None
        and invoice.subtotal is not None
    ):
        return (
            f"{bold('Subtotal')}: the lines add up to {_money(doc.line_sum)} "
            f"but the subtotal says {_money(invoice.subtotal)}. Which is right?"
        )
    # Amber only because line-level problems taint the totals (failed lines,
    # or unreadable line totals): the line questions carry it - a document
    # question here would spend a slot restating them.
    return None


def _line_question(line: ExtractedLine, check: LineCheck) -> str:
    n = check.line_index + 1
    label = bold(f"Line {n}")
    if (
        check.arith is CheckStatus.FAILED
        and line.qty is not None
        and line.unit_price is not None
        and check.expected is not None
        and check.extracted is not None
    ):
        return (
            f"{label}: {_qty(line.qty)} x {_money(line.unit_price)} = {_money(check.expected)} "
            f"but the line says {_money(check.extracted)}. Which is right?"
        )
    if line.qty is None:
        return (
            f"{label}: I couldn't read the quantity. How many were delivered? "
            f"Reply like {code(f'line {n} qty 16')}."
        )
    if line.unit_price is None:
        return (
            f"{label}: I couldn't read the unit price. What price was charged? "
            f"Reply like {code(f'line {n} price 4.50')}."
        )
    if line.line_total is None:
        return (
            f"{label}: I couldn't read the line total. What does it say? "
            f"Reply like {code(f'line {n} total 90.00')}."
        )
    # Arithmetic passed but the line stayed amber: the WP-22 snapping hook
    # said this doesn't match the supplier's known items at a plausible price.
    name = plain(line.raw_name, "this line")
    return f'{label}: I couldn\'t match "{name}" to your usual items. Is it right?'


def _currency(invoice: ExtractedInvoice) -> str:
    return invoice.currency or DEFAULT_CURRENCY


def _money(amount: Decimal) -> str:
    """Exactly two decimals, always: Decimal('54.5') renders '54.50'."""
    return f"{amount:.2f}"


def _signed_pct(pct: Decimal) -> str:
    """'+7.9%' or '-14.8%': the sign always shown, one decimal always."""
    sign = "-" if pct < 0 else "+"
    return f"{sign}{abs(pct):.1f}%"


def _date_words(value: datetime.date) -> str:
    """'5 Jul 2026' - words, so there is no digit order to re-litigate."""
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"


def _qty(qty: Decimal) -> str:
    """Quantities are not money: '12' stays '12', '2.5' stays '2.5'."""
    return format(qty.normalize(), "f")


def _number_part(invoice_no: str | None) -> str:
    """' 4471' after a supplier's name, or nothing when there is no number."""
    number = plain(invoice_no, "")
    return f" {number}" if number else ""


# --- WP-21: confirm-flow messages ------------------------------------------
# Appended for the confirm flow (confirm.py); everything above is WP-20 and
# frozen. Same rules apply: deterministic English templates, zero generation,
# money always rendered with exactly two decimals.

# The one clarify for anything the parser rejects (plan.md §6 M2: never a
# dead end, never silence) - it teaches every accepted form, one per line.
REPLY_CLARIFY = "\n".join(
    [
        f"Sorry, I didn't get that. Reply {bold('OK')} to confirm, or send a fix like:",
        f"- {code('line 1 qty 16')}",
        f"- {code('line 2 price 4.50')}",
        f"- {code('line 1 name Basmati Rice')}",
        f"- {code('total 745.76')}",
        f"- {code('date 5/7/26')}",
        f"- {code('invoice no 4471')}",
        f"- {code('currency AED')}",
        f"- {code('payment credit')}",
    ]
)

DISAMBIGUATION_FOOTER = (
    f"Reply with the number first, like {code('1 OK')} or {code('1 line 2 qty 16')}."
)


def compose_ambiguous_date_reply(text: str) -> str:
    """A date-shaped answer with no year ("date 5/7") could be more than one
    date, and a guessed year files the invoice into the wrong week of price
    history - ask for the year instead (C3/WP-27: never guess)."""
    typed = plain(text, "That")
    return (
        f'"{typed}" needs a year to be a date. Send it with the year, like {code("date 5/7/26")}.'
    )


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
    readable, with the same fallbacks the header uses."""
    supplier = bold(plain(supplier_name, UNKNOWN_SUPPLIER))
    if currency_differs(currency, tenant_currency):
        tail = PRICE_MEMORY_HELD.format(invoice_currency=currency, tenant_currency=tenant_currency)
    else:
        tail = PRICE_MEMORY_WATCHING
    if total is None:
        recorded = f"{supplier} invoice recorded."
    else:
        recorded = f"{supplier}, {currency or DEFAULT_CURRENCY} {_money(total)} recorded."
    return f"{ICON_DONE} Confirmed\n{recorded}\n{tail}"


def compose_disambiguation_reply(pending: list[PendingInvoice]) -> str:
    """C5: several invoices awaiting one sender's confirm - a numbered list
    (1 = newest); the sender resends with the number in front. Stateless by
    design: the numbering re-derives from the invoices on every message."""
    count = len(pending)
    invoice_word = "invoice" if count == 1 else "invoices"
    rows = []
    for number, invoice in enumerate(pending, start=1):
        supplier = bold(plain(invoice.supplier_name, UNKNOWN_SUPPLIER))
        if invoice.total is None:
            total_part = "total unreadable"
        else:
            total_part = f"{invoice.currency or DEFAULT_CURRENCY} {_money(invoice.total)}"
        received = invoice.received_at
        stamp = f"{received.day} {_MONTHS[received.month - 1]} {received:%H:%M}"
        rows.append(f"{number}. {supplier}, {total_part}, {stamp}")
    return _join_sections(
        [[f"You have {count} {invoice_word} waiting. Which one?"], rows, [DISAMBIGUATION_FOOTER]]
    )


def compose_line_out_of_range(n: int, line_count: int) -> str:
    """A correction named a line the invoice doesn't have - point at the real
    count instead of a dead end."""
    line_word = "line" if line_count == 1 else "lines"
    return (
        f"This invoice has {line_count} {line_word}, so I can't fix line {n} - "
        "check the line number and resend."
    )


# --- WP-44: duplicate invoice hold ------------------------------------------


def compose_duplicate_hold_reply(
    supplier_name: str | None,
    invoice_no: str | None,
    currency: str | None,
    total: Decimal | None,
    received_on: datetime.date,
) -> str:
    """The same paper sent twice is held, naming the earlier record - never
    silently double-counted, never silently dropped (WP-44). Replaces the
    extraction reply entirely: alerts and questions on a copy are noise."""
    supplier = bold(plain(supplier_name, UNKNOWN_SUPPLIER))
    money = "" if total is None else f" for {currency or DEFAULT_CURRENCY} {_money(total)}"
    return (
        f"{ICON_HELD} Already recorded\n"
        f"{supplier}{_number_part(invoice_no)}{money}, received {_date_words(received_on)}.\n"
        "I've held this copy so nothing is counted twice. "
        "If it really is a new invoice, confirm it on the review screen."
    )


def render_booked_under(supplier_name: str) -> str:
    """WP-87: whose price history this paper moves, when that is not the name
    printed on it - the filing note under the total, in italics, and written
    only when the two names differ: a line repeating the name already on the
    screen above it teaches nothing and costs the reader a line. No full
    stop, so "L.L.C." never doubles one."""
    return italic(f"Booked under {plain(supplier_name, 'another supplier')}")


def render_duplicate_note(similar: SimilarPaper) -> str:
    """The weaker WP-44 signal - the number alone, or the date and total,
    matches an earlier invoice but not enough to hold on: noted, never held,
    its own section above the closing."""
    supplier = plain(similar.supplier_name, "supplier unknown")
    return (
        f"{ICON_CHECK} This looks close to {supplier}{_number_part(similar.invoice_no)}, "
        f"received {_date_words(similar.received_on)}. Worth checking it isn't the same paper."
    )
