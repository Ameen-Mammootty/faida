"""Scoring for the extraction eval (plan.md §5).

Field-level accuracy (exact for numbers/dates, fuzzy >= 0.9 for names), line
alignment with recall/precision, and arithmetic reconciliation against the C4
constants. Pure functions, no I/O; run.py owns loading and reporting.
"""

from __future__ import annotations

from decimal import Decimal
from difflib import SequenceMatcher

from faida_api.extraction import units
from faida_api.extraction.currency import normalize_currency
from faida_api.extraction.provider import ProviderUsage
from faida_api.extraction.schema import (
    ExtractedInvoice,
    ExtractedLine,
    ExtractionResult,
)
from faida_api.extraction.validate import CheckStatus, validate_invoice

# Claude API list prices in USD per million tokens. Only models we actually
# run belong here: an unknown model id yields a null cost, never a guess.
MODEL_PRICING_USD_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    "claude-opus-5": (Decimal("5.00"), Decimal("25.00")),
}

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


def _match_line_field(field: str, extracted: object, truth: object) -> bool:
    """Line-field comparison, with the units dictionary applied where the same
    fact has many printings.

    A supplier writing "2 kg" where the catalog says "2000 g" has not made an
    error and neither has the model, so scoring them as a miss would send the
    accuracy loop chasing a difference that does not exist. The same dictionary
    decides it here and in the catalog (`extraction.units`), so the eval cannot
    drift from what snapping actually does.
    """
    if field == "pack_size":
        if extracted is None or truth is None:
            return extracted is None and truth is None
        return units.same_pack_size(str(extracted), str(truth))
    if field == "unit":
        if extracted is None or truth is None:
            return extracted is None and truth is None
        left = units.canonical_unit(str(extracted))
        right = units.canonical_unit(str(truth))
        if left is not None and right is not None:
            return left == right
    return _match(extracted, truth, fuzzy=field == "raw_name")


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
    """C4 arithmetic over one extracted invoice (plan.md §5 layer 2), decided
    by the validator the product ships.

    This was a second copy of C4 until WP-16, kept "so the eval stands alone",
    and it drifted exactly as plan.md §2 rule 3 predicts a second
    implementation will. It knew only the exclusive identity, so after WP-17
    and WP-18 it scored TH-01 and EDGE-02 (VAT-inclusive) and EDGE-01
    (trade discount) as unreconciled *off hand-verified ground truth* - a
    reconciliation ceiling of 11/14 against a §5 gate of 100%, measuring a
    program we do not run.

    An invoice reconciles when the document identity holds and every line's
    arithmetic passes. Snapping is deliberately not required: it moves a field
    from green to amber (layer 5), not the arithmetic.
    """
    validation = validate_invoice(invoice)
    return validation.document.arith is CheckStatus.PASSED and all(
        check.arith is CheckStatus.PASSED for check in validation.lines
    )


def cost_usd(usage: ProviderUsage | None) -> float | None:
    """Dollar cost of one run from its token counts (plan.md §5: cost per
    invoice). None when the model is not in the price table - a made-up unit
    price is worse than an empty column."""
    if usage is None:
        return None
    price = MODEL_PRICING_USD_PER_MTOK.get(usage.model_id)
    if price is None:
        # The API echoes back the model that served the request, which may
        # carry a suffix the request did not; fall back to the longest
        # matching prefix before giving up.
        matches = [k for k in MODEL_PRICING_USD_PER_MTOK if usage.model_id.startswith(k)]
        if not matches:
            return None
        price = MODEL_PRICING_USD_PER_MTOK[max(matches, key=len)]
    per_input, per_output = price
    total = (
        Decimal(usage.input_tokens) * per_input + Decimal(usage.output_tokens) * per_output
    ) / Decimal(1_000_000)
    return float(round(total, 6))


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 4)


def score_case(
    extracted: ExtractionResult,
    truth: ExtractionResult,
    usage: ProviderUsage | None = None,
    reconciled_before_repair: bool | None = None,
) -> dict:
    """Score one (extracted, truth) pair into a JSON-serializable dict.

    header_fields and lines are scored only when the truth carries an invoice;
    an extraction that missed the invoice (e.g. misclassified as "other")
    scores every set truth field wrong and every truth line unmatched.
    Reconciliation is a property of the extracted invoice alone, so it is
    "applicable" only when the extraction produced one.

    `extracted` is the post-repair invoice; `reconciled_before_repair` carries
    the pre-repair verdict so the aggregate can report repair lift (§5 layer
    3). Recorded runs replay the extract call alone and pass None.
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
            "reconciled_before_repair": reconciled_before_repair,
        },
        "usage": usage.model_dump() if usage is not None else None,
        "cost_usd": cost_usd(usage),
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
            if _match_line_field(field, getattr(extracted_line, field), getattr(truth_line, field)):
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


def _render(value: object) -> str | None:
    """Money, dates and enums into something a diff line can show."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(getattr(value, "value", value))


def explain_case(extracted: ExtractionResult, truth: ExtractionResult) -> dict:
    """Every disagreement behind one case's booleans, as extracted-vs-truth
    pairs (WP-16).

    The scores say a field is wrong; the accuracy loop needs to know *how*
    before it can tell a model error from a ground-truth error. The first live
    run scored pack_size at 19% and that turned out to be truth holding
    "2000" where the page prints "2 kg" - a converter bug, not an extraction
    one, and invisible from a boolean.

    Kept out of score_case so the scored dict stays exactly what the CI smoke
    pins.
    """
    out: dict = {"classification": None, "header_fields": {}, "lines": [], "unmatched": []}
    if extracted.classification != truth.classification:
        out["classification"] = {
            "extracted": extracted.classification.value,
            "truth": truth.classification.value,
        }
    if truth.invoice is None:
        return out

    extracted_invoice = extracted.invoice if extracted.invoice is not None else ExtractedInvoice()
    for field in HEADER_FIELDS:
        got = _header_value(extracted_invoice, field)
        want = _header_value(truth.invoice, field)
        if not _match(got, want, fuzzy=field in _FUZZY_HEADER_FIELDS):
            out["header_fields"][field] = {"extracted": _render(got), "truth": _render(want)}

    pairs = align_lines(extracted_invoice.lines, truth.invoice.lines)
    for i, j in pairs:
        extracted_line = extracted_invoice.lines[i]
        truth_line = truth.invoice.lines[j]
        for field in LINE_FIELDS:
            got = getattr(extracted_line, field)
            want = getattr(truth_line, field)
            if not _match_line_field(field, got, want):
                out["lines"].append(
                    {
                        "line": j,
                        "field": field,
                        "extracted": _render(got),
                        "truth": _render(want),
                    }
                )
    matched_extracted = {i for i, _ in pairs}
    matched_truth = {j for _, j in pairs}
    for i, extracted_line in enumerate(extracted_invoice.lines):
        if i not in matched_extracted:
            out["unmatched"].append({"side": "extracted", "raw_name": extracted_line.raw_name})
    for j, truth_line in enumerate(truth.invoice.lines):
        if j not in matched_truth:
            out["unmatched"].append({"side": "truth", "raw_name": truth_line.raw_name})
    return out


def aggregate(cases: list[dict]) -> dict:
    """Fold per-case scores into corpus-level metrics."""
    classification_correct = sum(1 for c in cases if c["classification"]["correct"])
    header = {field: {"correct": 0, "total": 0} for field in HEADER_FIELDS}
    line_fields = {field: {"correct": 0, "total": 0} for field in LINE_FIELDS}
    matched = truth_count = extracted_count = 0
    reconciled = applicable = 0
    reconciled_before = before_measured = 0
    usages = [c["usage"] for c in cases if c["usage"] is not None]
    costs = [c["cost_usd"] for c in cases if c.get("cost_usd") is not None]

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
            before = case["reconciliation"].get("reconciled_before_repair")
            if before is not None:
                before_measured += 1
                reconciled_before += int(before)

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
            # Null when no case carried a priced model (see cost_usd).
            "avg_cost_usd": round(sum(costs) / len(costs), 6) if costs else None,
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
        # Repair lift (plan.md §5 layer 3): reconciliation before vs after the
        # scoped repair round. Only live runs make both calls, so recorded
        # replays leave both rates null rather than reporting a lift of zero.
        "repair_lift": {
            "reconciliation_rate_before_repair": (
                _rate(reconciled_before, before_measured) if before_measured else None
            ),
            "reconciliation_rate_after_repair": (
                _rate(reconciled, applicable) if before_measured else None
            ),
        },
    }
