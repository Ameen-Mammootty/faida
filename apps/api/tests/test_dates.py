"""The printed date and the calendar date it means (WP-27, C3).

The rules under test: GCC dates are day-first; a date with no year is
ambiguous and stays null (asked for, never guessed); an unrecognized printing
falls back to the model's own reading, an ambiguous one does not.
"""

import datetime

import pytest

from faida_api.extraction.dates import derive_invoice_date, parse_printed_date


def d(year: int, month: int, day: int) -> datetime.date:
    return datetime.date(year, month, day)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # ISO and year-first variants - the only shapes the corpus used to print.
        ("2026-07-05", d(2026, 7, 5)),
        ("2026/7/5", d(2026, 7, 5)),
        ("2026.07.05", d(2026, 7, 5)),
        # Day-first numerics, the GCC norm (WP-27 acceptance: 09/07/2026 is 9 July).
        ("09/07/2026", d(2026, 7, 9)),
        ("9-7-26", d(2026, 7, 9)),
        ("09.07.2026", d(2026, 7, 9)),
        ("5/7/26", d(2026, 7, 5)),  # AMD-01's printed date
        # Day over 12 proves the order either way round.
        ("25/12/2026", d(2026, 12, 25)),
        # Month-first is accepted only when it is the sole valid reading.
        ("07/25/2026", d(2026, 7, 25)),
        # Written months are unambiguous whichever side the day is on.
        ("9 July 2026", d(2026, 7, 9)),
        ("9th July 2026", d(2026, 7, 9)),
        ("July 9, 2026", d(2026, 7, 9)),
        ("09-Jul-2026", d(2026, 7, 9)),
        ("9 Jul 26", d(2026, 7, 9)),
        ("14 SEPT 2026", d(2026, 9, 14)),
        # The date is found inside the cell, not required to be all of it.
        ("Date: 5/7/26", d(2026, 7, 5)),
        ("5/7/26 6:15 AM", d(2026, 7, 5)),
        # Arabic-Indic digits and transliterated Gregorian months.
        ("٥/٧/٢٠٢٦", d(2026, 7, 5)),
        ("٩ يوليو ٢٠٢٦", d(2026, 7, 9)),
    ],
)
def test_unambiguous_printings_resolve(text: str, expected: datetime.date):
    parsed = parse_printed_date(text)
    assert parsed.date == expected
    assert not parsed.ambiguous


@pytest.mark.parametrize("text", ["5/7", "05-07", "9 July", "July 9", "٥/٧"])
def test_a_date_with_no_year_is_ambiguous_not_a_date(text: str):
    parsed = parse_printed_date(text)
    assert parsed.date is None
    assert parsed.ambiguous


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "  ",
        "no date shown",
        "13/13/26",  # no valid reading either way round
        "31/02/2026",  # not a calendar date
        "100000000000101",  # a TRN is not a date
        "1,240.50",  # money is not a date
        "55.99",  # digits with a separator but no day/month reading
        "July 2026",  # a month and year with no day
    ],
)
def test_everything_else_is_no_date_at_all(text: str | None):
    parsed = parse_printed_date(text)
    assert parsed.date is None
    assert not parsed.ambiguous


def test_two_digit_years_land_in_this_century():
    assert parse_printed_date("1/1/00").date == d(2000, 1, 1)
    assert parse_printed_date("31/12/99").date == d(2099, 12, 31)


def test_derivation_printed_text_outranks_the_given_date():
    # A month-first reading arrived alongside; the day-first rule in code wins.
    assert derive_invoice_date("09/07/2026", d(2026, 9, 7)) == d(2026, 7, 9)


def test_derivation_an_ambiguous_printing_nulls_the_given_date():
    # Whatever else claims to know what "5/7" means was guessing too (C3).
    assert derive_invoice_date("5/7", d(2026, 7, 5)) is None


def test_derivation_falls_back_to_the_given_date_when_text_is_absent_or_unknown():
    # No printed text: the date set directly (manual entry, truth) stands.
    assert derive_invoice_date(None, d(2026, 8, 20)) == d(2026, 8, 20)
    # A printing these rules do not know (say, Hijri) with a date alongside
    # (a replayed old recording): the date stands rather than being nulled.
    assert derive_invoice_date("15 Muharram 1448", d(2026, 7, 1)) == d(2026, 7, 1)
    assert derive_invoice_date(None, None) is None
