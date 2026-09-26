"""The house wording (`words`): the rules a screen, a sentence, the brief and
the printout share, driven through the public functions."""

import datetime
import locale
from decimal import Decimal as D

import pytest

from faida_api import words


def test_a_headline_rounds_half_up_to_whole_dirhams_with_separators():
    assert words.money(D("1240.50"), "AED") == "AED 1,241"
    assert words.money(D("-1240.50"), "AED") == "AED -1,241"
    assert words.money(D("0.49"), "AED") == "AED 0"


def test_a_plate_figure_is_cut_at_the_fils_and_never_rounded_up():
    # D9: 6.415 is AED 6.41 on /menu, so it is AED 6.41 everywhere.
    assert words.plate_money(D("6.415"), "AED") == "AED 6.41"
    assert words.plate_money(D("6.419"), "AED") == "AED 6.41"
    assert words.plate_money(D("-0.079"), "AED") == "AED -0.07"


def test_a_price_per_unit_rounds_half_up_to_the_fils():
    assert words.price(D("2.305"), "AED") == "AED 2.31"
    assert f"{words.price(D('2.3'), 'AED')} {words.per_unit('kg')}" == "AED 2.30 per kg"
    assert words.per_unit("each") == "each"


def test_numbers_drop_the_tills_trailing_zeros():
    assert words.pct(D("60.5")) == "61%"
    assert words.qty(D("2.500")) == "2.5"
    assert words.qty(D("1240.000")) == "1240"
    assert words.portions(D("1240.000")) == "1,240"
    assert words.portions(D("2.500")) == "2.5"


def test_counts_and_names_read_as_a_person_says_them():
    assert words.count(1, "invoice") == "1 invoice"
    assert words.count(3, "invoice") == "3 invoices"
    assert words.count(2, "dish", "dishes") == "2 dishes"
    assert words.names(["Deira"]) == "Deira"
    assert words.names(["Deira", "Rolla", "Karama"]) == "Deira, Rolla and Karama"
    assert words.short_branch("Rolla Branch") == "Rolla"
    assert words.short_branch("Branch") == "Branch"


def test_dates_spell_the_same_months_under_any_locale():
    day = datetime.date(2026, 8, 31)
    before = locale.setlocale(locale.LC_TIME)
    try:
        for name in ("fr_FR.UTF-8", "ar_AE.UTF-8", "de_DE.UTF-8"):
            try:
                locale.setlocale(locale.LC_TIME, name)
            except locale.Error:
                continue
            assert words.short_date(day) == "31 Aug"
            assert words.long_date(day) == "31 Aug 2026"
            assert words.weekday_date(day) == "Mon 31 Aug"
    finally:
        locale.setlocale(locale.LC_TIME, before)


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@pytest.mark.parametrize(("month", "letters"), list(enumerate(MONTHS, 1)))
def test_every_month_has_its_three_letters(month, letters):
    assert words.short_date(datetime.date(2026, month, 1)) == f"1 {letters}"
