"""Reading printed money into exact Decimals (C4).

The extraction schema takes money as a string so nothing becomes a float on
the way in, which makes this the one place the printed form is interpreted.
"""

import pytest

from faida_api.extraction.money import parse_money
from faida_api.extraction.schema import ExtractedInvoice


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        # The model is told to copy exactly as printed, so it does - currency
        # symbol and all. This is what broke the first v2 live run.
        ("AED 332.00", "332.00"),
        ("332.00 AED", "332.00"),
        ("د.إ 45.00", "45.00"),  # the dirham sign carries its own dot
        ("SAR 1,240.50", "1240.50"),
        ("1,240.50", "1240.50"),
        ("  18.50  ", "18.50"),
        ("-92.00", "-92.00"),
        ("(41.70)", "-41.70"),  # accounting negative
        ("٤٥.٥٠", "45.50"),  # Arabic-Indic digits
        ("0.00", "0.00"),
    ],
)
def test_printed_money_parses_exactly(printed, expected):
    assert str(ExtractedInvoice(total=printed).total) == expected


def test_a_value_with_no_number_is_rejected_rather_than_guessed():
    """A money field we cannot read must fail loudly. Quietly returning zero
    would be a silent wrong number, which plan.md §5 forbids above all."""
    for unreadable in ("n/a", "", "illegible", "-"):
        with pytest.raises(ValueError):
            ExtractedInvoice(total=unreadable)


def test_non_strings_pass_through_untouched():
    from decimal import Decimal

    assert parse_money(Decimal("12.50")) == Decimal("12.50")
    assert parse_money(None) is None
