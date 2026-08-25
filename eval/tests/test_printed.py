"""Tests for the printed-page reader (WP-15/F8).

This module writes ground truth, so a silent mis-parse would poison every
score computed against it. The cross-check in convert_generated is the
backstop; these are the unit-level guarantees.

Run from the repo root: apps/api/.venv/bin/python -m pytest eval/tests -q
"""

import pathlib

import pytest

from eval.printed import PrintedPageError, parse_columns, parse_rows, split_description
from eval.printed import read as read_printed_page

# Verbatim from the generated prompts, so it must stay byte-exact; composed
# only so the source line fits.
COLUMNS_LINE = (
    "COLUMNS, left to right: # | Item code | Description | Qty | Unit | Pack size "
    "| Unit price AED | Amount AED"
)

TABLE = f"""\
DOCUMENT TITLE: TAX INVOICE
Payment terms: 14 days

{COLUMNS_LINE}

1 | GPS-TAH-2KG | Tahina Sesame Paste | 4 | tub | 2 kg | 46.00 | 184.00
2 | GPS-FRE-5KG | Frikeh Green Cracked Wheat | 2 | bag | 5 kg | 38.00 | 76.00
3 | - | Chilled delivery and cool box hire | 1 | service | - | 25.00 | 25.00

Delivery charge: AED 25.00
"""

RECEIPT = """\
Receipt No: T-0084417
Till: 03    Cashier: 118

RICE BASM 5KG
    2 x 33.60                67.20
"""


def write(tmp_path: pathlib.Path, name: str, text: str) -> pathlib.Path:
    case = tmp_path / name
    case.mkdir()
    (case / f"{name}.prompt.txt").write_text(text)
    return case


def test_printed_columns_are_read_as_printed_not_converted(tmp_path):
    """The regression this module exists for: the page prints "2 kg" and the
    generator models 2000 grams. Truth takes the page."""
    page = read_printed_page(write(tmp_path, "ALT-01", TABLE))
    assert page.has_table
    assert page.pack_size(0) == "2 kg"
    assert page.pack_size(1) == "5 kg"
    assert page.unit(0) == "tub"


def test_unit_column_never_resolves_to_unit_price():
    columns = parse_columns(TABLE)
    rows = parse_rows(TABLE, columns)
    assert len(rows) == 3
    # "Unit" and "Unit price AED" both contain "unit"; the exact heading wins.
    assert rows[0]["Unit"] == "tub"
    assert rows[0]["Unit price AED"] == "46.00"


def test_dash_placeholder_is_an_absence(tmp_path):
    """EDGE-01's charge row prints "-" for pack size; truth records None, not
    a literal dash."""
    page = read_printed_page(write(tmp_path, "EDGE-01", TABLE))
    assert page.pack_size(2) is None
    assert page.unit(2) == "service"


def test_a_page_with_no_table_states_no_unit(tmp_path):
    """TH-01 is a till receipt: no columns at all. That the page prints no
    unit is a fact, and truth must record its absence rather than borrow the
    generator's vocabulary."""
    page = read_printed_page(write(tmp_path, "TH-01", RECEIPT))
    assert not page.has_table
    assert page.unit(0) is None
    assert page.pack_size(0) is None


def test_payment_kind_reads_the_printed_terms(tmp_path):
    assert read_printed_page(write(tmp_path, "A", TABLE)).payment_kind() == "credit"
    cash = TABLE.replace("Payment terms: 14 days", "Payment terms: Cash on delivery")
    assert read_printed_page(write(tmp_path, "B", cash)).payment_kind() == "cash"
    # A receipt states no terms; the caller falls back to the document kind.
    assert read_printed_page(write(tmp_path, "C", RECEIPT)).payment_kind() is None


def test_bilingual_description_keeps_both_scripts():
    cell = "Unsalted Butter  (Arabic line directly under it: زبدة غير مملحة)"
    assert split_description(cell) == "Unsalted Butter زبدة غير مملحة"
    assert split_description("  Plain   Name  ") == "Plain Name"


def test_a_missing_prompt_is_an_error_not_an_empty_page(tmp_path):
    case = tmp_path / "GONE-01"
    case.mkdir()
    with pytest.raises(PrintedPageError, match="no prompt"):
        read_printed_page(case)


def test_a_misparsed_table_fails_the_case_instead_of_writing_truth(tmp_path):
    """The backstop: printed rows and modelled lines must describe the same
    invoice. If the parse slips, the case fails loudly - silently rewriting
    ground truth from a bad parse is the one outcome worse than not running."""
    import json

    from eval.convert_generated import convert

    case = write(tmp_path, "BAD-01", TABLE)
    (case / "BAD-01.expected.json").write_text(
        json.dumps(
            {
                "expected_document_type": "invoice",
                "expected_invoice_kind": "credit_purchase",
                "header": {"supplier_name": "Gulf Pantry", "invoice_total": "285.00"},
                "lines": [
                    # The printed table's row 1 is 184.00, not 999.00.
                    {
                        "description_raw": "Tahina",
                        "purchase_quantity": "4",
                        "unit_price": "46.00",
                        "line_total": "999.00",
                    },
                    {
                        "description_raw": "Frikeh",
                        "purchase_quantity": "2",
                        "unit_price": "38.00",
                        "line_total": "76.00",
                    },
                    {
                        "description_raw": "Delivery",
                        "purchase_quantity": "1",
                        "unit_price": "25.00",
                        "line_total": "25.00",
                    },
                ],
            }
        )
    )
    with pytest.raises(PrintedPageError, match="does not match"):
        convert(case)
