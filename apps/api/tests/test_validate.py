"""Unit tests for deterministic validation (plan.md §5 layers 2 and 5, C4).

Pure money math, no DB, no network. The invariant under test throughout:
a wrong value can never come out green.
"""

from decimal import Decimal

import pytest

from faida_api.extraction.schema import (
    ExtractedInvoice,
    ExtractedLine,
    LineKind,
    TaxTreatment,
)
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


# --- C4 two identities: VAT-inclusive and VAT-exclusive (WP-17) -------------
#
# The first real invoice through the live pipeline (Deira Cold Store T-0084417,
# 2026-08-23) was VAT-inclusive at UAE 5% and reconciled to the fil. Extraction
# was correct; the single `subtotal + tax = total` identity was wrong, and it
# was marking correct invoices amber. These lock in both readings.


def _deira() -> ExtractedInvoice:
    """The real invoice, to the fil: 10 lines summing to 706.65, tax 33.65
    already inside them, total 706.65. 706.65 / 1.05 = 673.00 exactly, and
    706.65 - 673.00 = 33.65, the printed tax."""
    priced = [
        ("2", "33.60"),
        ("2", "47.25"),
        ("6", "18.90"),
        ("8", "21.00"),
        ("1", "7.35"),
        ("2", "12.60"),
        ("24", "4.20"),
        ("2", "14.70"),
        ("1", "37.80"),
        ("3", "21.00"),
    ]
    lines = [_line(qty, price, str(Decimal(qty) * Decimal(price))) for qty, price in priced]
    return _invoice(lines, subtotal="706.65", tax="33.65", total="706.65")


def test_vat_inclusive_invoice_reconciles_green():
    doc = validate_invoice(_deira()).document
    assert doc.arith == CheckStatus.PASSED
    assert doc.status == FieldStatus.GREEN
    assert doc.tax_treatment == TaxTreatment.INCLUSIVE
    assert doc.vat_rate == Decimal("0.0500")
    # Nothing to ask about: the amber question this used to raise was the bug.
    assert doc.expected is None and doc.extracted is None


def test_vat_exclusive_invoice_still_reconciles_green():
    lines = [_line("2", "50.00", "100.00"), _line("1", "100.00", "100.00")]
    doc = validate_invoice(_invoice(lines, subtotal="200.00", tax="10.00", total="210.00")).document
    assert doc.arith == CheckStatus.PASSED
    assert doc.tax_treatment == TaxTreatment.EXCLUSIVE
    assert doc.status == FieldStatus.GREEN


def test_inclusive_invoice_printing_a_net_subtotal_is_not_read_as_exclusive():
    """The trap C4 calls out: such an invoice satisfies S + T = G and looks
    exclusive. Anchoring on the line sum - the only total verified line by
    line - is what keeps it honest."""
    lines = [_line("1", "105.00", "105.00"), _line("1", "105.00", "105.00")]
    doc = validate_invoice(_invoice(lines, subtotal="200.00", tax="10.00", total="210.00")).document
    assert doc.tax_treatment == TaxTreatment.INCLUSIVE
    assert doc.arith == CheckStatus.PASSED
    # The printed subtotal is the net figure, which is legitimate, not amber.
    assert doc.subtotal_check == CheckStatus.PASSED
    assert doc.status == FieldStatus.GREEN


def test_zero_tax_resolves_exclusive_and_stays_green():
    lines = [_line("1", "50.00", "50.00"), _line("1", "50.00", "50.00")]
    doc = validate_invoice(_invoice(lines, subtotal="100.00", tax="0.00", total="100.00")).document
    assert doc.arith == CheckStatus.PASSED
    assert doc.tax_treatment == TaxTreatment.EXCLUSIVE
    assert doc.vat_rate is None


def test_inclusive_at_an_unlisted_rate_still_reconciles_but_is_noted():
    """Lines summing to the total is the proof; matching a published rate is
    confirmation. An unfamiliar rate must not fail an invoice that adds up."""
    lines = [_line("1", "107.00", "107.00"), _line("1", "107.00", "107.00")]
    doc = validate_invoice(_invoice(lines, subtotal="214.00", tax="14.00", total="214.00")).document
    assert doc.arith == CheckStatus.PASSED
    assert doc.tax_treatment == TaxTreatment.INCLUSIVE
    assert any("unlisted rate" in note for note in doc.notes)


def test_totals_fitting_neither_identity_stay_amber():
    lines = [_line("2", "30.00", "60.00"), _line("4", "10.00", "40.00")]
    doc = validate_invoice(_invoice(lines, tax="5.00", total="120.00")).document
    assert doc.arith == CheckStatus.FAILED
    assert doc.status == FieldStatus.AMBER
    assert doc.tax_treatment is None
    assert doc.expected == Decimal("105.00")
    assert doc.extracted == Decimal("120.00")


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


# --- C4: discounts and non-stock charges (WP-18) ------------------------------
#
# Found by running the generated fixtures through the amended validator:
# EDGE-01 reads perfectly and still failed, because the line sum misses a trade
# discount exactly. Same shape as the VAT bug - correct extraction, wrong
# identity, spurious amber - and trade discounts are routine in GCC food supply.


def _edge01() -> ExtractedInvoice:
    """EDGE-01 to the fil: six stock lines (one a credit return) summing to
    834.00, a 25.00 delivery charge, a 41.70 trade discount which is 5% of the
    goods and not of the delivery, then 40.87 tax on 817.30, total 858.17."""
    stock = [
        ("5", "92.00", "460.00"),
        ("2", "44.00", "88.00"),
        ("4", "42.00", "168.00"),
        ("5", "18.00", "90.00"),
        ("6", "20.00", "120.00"),
        ("-1", "92.00", "-92.00"),
    ]
    lines = [_line(q, p, t) for q, p, t in stock]
    charge = _line("1", "25.00", "25.00")
    charge.line_kind = LineKind.CHARGE
    lines.append(charge)
    invoice = _invoice(lines, subtotal="834.00", tax="40.87", total="858.17")
    invoice.discount_total = Decimal("41.70")
    return invoice


def test_trade_discount_reconciles_green():
    doc = validate_invoice(_edge01()).document
    assert doc.arith == CheckStatus.PASSED
    assert doc.status == FieldStatus.GREEN
    assert doc.tax_treatment == TaxTreatment.EXCLUSIVE
    # Every line, charge included; and the goods-only figure a subtotal means.
    assert doc.line_sum == Decimal("859.00")
    assert doc.stock_sum == Decimal("834.00")


def test_discount_ignored_would_fail_the_same_invoice():
    """Guards the fix itself: drop the discount and the invoice must break by
    exactly 41.70, which is what was happening to every discounted invoice."""
    invoice = _edge01()
    invoice.discount_total = None
    doc = validate_invoice(invoice).document
    assert doc.arith == CheckStatus.FAILED
    assert doc.expected - doc.extracted == Decimal("41.70")


def test_discount_printed_negative_is_stored_as_a_magnitude():
    """The first live eval run (2026-08-24) caught the model returning
    discount_total -41.70 for EDGE-01, copying the sign the invoice prints.
    C4 states the identity as `line sum - discount + rounding`, so a negative
    D adds the discount instead: the invoice misses by 83.40 and a perfectly
    read page fails into amber. The schema canonicalizes the sign, so this can
    never depend on prompt wording."""
    printed_negative = ExtractedInvoice(discount_total=Decimal("-41.70"))
    assert printed_negative.discount_total == Decimal("41.70")

    invoice = _edge01()
    invoice.discount_total = Decimal("-41.70")
    doc = validate_invoice(ExtractedInvoice(**invoice.model_dump())).document
    assert doc.arith == CheckStatus.PASSED
    assert doc.status == FieldStatus.GREEN


def test_subtotal_may_be_printed_before_or_after_the_discount():
    invoice = _edge01()
    invoice.subtotal = Decimal("792.30")  # 834.00 - 41.70, equally legitimate
    assert validate_invoice(invoice).document.subtotal_check == CheckStatus.PASSED


def test_charge_lines_stay_out_of_the_subtotal_comparison():
    """The printed subtotal is the goods total: a delivery charge sits outside
    it, so including charges here would amber a correct invoice."""
    doc = validate_invoice(_edge01()).document
    assert doc.subtotal_check == CheckStatus.PASSED
    assert doc.stock_sum != doc.line_sum


def test_rounding_amount_absorbs_an_adjustment_larger_than_tolerance():
    """A fils-level rounding is already inside DOC_TOLERANCE_ABS and needs no
    field. This is for the invoice that rounds its total to the quarter dirham,
    where the adjustment is real money and has to be accounted for, not
    tolerated."""
    lines = [_line("1", "100.00", "100.00")]
    invoice = _invoice(lines, subtotal="100.00", tax="5.00", total="105.50")
    assert validate_invoice(invoice).document.arith == CheckStatus.FAILED
    invoice.rounding_amount = Decimal("0.50")
    assert validate_invoice(invoice).document.arith == CheckStatus.PASSED
