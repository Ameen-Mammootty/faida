"""normalize_currency: printed currency marks become ISO codes (found live
2026-08-24, when a real invoice replied "total dirhams 402.00")."""

import pytest

from faida_api.extraction.currency import (
    SAUDI_RIYAL_SIGN,
    UAE_DIRHAM_SIGN,
    normalize_currency,
)


@pytest.mark.parametrize(
    ("printed", "code"),
    [
        ("dirhams", "AED"),
        ("Dirham", "AED"),
        ("Dhs.", "AED"),
        ("DH", "AED"),
        ("UAE Dirhams", "AED"),
        ("(AED)", "AED"),
        ("aed", "AED"),
        ("د.إ", "AED"),
        ("درهم", "AED"),
        (UAE_DIRHAM_SIGN, "AED"),
        (f"{UAE_DIRHAM_SIGN} ", "AED"),
        ("SAR", "SAR"),
        ("SR", "SAR"),
        ("Saudi Riyals", "SAR"),
        ("ر.س", "SAR"),
        (SAUDI_RIYAL_SIGN, "SAR"),
        ("QAR", "QAR"),
        ("KD", "KWD"),
        ("BD", "BHD"),
        ("Omani Rial", "OMR"),
        ("RO", "OMR"),
    ],
)
def test_printed_marks_map_to_iso_codes(printed: str, code: str):
    assert normalize_currency(printed) == code


def test_multi_token_strings_take_the_first_recognised_mark():
    assert normalize_currency("AED (Dhs)") == "AED"
    assert normalize_currency("Total in Dirhams") == "AED"


def test_unknown_text_passes_through_trimmed_never_invented():
    assert normalize_currency(" Dinar ") == "Dinar"  # KWD or BHD: do not guess
    assert normalize_currency("EUR") == "EUR"


def test_empty_and_none_stay_none():
    assert normalize_currency(None) is None
    assert normalize_currency("") is None
    assert normalize_currency(" . ") is None
