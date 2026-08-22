"""Scorer unit tests (WP-14): line alignment, fuzzy edges, Decimal-numeric
equality, and reconciliation tolerance boundaries.

Run from the repo root: apps/api/.venv/bin/python -m pytest eval/tests -q
"""

from decimal import Decimal

from eval.score import (
    aggregate,
    align_lines,
    fuzzy_equal,
    fuzzy_ratio,
    invoice_reconciles,
    score_case,
)
from faida_api.extraction.constants import (
    DOC_TOLERANCE_ABS,
    LINE_TOLERANCE_ABS,
)
from faida_api.extraction.schema import (
    Classification,
    ExtractedInvoice,
    ExtractedLine,
    ExtractionResult,
)


def line(
    raw_name: str,
    qty: str | None = None,
    unit_price: str | None = None,
    line_total: str | None = None,
    unit: str | None = None,
    pack_size: str | None = None,
) -> ExtractedLine:
    return ExtractedLine(
        raw_name=raw_name,
        qty=Decimal(qty) if qty is not None else None,
        unit=unit,
        pack_size=pack_size,
        unit_price=Decimal(unit_price) if unit_price is not None else None,
        line_total=Decimal(line_total) if line_total is not None else None,
    )


def invoice_result(lines: list[ExtractedLine], **headers) -> ExtractionResult:
    return ExtractionResult(
        classification=Classification.INVOICE,
        invoice=ExtractedInvoice(lines=lines, **headers),
    )


TRUTH_LINES = [
    line("Tomato Local Box 5kg", qty="4", unit_price="18.50", line_total="74.00", unit="box"),
    line("Cucumber 5kg", qty="2", unit_price="12.00", line_total="24.00", unit="box"),
    line("Onion Red 10kg", qty="1", unit_price="22.00", line_total="22.00", unit="bag"),
]


def test_alignment_extra_extracted_line_costs_precision_not_recall():
    extracted = TRUTH_LINES + [line("Delivery charge", qty="1", unit_price="5.00")]
    result = score_case(invoice_result(extracted), invoice_result(TRUTH_LINES))
    assert result["lines"]["matched"] == 3
    assert result["lines"]["recall"] == 1.0
    assert result["lines"]["precision"] == 0.75


def test_alignment_missing_line_costs_recall_not_precision():
    extracted = TRUTH_LINES[:2]
    result = score_case(invoice_result(extracted), invoice_result(TRUTH_LINES))
    assert result["lines"]["matched"] == 2
    assert result["lines"]["recall"] == 0.6667
    assert result["lines"]["precision"] == 1.0


def test_alignment_survives_reordering():
    extracted = list(reversed(TRUTH_LINES))
    pairs = align_lines(extracted, TRUTH_LINES)
    assert pairs == [(0, 2), (1, 1), (2, 0)]
    result = score_case(invoice_result(extracted), invoice_result(TRUTH_LINES))
    assert result["lines"]["recall"] == 1.0
    assert result["lines"]["precision"] == 1.0
    for tally in result["lines"]["fields"].values():
        assert tally == {"correct": 3, "total": 3}


def test_fuzzy_threshold_edges():
    # ratio 2*9/20 = 0.9 exactly: at the threshold, so it matches.
    assert fuzzy_ratio("abcdefghij", "abcdefghix") == 0.9
    assert fuzzy_equal("abcdefghij", "abcdefghix")
    # ratio 2*8/18 = 0.889: just below the threshold.
    assert fuzzy_ratio("abcdefghi", "abcdefghx") < 0.9
    assert not fuzzy_equal("abcdefghi", "abcdefghx")
    # Normalization: case and whitespace never count against the ratio.
    assert fuzzy_equal("  AL MADINA   TRADING ", "al madina trading")


def test_supplier_name_scored_fuzzy_but_invoice_no_exact():
    truth = invoice_result([], supplier_name="Al Madina Foodstuff Trading LLC", invoice_no="A-1")
    extracted = invoice_result(
        [], supplier_name="Al Madina Foodstuff Trading L.L.C", invoice_no="A-2"
    )
    fields = score_case(extracted, truth)["header_fields"]
    assert fields["supplier_name"] is True
    assert fields["invoice_no"] is False


def test_decimal_numeric_equality_across_string_forms():
    truth = invoice_result(
        [line("Karak Premix", qty="2", unit_price="27.25", line_total="54.50")],
        subtotal=Decimal("54.50"),
    )
    extracted = invoice_result(
        [line("Karak Premix", qty="2.0", unit_price="27.25", line_total="54.5")],
        subtotal=Decimal("54.5"),
    )
    result = score_case(extracted, truth)
    assert result["header_fields"]["subtotal"] is True
    assert result["lines"]["fields"]["qty"] == {"correct": 1, "total": 1}
    assert result["lines"]["fields"]["line_total"] == {"correct": 1, "total": 1}


def test_line_reconciliation_boundary_at_abs_tolerance():
    # qty * unit_price = 2.00; abs tolerance dominates (0.5% of ~2 is < 0.05).
    at_tolerance = ExtractedInvoice(
        lines=[line("Item", qty="1", unit_price="2.00", line_total="2.05")],
        total=Decimal("2.05"),
    )
    assert LINE_TOLERANCE_ABS == Decimal("0.05")
    assert invoice_reconciles(at_tolerance)
    over_tolerance = ExtractedInvoice(
        lines=[line("Item", qty="1", unit_price="2.00", line_total="2.06")],
        total=Decimal("2.06"),
    )
    assert not invoice_reconciles(over_tolerance)


def test_line_reconciliation_pct_tolerance_dominates_on_large_lines():
    # qty * unit_price = 1000.00; 0.5% of the line_total exceeds 0.05.
    within = ExtractedInvoice(
        lines=[line("Item", qty="100", unit_price="10.00", line_total="1004.00")],
        total=Decimal("1004.00"),
    )
    assert invoice_reconciles(within)
    beyond = ExtractedInvoice(
        lines=[line("Item", qty="100", unit_price="10.00", line_total="1005.10")],
        total=Decimal("1005.10"),
    )
    assert not invoice_reconciles(beyond)


def test_document_reconciliation_boundary_at_doc_tolerance():
    lines = [line("Item", qty="4", unit_price="25.00", line_total="100.00")]
    assert DOC_TOLERANCE_ABS == Decimal("0.10")
    at_tolerance = ExtractedInvoice(lines=lines, tax=Decimal("5.00"), total=Decimal("105.10"))
    assert invoice_reconciles(at_tolerance)
    over_tolerance = ExtractedInvoice(lines=lines, tax=Decimal("5.00"), total=Decimal("105.11"))
    assert not invoice_reconciles(over_tolerance)


def test_incomplete_line_never_reconciles():
    incomplete = ExtractedInvoice(
        lines=[line("Item", qty="4", line_total="100.00")], total=Decimal("100.00")
    )
    assert not invoice_reconciles(incomplete)


def test_misclassification_scores_truth_fields_wrong():
    truth = invoice_result(TRUTH_LINES, supplier_name="Gulf Fresh", total=Decimal("120.00"))
    extracted = ExtractionResult(classification=Classification.OTHER, invoice=None)
    result = score_case(extracted, truth)
    assert result["classification"]["correct"] is False
    assert result["header_fields"]["supplier_name"] is False
    assert result["header_fields"]["total"] is False
    # Truth fields that are genuinely absent still agree with an absent invoice.
    assert result["header_fields"]["tax"] is True
    assert result["lines"]["recall"] == 0.0
    assert result["lines"]["precision"] is None
    assert result["reconciliation"] == {"applicable": False, "reconciled": None}


def test_aggregate_sums_counters_across_cases():
    perfect = score_case(invoice_result(TRUTH_LINES), invoice_result(TRUTH_LINES))
    missing = score_case(invoice_result(TRUTH_LINES[:2]), invoice_result(TRUTH_LINES))
    agg = aggregate([perfect, missing])
    assert agg["lines"]["matched"] == 5
    assert agg["lines"]["truth_count"] == 6
    assert agg["lines"]["recall"] == 0.8333
    assert agg["lines"]["precision"] == 1.0
    assert agg["classification"] == {"correct": 2, "total": 2, "accuracy": 1.0}
    assert agg["repair_lift"] == {
        "reconciliation_rate_before_repair": None,
        "reconciliation_rate_after_repair": None,
    }
