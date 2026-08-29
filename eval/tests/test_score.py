"""Scorer unit tests (WP-14): line alignment, fuzzy edges, Decimal-numeric
equality, and reconciliation tolerance boundaries.

Run from the repo root: apps/api/.venv/bin/python -m pytest eval/tests -q
"""

from decimal import Decimal

from faida_api.extraction.constants import (
    DOC_TOLERANCE_ABS,
    LINE_TOLERANCE_ABS,
)
from faida_api.extraction.provider import ProviderUsage
from faida_api.extraction.schema import (
    Classification,
    ExtractedInvoice,
    ExtractedLine,
    ExtractionResult,
    LineKind,
)

from eval.score import (
    aggregate,
    align_lines,
    cost_usd,
    fuzzy_equal,
    fuzzy_ratio,
    invoice_reconciles,
    score_case,
)


def line(
    raw_name: str,
    qty: str | None = None,
    unit_price: str | None = None,
    line_total: str | None = None,
    unit: str | None = None,
    pack_size: str | None = None,
    line_kind: LineKind = LineKind.STOCK_ITEM,
) -> ExtractedLine:
    return ExtractedLine(
        raw_name=raw_name,
        qty=Decimal(qty) if qty is not None else None,
        unit=unit,
        pack_size=pack_size,
        unit_price=Decimal(unit_price) if unit_price is not None else None,
        line_total=Decimal(line_total) if line_total is not None else None,
        line_kind=line_kind,
    )


def invoice_result(lines: list[ExtractedLine], **headers) -> ExtractionResult:
    return ExtractionResult(
        classification=Classification.INVOICE,
        invoice=ExtractedInvoice(lines=lines, **headers),
    )


TRUTH_LINES = [
    line(
        "Tomato Local Box 5kg",
        qty="4",
        unit_price="18.50",
        line_total="74.00",
        unit="box",
    ),
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


def test_currency_scored_as_the_derived_iso_code():
    # The model copies "Dhs." as printed; the pipeline derives AED from it, so
    # the eval must agree with what the invoice row will actually hold.
    truth = invoice_result([], currency="AED")
    assert score_case(invoice_result([], currency="Dhs."), truth)["header_fields"]["currency"]
    assert not score_case(invoice_result([], currency="SAR"), truth)["header_fields"]["currency"]


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
    assert result["reconciliation"] == {
        "applicable": False,
        "reconciled": None,
        "reconciled_before_repair": None,
    }


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


def test_vat_inclusive_invoice_reconciles_like_the_shipped_validator():
    """The regression that made this delegate to faida_api.extraction.validate
    (WP-16). The eval carried its own copy of C4 that knew only the exclusive
    identity, so after WP-17 a VAT-inclusive invoice - the GCC norm, and the
    shape of TH-01 and EDGE-02 - scored as unreconciled off perfect ground
    truth. Lines are gross here: 700.00 of lines IS the 700.00 total, with
    33.33 of UAE 5% VAT already inside it."""
    inclusive = ExtractedInvoice(
        lines=[line("Milk Powder 2.5kg", qty="10", unit_price="70.00", line_total="700.00")],
        tax=Decimal("33.33"),
        total=Decimal("700.00"),
    )
    assert invoice_reconciles(inclusive)


def test_trade_discount_invoice_reconciles_like_the_shipped_validator():
    """The WP-18 half of the same regression (EDGE-01): lines sum to 834.00,
    a 41.70 trade discount and a 25.00 delivery charge sit between that and
    the total, and the old copy of C4 modelled none of it."""
    discounted = ExtractedInvoice(
        lines=[
            line("Basmati Rice 20kg", qty="20", unit_price="41.70", line_total="834.00"),
            line(
                "Chilled delivery",
                qty="1",
                unit_price="25.00",
                line_total="25.00",
                line_kind=LineKind.CHARGE,
            ),
        ],
        discount_total=Decimal("41.70"),
        tax=Decimal("40.87"),
        total=Decimal("858.17"),
    )
    assert invoice_reconciles(discounted)


def test_cost_derives_from_tokens_and_is_null_for_an_unpriced_model():
    priced = ProviderUsage(
        model_id="claude-opus-5",
        prompt_version="v1",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        latency_ms=1000,
    )
    # $5/M in + $25/M out.
    assert cost_usd(priced) == 30.0
    # The API echoes back the model that served the request; a suffixed id
    # still prices off its family rather than silently costing nothing.
    suffixed = priced.model_copy(update={"model_id": "claude-opus-5-20260801"})
    assert cost_usd(suffixed) == 30.0
    unknown = priced.model_copy(update={"model_id": "some-other-model"})
    assert cost_usd(unknown) is None
    assert cost_usd(None) is None


def test_repair_lift_reported_only_when_a_before_verdict_exists():
    # 74.00 + 24.00 + 22.00, so this reconciles after repair either way.
    truth = invoice_result(TRUTH_LINES, total=Decimal("120.00"))
    broke = score_case(truth, truth, reconciled_before_repair=False)
    held = score_case(truth, truth, reconciled_before_repair=True)
    agg = aggregate([broke, held])
    # Both reconcile after repair; one did not before it.
    assert agg["repair_lift"] == {
        "reconciliation_rate_before_repair": 0.5,
        "reconciliation_rate_after_repair": 1.0,
    }


# --- the model's own pack reading, kept visible under the derivation --------


def test_pack_size_is_scored_twice_so_the_derivation_cannot_hide_the_model():
    # A till receipt: no pack column, every pack inside the item name. The
    # seam recovers all three deterministically, so the stored pack_size is
    # perfect - but the model returned none of them, and that is the number
    # that says whether a model reads packs off paper.
    truth = invoice_result(
        [
            line("RICE BASM 5KG", qty="2", unit_price="33.60", line_total="67.20", pack_size="5KG"),
            line("SODA 1L", qty="24", unit_price="4.20", line_total="100.80", pack_size="1L"),
        ]
    )
    as_returned = invoice_result(
        [
            line("RICE BASM 5KG", qty="2", unit_price="33.60", line_total="67.20"),
            line("SODA 1L", qty="24", unit_price="4.20", line_total="100.80"),
        ]
    )
    # What the seam produced, and what the database would store.
    stored = truth
    case = score_case(stored, truth, as_returned=as_returned)
    assert case["lines"]["fields"]["pack_size"] == {"correct": 2, "total": 2}
    assert case["lines"]["model_pack_size"] == {"correct": 0, "total": 2}


def test_the_model_pack_score_is_absent_when_no_raw_answer_was_given():
    truth = invoice_result([line("Cucumber 5kg", qty="2", unit_price="12.00", line_total="24.00")])
    assert score_case(truth, truth)["lines"]["model_pack_size"] is None


def test_aggregate_folds_the_model_pack_score_across_cases():
    truth = invoice_result(
        [line("RICE BASM 5KG", qty="2", unit_price="33.60", line_total="67.20", pack_size="5KG")]
    )
    read = score_case(truth, truth, as_returned=truth)
    missed = score_case(truth, truth, as_returned=invoice_result([line("RICE BASM 5KG", qty="2")]))
    agg = aggregate([read, missed])
    assert agg["lines"]["model_pack_size"]["correct"] == 1
    assert agg["lines"]["model_pack_size"]["total"] == 2
    assert agg["lines"]["fields"]["pack_size"]["accuracy"] == 1.0
