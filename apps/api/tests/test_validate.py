"""Unit tests for deterministic validation (plan.md §5 layers 2 and 5, C4).

Pure money math, no DB, no network. The invariant under test throughout:
a wrong value can never come out green.
"""

from decimal import Decimal

import pytest

from faida_api.extraction.schema import ExtractedInvoice, ExtractedLine
from faida_api.extraction.validate import CheckStatus, FieldStatus, validate_invoice


def _line(qty: str | None, price: str | None, total: str | None) -> ExtractedLine:
    return ExtractedLine(
        raw_name="item",
        qty=Decimal(qty) if qty is not None else None,
        unit_price=Decimal(price) if price is not None else None,
        line_total=Decimal(total) if total is not None else None,
    )


def _invoice(
    lines: list[ExtractedLine],
    subtotal: str | None = None,
    tax: str | None = None,
    total: str | None = None,
) -> ExtractedInvoice:
    return ExtractedInvoice(
        lines=lines,
        subtotal=Decimal(subtotal) if subtotal is not None else None,
        tax=Decimal(tax) if tax is not None else None,
        total=Decimal(total) if total is not None else None,
    )


# --- line arithmetic ---


def test_exact_line_passes_green():
    res = validate_invoice(_invoice([_line("12", "4.50", "54.00")], total="54.00"))
    lc = res.lines[0]
    assert lc.arith == CheckStatus.PASSED
    assert lc.status == FieldStatus.GREEN
    assert lc.expected is None and lc.extracted is None
    # Snapping does not exist yet (WP-22); its absence never blocks green.
    assert lc.snapped is None


def test_line_boundary_absolute_tolerance_passes():
    # diff 0.05 == LINE_TOLERANCE_ABS; pct tolerance (0.03125) is smaller.
    res = validate_invoice(_invoice([_line("2", "3.10", "6.25")]))
    assert res.lines[0].arith == CheckStatus.PASSED
    assert res.lines[0].status == FieldStatus.GREEN


def test_line_boundary_percentage_tolerance_passes():
    # Large line: 0.5% of 2000.00 is 10.00, well over the 0.05 absolute floor.
    res = validate_invoice(_invoice([_line("10", "201.00", "2000.00")]))
    assert res.lines[0].arith == CheckStatus.PASSED
    assert res.lines[0].status == FieldStatus.GREEN


def test_line_just_over_absolute_tolerance_fails_with_expected():
    res = validate_invoice(_invoice([_line("2", "3.10", "6.26")]))
    lc = res.lines[0]
    assert lc.arith == CheckStatus.FAILED
    assert lc.status == FieldStatus.AMBER
    assert lc.expected == Decimal("6.20")
    assert lc.extracted == Decimal("6.26")


def test_line_just_over_percentage_tolerance_fails_with_expected():
    res = validate_invoice(_invoice([_line("10", "201.01", "2000.00")]))
    lc = res.lines[0]
    assert lc.arith == CheckStatus.FAILED
    assert lc.status == FieldStatus.AMBER
    assert lc.expected == Decimal("2010.10")
    assert lc.extracted == Decimal("2000.00")


def test_three_decimal_unit_price_rounded_line_total_passes():
    # numeric(12,3) prices: 7 x 1.235 = 8.645, printed as 8.65.
    res = validate_invoice(_invoice([_line("7", "1.235", "8.65")]))
    assert res.lines[0].arith == CheckStatus.PASSED
    # Fractional qty as well: 2.5 x 3.775 = 9.4375, printed as 9.44.
    res = validate_invoice(_invoice([_line("2.5", "3.775", "9.44")]))
    assert res.lines[0].arith == CheckStatus.PASSED


@pytest.mark.parametrize(
    ("qty", "price", "total"),
    [
        (None, "4.50", "54.00"),
        ("12", None, "54.00"),
        ("12", "4.50", None),
    ],
)
def test_missing_line_value_is_indeterminate_and_amber(qty, price, total):
    res = validate_invoice(_invoice([_line(qty, price, total)]))
    lc = res.lines[0]
    assert lc.arith == CheckStatus.INDETERMINATE
    assert lc.status == FieldStatus.AMBER
    assert lc.expected is None and lc.extracted is None


# --- document arithmetic ---


def test_document_all_consistent_is_green():
    lines = [_line("2", "30.00", "60.00"), _line("4", "10.00", "40.00")]
    res = validate_invoice(_invoice(lines, subtotal="100.00", tax="5.00", total="105.00"))
    doc = res.document
    assert doc.arith == CheckStatus.PASSED
    assert doc.subtotal_check == CheckStatus.PASSED
    assert doc.status == FieldStatus.GREEN
    assert doc.line_sum == Decimal("100.00")
    assert doc.notes == []


def test_document_boundary_tolerance():
    lines = [_line("1", "100.00", "100.00")]
    res = validate_invoice(_invoice(lines, tax="5.00", total="105.10"))
    assert res.document.arith == CheckStatus.PASSED  # diff exactly 0.10
    res = validate_invoice(_invoice(lines, tax="5.00", total="105.11"))
    assert res.document.arith == CheckStatus.FAILED


def test_missing_tax_treated_as_zero_with_note():
    lines = [_line("1", "10.00", "10.00"), _line("1", "5.00", "5.00")]
    res = validate_invoice(_invoice(lines, total="15.00"))
    doc = res.document
    assert doc.arith == CheckStatus.PASSED
    assert any("tax" in note for note in doc.notes)


def test_tax_inclusive_mismatch_fails_document_check():
    # Total copied tax-inclusive style: equals the line sum, ignoring tax.
    lines = [_line("2", "30.00", "60.00"), _line("4", "10.00", "40.00")]
    res = validate_invoice(_invoice(lines, tax="5.00", total="100.00"))
    doc = res.document
    assert doc.arith == CheckStatus.FAILED
    assert doc.status == FieldStatus.AMBER
    assert doc.expected == Decimal("105.00")
    assert doc.extracted == Decimal("100.00")


def test_subtotal_disagreeing_with_line_sum_is_never_green():
    # Total reconciles against the line sum, but the extracted subtotal is off:
    # something is wrong somewhere, so the totals block must stay amber.
    lines = [_line("2", "30.00", "60.00"), _line("4", "10.00", "40.00")]
    res = validate_invoice(_invoice(lines, subtotal="90.00", tax="5.00", total="105.00"))
    doc = res.document
    assert doc.arith == CheckStatus.PASSED
    assert doc.subtotal_check == CheckStatus.FAILED
    assert doc.status == FieldStatus.AMBER


def test_failed_line_keeps_document_amber_even_when_total_reconciles():
    # The total matches the line sum, but that sum contains a line that failed
    # its own arithmetic - if the misread number is the line_total, the total
    # is unverified, so the totals block must not go green.
    res = validate_invoice(_invoice([_line("2", "3.10", "6.26")], total="6.26"))
    doc = res.document
    assert doc.arith == CheckStatus.PASSED
    assert doc.status == FieldStatus.AMBER


def test_indeterminate_lines_do_not_block_a_reconciled_document():
    # Delivery-note style: only line totals printed. sum == total is still two
    # independent readings agreeing, so the totals block may be green while
    # every line stays amber on its own missing qty/price.
    lines = [_line(None, None, "10.00"), _line(None, None, "5.00")]
    res = validate_invoice(_invoice(lines, tax="0", total="15.00"))
    assert all(lc.status == FieldStatus.AMBER for lc in res.lines)
    assert res.document.arith == CheckStatus.PASSED
    assert res.document.status == FieldStatus.GREEN


def test_missing_total_makes_document_check_indeterminate():
    lines = [_line("1", "10.00", "10.00")]
    res = validate_invoice(_invoice(lines, tax="0.50"))
    doc = res.document
    assert doc.arith == CheckStatus.INDETERMINATE
    assert doc.status == FieldStatus.AMBER


def test_missing_line_total_makes_document_check_indeterminate():
    # An unknown line sum must never let the total reconcile by accident.
    lines = [_line("1", "10.00", "10.00"), _line("2", "5.00", None)]
    res = validate_invoice(_invoice(lines, tax="0", total="10.00"))
    doc = res.document
    assert doc.arith == CheckStatus.INDETERMINATE
    assert doc.status == FieldStatus.AMBER
    assert doc.line_sum is None


def test_empty_lines_list():
    res = validate_invoice(_invoice([]))
    assert res.lines == []
    assert res.document.arith == CheckStatus.INDETERMINATE  # no total either
    # With a total present, an empty line sum genuinely fails to reconcile.
    res = validate_invoice(_invoice([], total="50.00"))
    assert res.document.arith == CheckStatus.FAILED
    assert res.document.status == FieldStatus.AMBER
    assert res.document.line_sum == Decimal("0")


def test_document_where_every_check_is_indeterminate():
    res = validate_invoice(_invoice([ExtractedLine(raw_name="smudged")]))
    assert res.lines[0].arith == CheckStatus.INDETERMINATE
    assert res.lines[0].status == FieldStatus.AMBER
    doc = res.document
    assert doc.arith == CheckStatus.INDETERMINATE
    assert doc.subtotal_check == CheckStatus.INDETERMINATE
    assert doc.status == FieldStatus.AMBER
