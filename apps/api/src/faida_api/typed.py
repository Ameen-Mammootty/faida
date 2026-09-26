"""Reading what a person typed: a number in a chat reply or a form field, and
a free-text field. The input side of `words` - reading, not writing.

Imports nothing from `faida_api`."""

import re
from decimal import Decimal

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def parse_number(text: str) -> Decimal | None:
    """A plain non-negative number, or None. A sentence-ending "16." or "16!"
    is still a number; a sign or NaN is not."""
    text = text.strip().rstrip(".!?")
    if _NUMBER_RE.fullmatch(text) is None:
        return None
    return Decimal(text)


def clean(value: str | None) -> str | None:
    """Trim a free-text field; a blank string means the field was not given."""
    if value is None:
        return None
    return value.strip() or None
