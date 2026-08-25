"""Cash or credit, decided by rule rather than by wording (plan.md §5 layer 5).

Whether a purchase was paid now or is owed later is not decoration: cash
purchases are held for owner approval (WP-24, PRD §21), so this field decides
who has to sign off on what. It was the last field still reading null on
invoices whose terms a human would read at a glance.

The cause was an instruction the prompt was obeying exactly - "payment_kind
only when the document states cash or credit" - so "Payment terms: 14 days"
returned null, because the page never prints the word "credit". A page does not
have to name the arrangement to state it.

So the model copies the terms *as printed* and the rule lives here, in code that
can be read, tested and argued with:

- an explicit cash marker ("cash", "cash on delivery", "نقدا") means cash
- a due period ("14 days", "net 30", "end of month", "credit") means credit
- anything else stays null, and the model's own reading is used instead

Printed terms win over the model's reading when both are present: the terms are
the harder evidence, and disagreement almost always means the model inferred
from layout while the page said otherwise. This mirrors how the currency is
handled - the model copies what is printed, one module derives the meaning.
"""

import re
from typing import Literal

PaymentKind = Literal["credit", "cash"]

# Checked before the credit markers, so "cash on delivery" is never read as a
# due period because it happens to contain a day word.
CASH_MARKERS = (
    "cash on delivery",
    "cash and carry",
    "cash",
    "cod",
    "c.o.d",
    "paid in full",
    "paid",
    "settled",
    "نقدا",
    "نقداً",
    "نقدي",
    "كاش",
    "مدفوع",
)

# A due period, however it is written. "days" catches "14 days", "30 Days
# from invoice date" and "payment within 7 days" alike.
CREDIT_MARKERS = (
    "credit",
    "days",
    "day",
    "net",
    "end of month",
    "eom",
    "due on",
    "due by",
    "payable by",
    "on account",
    "آجل",
    "أجل",
    "بالأجل",
    "شهر",
    "يوم",
)

_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _normalize(text: str) -> str:
    return " ".join(_WORD_RE.sub(" ", text.casefold()).split())


def kind_from_terms(terms_text: str | None) -> PaymentKind | None:
    """The arrangement a printed terms line states, or None when it states
    none we recognize."""
    if not terms_text:
        return None
    text = _normalize(terms_text)
    if not text:
        return None
    for marker in CASH_MARKERS:
        if _normalize(marker) in text:
            return "cash"
    for marker in CREDIT_MARKERS:
        if _normalize(marker) in text:
            return "credit"
    return None


def derive_payment_kind(
    terms_text: str | None, extracted_kind: PaymentKind | None
) -> PaymentKind | None:
    """The invoice's payment kind: printed terms first, the model's own reading
    second, null when neither settles it.

    Null is a real answer and stays available - guessing "credit" for an
    unmarked document would quietly route a cash purchase around the approval
    gate, which is the one thing this field must never do.
    """
    return kind_from_terms(terms_text) or extracted_kind
