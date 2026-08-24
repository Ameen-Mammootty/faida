"""Scoring for the extraction eval (plan.md §5).

Field-level accuracy (exact for numbers/dates, fuzzy >= 0.9 for names), line
alignment with recall/precision, and arithmetic reconciliation against the C4
constants. Pure functions, no I/O; run.py owns loading and reporting.
"""

from __future__ import annotations

from decimal import Decimal
from difflib import SequenceMatcher

from faida_api.extraction.constants import (
    DOC_TOLERANCE_ABS,
    LINE_TOLERANCE_ABS,
    LINE_TOLERANCE_PCT,
)
from faida_api.extraction.currency import normalize_currency
from faida_api.extraction.provider import ProviderUsage
from faida_api.extraction.schema import ExtractedInvoice, ExtractedLine, ExtractionResult

FUZZY_THRESHOLD = 0.9
# A candidate line pair needs at least this pair score to align at all.
MIN_ALIGNMENT_SCORE = 0.5

# Header fields scored per invoice: fuzzy for the supplier name; exact for the
# rest (Decimal-numeric for money, date equality, normalized text otherwise).
HEADER_FIELDS = (
    "supplier_name",
    "invoice_no",
    "invoice_date",
    "currency",
    "payment_kind",
    "subtotal",
    "tax",
    "total",
)
_FUZZY_HEADER_FIELDS = frozenset({"supplier_name"})

# Line fields over aligned pairs: raw_name fuzzy; qty/unit_price/line_total
# Decimal-exact; unit/pack_size case-insensitive via the same normalization.
LINE_FIELDS = ("raw_name", "qty", "unit", "pack_size", "unit_price", "line_total")


def normalize_text(value: str) -> str:
    """Casefold and collapse whitespace before any string comparison."""
    return " ".join(value.casefold().split())


def fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def fuzzy_equal(a: str, b: str) -> bool:
    return fuzzy_ratio(a, b) >= FUZZY_THRESHOLD


def _match(extracted: object, truth: object, fuzzy: bool) -> bool:
    """One field comparison; both-None counts as agreement."""
    if extracted is None or truth is None:
        return extracted is None and truth is None
    if isinstance(truth, str):
        if fuzzy:
            return fuzzy_equal(str(extracted), truth)
        return normalize_text(str(extracted)) == normalize_text(truth)
    # Decimal ("54.5" == "54.50") and dates compare by value.
    return bool(extracted == truth)


def _header_value(invoice: ExtractedInvoice, field: str) -> object:
    """Currency is scored as the ISO code the pipeline derives, so a printed
    "Dhs" read as "Dhs" against a truth of "AED" is agreement, not a miss."""
    value = getattr(invoice, field)
    if field == "currency":
        return normalize_currency(value)
    return value


def _pair_score(extracted: ExtractedLine, truth: ExtractedLine) -> float:
    """Greedy alignment score: raw_name similarity plus qty/unit_price agreement."""
    score = fuzzy_ratio(extracted.raw_name, truth.raw_name)
    if extracted.qty is not None and truth.qty is not None and extracted.qty == truth.qty:
        score += 0.25
    if (
        extracted.unit_price is not None
        and truth.unit_price is not None
        and extracted.unit_price == truth.unit_price
    ):
        score += 0.25
    return score


def align_lines(
    extracted: list[ExtractedLine], truth: list[ExtractedLine]
) -> list[tuple[int, int]]:
    """Greedy best-match pairing of extracted to truth lines.

    Returns (extracted_index, truth_index) pairs; each line matches at most
    once, and pairs below MIN_ALIGNMENT_SCORE never form.
    """
    candidates = []
    for i, e in enumerate(extracted):
        for j, t in enumerate(truth):
            score = _pair_score(e, t)
            if score >= MIN_ALIGNMENT_SCORE:
                candidates.append((score, i, j))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    used_extracted: set[int] = set()
    used_truth: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for _score, i, j in candidates:
        if i not in used_extracted and j not in used_truth:
            pairs.append((i, j))
            used_extracted.add(i)
            used_truth.add(j)
    return sorted(pairs)


def invoice_reconciles(invoice: ExtractedInvoice) -> bool:
    """C4 arithmetic over one extracted invoice (plan.md §5 layer 2).

    Line: |qty * unit_price - line_total| <= max(LINE_TOLERANCE_ABS,
    LINE_TOLERANCE_PCT * line_total); a line missing any of the three values
    cannot reconcile. Document: |sum(line_totals) + tax - total| <=
    DOC_TOLERANCE_ABS, with a missing tax treated as zero. Duplicated here so
    the eval stands alone; WP-16 may swap this to faida_api.extraction.validate
    once WP-11/WP-13 integrate.
    """
    for line in invoice.lines:
        if line.qty is None or line.unit_price is None or line.line_total is None:
            return False
        tolerance = max(LINE_TOLERANCE_ABS, LINE_TOLERANCE_PCT * abs(line.line_total))
        if abs(line.qty * line.unit_price - line.line_total) > tolerance:
            return False
    if invoice.total is None:
        return False
    tax = invoice.tax if invoice.tax is not None else Decimal(0)
    line_sum = sum((line.line_total for line in invoice.lines), Decimal(0))
    return abs(line_sum + tax - invoice.total) <= DOC_TOLERANCE_ABS


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 4)


def score_case(
    extracted: ExtractionResult,
    truth: ExtractionResult,
    usage: ProviderUsage | None = None,
) -> dict:
    """Score one (extracted, truth) pair into a JSON-serializable dict.

    header_fields and lines are scored only when the truth carries an invoice;
    an extraction that missed the invoice (e.g. misclassified as "other")
    scores every set truth field wrong and every truth line unmatched.
    Reconciliation is a property of the extracted invoice alone, so it is
    "applicable" only when the extraction produced one.
    """
    case: dict = {
        "classification": {
            "truth": truth.classification.value,
            "extracted": extracted.classification.value,
            "correct": extracted.classification == truth.classification,
        },
        "header_fields": None,
        "lines": None,
        "reconciliation": {
            "applicable": extracted.invoice is not None,
            "reconciled": (
                invoice_reconciles(extracted.invoice) if extracted.invoice is not None else None
            ),
        },
        "usage": usage.model_dump() if usage is not None else None,
    }
    if truth.invoice is None:
        return case

    truth_invoice = truth.invoice
    extracted_invoice = extracted.invoice if extracted.invoice is not None else ExtractedInvoice()
    case["header_fields"] = {
        field: _match(
            _header_value(extracted_invoice, field),
            _header_value(truth_invoice, field),
            fuzzy=field in _FUZZY_HEADER_FIELDS,
        )
        for field in HEADER_FIELDS
    }

    pairs = align_lines(extracted_invoice.lines, truth_invoice.lines)
    fields = {field: {"correct": 0, "total": 0} for field in LINE_FIELDS}
    for i, j in pairs:
        extracted_line = extracted_invoice.lines[i]
        truth_line = truth_invoice.lines[j]
        for field in LINE_FIELDS:
            fields[field]["total"] += 1
            if _match(
                getattr(extracted_line, field),
                getattr(truth_line, field),
                fuzzy=field == "raw_name",
            ):
                fields[field]["correct"] += 1
    case["lines"] = {
        "truth_count": len(truth_invoice.lines),
        "extracted_count": len(extracted_invoice.lines),
        "matched": len(pairs),
        "recall": _rate(len(pairs), len(truth_invoice.lines)),
        "precision": _rate(len(pairs), len(extracted_invoice.lines)),
        "fields": fields,
    }
    return case


def aggregate(cases: list[dict]) -> dict:
    """Fold per-case scores into corpus-level metrics."""
    classification_correct = sum(1 for c in cases if c["classification"]["correct"])
    header = {field: {"correct": 0, "total": 0} for field in HEADER_FIELDS}
    line_fields = {field: {"correct": 0, "total": 0} for field in LINE_FIELDS}
    matched = truth_count = extracted_count = 0
    reconciled = applicable = 0
    usages = [c["usage"] for c in cases if c["usage"] is not None]

    for case in cases:
        if case["header_fields"] is not None:
            for field, ok in case["header_fields"].items():
                header[field]["total"] += 1
                header[field]["correct"] += int(ok)
        if case["lines"] is not None:
            matched += case["lines"]["matched"]
            truth_count += case["lines"]["truth_count"]
            extracted_count += case["lines"]["extracted_count"]
            for field, tally in case["lines"]["fields"].items():
                line_fields[field]["correct"] += tally["correct"]
                line_fields[field]["total"] += tally["total"]
        if case["reconciliation"]["applicable"]:
            applicable += 1
            reconciled += int(bool(case["reconciliation"]["reconciled"]))

    for tally in header.values():
        tally["accuracy"] = _rate(tally["correct"], tally["total"])
    for tally in line_fields.values():
        tally["accuracy"] = _rate(tally["correct"], tally["total"])

    usage_aggregate = None
    if usages:
        n = len(usages)
        usage_aggregate = {
            "cases_with_usage": n,
            "avg_input_tokens": round(sum(u["input_tokens"] for u in usages) / n, 1),
            "avg_output_tokens": round(sum(u["output_tokens"] for u in usages) / n, 1),
            "avg_latency_ms": round(sum(u["latency_ms"] for u in usages) / n, 1),
            # Dollar cost derives from tokens; the pricing table arrives with
            # WP-16 live runs.
            "avg_cost_usd": None,
        }

    return {
        "cases": len(cases),
        "classification": {
            "correct": classification_correct,
            "total": len(cases),
            "accuracy": _rate(classification_correct, len(cases)),
        },
        "header_fields": header,
        "lines": {
            "matched": matched,
            "truth_count": truth_count,
            "extracted_count": extracted_count,
            "recall": _rate(matched, truth_count),
            "precision": _rate(matched, extracted_count),
            "fields": line_fields,
        },
        "reconciliation": {
            "reconciled": reconciled,
            "applicable": applicable,
            "rate": _rate(reconciled, applicable),
        },
        "usage": usage_aggregate,
        # Repair lift is measured on live runs (reconciliation before vs after
        # the repair pass, plan.md §5 layer 3); recorded fixtures cannot supply
        # it, so the fields stay null until WP-16.
        "repair_lift": {
            "reconciliation_rate_before_repair": None,
            "reconciliation_rate_after_repair": None,
        },
    }
