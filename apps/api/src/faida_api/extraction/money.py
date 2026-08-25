"""Reading a printed money value into an exact Decimal (C4).

Invoices print amounts the way people read them, not the way a parser wants
them: "AED 332.00", "1,240.50", "‎د.إ 45.00", "(41.70)" for a credit, and in
Arabic-Indic digits on plenty of GCC paperwork. The extraction schema takes
money as a string precisely so nothing becomes a float on the way in, which
leaves this module as the one place that turns the printed form into a number.

Everything here is a change of representation, never of value. A string that
does not contain a number is returned untouched so the schema raises a clear
error, because a money field we cannot read must fail loudly - guessing zero
would be a silent wrong number, which plan.md §5 forbids above all else.
"""

import re
from decimal import Decimal, InvalidOperation

# ٠-٩ (Arabic-Indic) and ۰-۹ (Extended Arabic-Indic), both seen on GCC invoices.
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
# Accounting negatives: "(41.70)" is -41.70 on every ledger ever printed.
_PARENTHESIZED = re.compile(r"^\((.*)\)$")
# The number is found, not carved out by deleting everything else: the dirham
# sign "د.إ" carries its own dot, and stripping non-digits would have turned
# "د.إ 45.00" into ".45.00".
_NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")
_HAS_DIGIT = re.compile(r"\d")


def parse_money(value: object) -> object:
    """Normalize a printed money string; anything else passes through.

    Returned as a string for Pydantic to turn into a Decimal, so this module
    never has to decide what an unreadable value means.
    """
    if not isinstance(value, str):
        return value
    text = value.strip().translate(_ARABIC_DIGITS)
    if not _HAS_DIGIT.search(text):
        return value  # no number in it: let the schema reject it, loudly

    negative = False
    parenthesized = _PARENTHESIZED.match(text)
    if parenthesized:
        negative, text = True, parenthesized.group(1)

    number = _NUMBER.search(text)
    if number is None:
        return value
    # Thousands separators go; the decimal point stays. GCC invoices use the
    # English convention.
    found = number.group(0).replace(",", "")
    sign = "-" if found.startswith("-") or negative else ""
    digits = found.lstrip("+-")
    try:
        Decimal(sign + digits)
    except InvalidOperation:
        return value
    return sign + digits
