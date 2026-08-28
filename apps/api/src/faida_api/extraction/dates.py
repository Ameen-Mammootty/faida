"""The printed date, and the calendar date it means (WP-27, C3).

Al Aweer AAF 2214 arrived with its date plainly printed on the page and was
stored with a null date anyway: every corpus invoice prints `YYYY-MM-DD`, so
the one shape a GCC supplier is least likely to use was the only shape the
pipeline had ever been measured on. The model now copies the date exactly as
printed (C3 `invoice_date_text`) and this module derives the calendar date
from it - the same split as the printed currency word and its ISO code, and
the printed terms line and cash-or-credit: printed facts are copied, meaning
is derived in code that can be read, tested and argued with.

The rules, stated once:

- GCC dates are day-first: "09/07/2026" is 9 July 2026. When only one of the
  two numeric readings is a valid calendar date, that reading wins ("25/12"
  cannot be month-first); when both are valid, day-first is the convention.
- A date with no year is not a date. "5/7" stays null and the reply asks for
  it (WP-25); resolving it from today's clock would be a guess, and a guessed
  date files an invoice into the wrong week of price history.
- A printed form this module does not recognize resolves to null and becomes
  the same question - the wire carries no model-read calendar date to fall
  back on (the grammar budget fits exactly one date field, see the schema).
  The fallback in derive_invoice_date serves the paths that set the calendar
  date directly: manual entry, ground truth, and rows rebuilt from the
  database. An *ambiguous* printing never falls back - whatever else claims
  to know what "5/7" means was guessing too.
"""

import datetime
import re
from typing import NamedTuple

# ٠-٩ (Arabic-Indic) and ۰-۹ (Extended Arabic-Indic), both seen on GCC paperwork.
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

_MONTH_NAMES: dict[str, int] = {
    # English, full and short ("sept" included: receipts truncate).
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
    # Gregorian months as GCC invoices transliterate them.
    "يناير": 1,
    "فبراير": 2,
    "مارس": 3,
    "أبريل": 4, "ابريل": 4,
    "مايو": 5,
    "يونيو": 6,
    "يوليو": 7,
    "أغسطس": 8, "اغسطس": 8,
    "سبتمبر": 9,
    "أكتوبر": 10, "اكتوبر": 10,
    "نوفمبر": 11,
    "ديسمبر": 12,
}  # fmt: skip

# Longest first, so "june" is never eaten by "jun" leaving a stray "e".
_MONTH_ALTERNATION = "|".join(
    sorted((re.escape(name) for name in _MONTH_NAMES), key=len, reverse=True)
)

# Year-first: 2026-07-05, 2026/7/5, 2026.07.05. Unambiguous everywhere.
_YMD = re.compile(r"(?<![\d.])(20\d{2})([./-])(\d{1,2})\2(\d{1,2})(?![\d.])")
# Numeric with a trailing 2- or 4-digit year: 5/7/26, 09-07-2026, 9.7.2026.
_DMY = re.compile(r"(?<![\d.])(\d{1,2})([./-])(\d{1,2})\2(\d{4}|\d{2})(?![\d.])")
# Date-shaped with no year at all: 5/7. Recognized so it can be *asked about*.
_DM_NO_YEAR = re.compile(r"(?<![\d.])(\d{1,2})([./-])(\d{1,2})(?![\d./-])")
# 9 July 2026 / 9th Jul 26 / 09-Jul-2026 / ٩ يوليو ٢٠٢٦ - month names are
# unambiguous whichever side the day is on.
_D_MON_Y = re.compile(
    rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?[\s.,-]+({_MONTH_ALTERNATION})[\s.,-]+(\d{{4}}|\d{{2}})(?!\d)",
    re.IGNORECASE,
)
# July 9, 2026 / Jul 9 26.
_MON_D_Y = re.compile(
    rf"({_MONTH_ALTERNATION})[\s.,-]+(\d{{1,2}})(?:st|nd|rd|th)?[\s.,-]+(\d{{4}}|\d{{2}})(?!\d)",
    re.IGNORECASE,
)
# A named month and a day with no year: "9 July" / "July 9". Ambiguous.
_D_MON = re.compile(
    rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?[\s.,-]+({_MONTH_ALTERNATION})(?![\s.,-]*\d)",
    re.IGNORECASE,
)
_MON_D = re.compile(
    rf"({_MONTH_ALTERNATION})[\s.,-]+(\d{{1,2}})(?:st|nd|rd|th)?(?![\s.,-]*\d)",
    re.IGNORECASE,
)


class ParsedDate(NamedTuple):
    date: datetime.date | None
    # Date-shaped but unresolvable without guessing (no year). Distinct from
    # "no date here at all": an ambiguous printing must also null the model's
    # own reading, an unrecognized one must not.
    ambiguous: bool


_NO_DATE = ParsedDate(None, False)
_AMBIGUOUS = ParsedDate(None, True)


def _valid(year: int, month: int, day: int) -> datetime.date | None:
    """A real calendar date in the window paper invoices live in, or None.
    The century bound is what stops a stray "20.26" reading as a year."""
    if year < 100:
        year += 2000
    if not 2000 <= year <= 2099:
        return None
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _day_first(year: int, first: int, second: int) -> datetime.date | None:
    """The GCC convention: first/second is day/month. The swapped reading is
    used only when it is the *only* valid one - that is not a guess, it is
    the single date the digits can mean."""
    return _valid(year, second, first) or _valid(year, first, second)


def parse_printed_date(text: str | None) -> ParsedDate:
    """Read a printed date string into a calendar date, deterministically.

    The date is found inside the text, not required to be the whole of it -
    the model copies the date cell, and a date cell can print "Date: 5/7/26"
    or carry a time beside it.
    """
    if text is None:
        return _NO_DATE
    normalized = " ".join(text.translate(_ARABIC_DIGITS).split())
    if not normalized:
        return _NO_DATE

    if match := _YMD.search(normalized):
        year, _, month, day = match.groups()
        date = _valid(int(year), int(month), int(day))
        return ParsedDate(date, False) if date else _NO_DATE
    if match := _DMY.search(normalized):
        first, _, second, year = match.groups()
        date = _day_first(int(year), int(first), int(second))
        return ParsedDate(date, False) if date else _NO_DATE
    if match := _D_MON_Y.search(normalized):
        day, month_name, year = match.groups()
        date = _valid(int(year), _MONTH_NAMES[month_name.casefold()], int(day))
        return ParsedDate(date, False) if date else _NO_DATE
    if match := _MON_D_Y.search(normalized):
        month_name, day, year = match.groups()
        date = _valid(int(year), _MONTH_NAMES[month_name.casefold()], int(day))
        return ParsedDate(date, False) if date else _NO_DATE

    # No resolvable date. Date-shaped remnants are the ask-for-the-year case,
    # but only when the digits could actually be a day and a month - "55.99"
    # is not a date missing its year. 2000 is a leap year, so 29/2 stays
    # askable rather than dismissed.
    if match := _DM_NO_YEAR.search(normalized):
        first, _, second = match.groups()
        if _day_first(2000, int(first), int(second)) is not None:
            return _AMBIGUOUS
        return _NO_DATE
    if _D_MON.search(normalized) or _MON_D.search(normalized):
        return _AMBIGUOUS
    return _NO_DATE


def derive_invoice_date(
    date_text: str | None, extracted_date: datetime.date | None
) -> datetime.date | None:
    """The invoice's calendar date: the printed text first, the date given
    alongside second, null when the printing is ambiguous.

    Printed text outranks the given date for the same reason the terms line
    outranks the cash-or-credit call: the day-first rule must come from code,
    not from whichever convention a reader felt like on the day. The
    extraction wire never carries a calendar date, so on that path this is
    the only reader; `extracted_date` serves manual entry, ground truth, and
    invoices rebuilt from their rows.
    """
    parsed = parse_printed_date(date_text)
    if parsed.date is not None:
        return parsed.date
    if parsed.ambiguous:
        return None
    return extracted_date
