"""Deterministic validation (plan.md §5 layers 2 and 5, contract C4).

Pure functions over the extraction schema: per-line and document arithmetic
reconciliation in Decimal, plus the derived green/amber field statuses. The
result models here are the persisted `checks` shape (WP-13 stores them).

The one invariant: a wrong value can never come out green - when in doubt,
amber. Supplier-item snapping (WP-22) plugs in through the `snapped`
placeholder; until it exists its absence must never count against a line.
"""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .constants import DOC_TOLERANCE_ABS, LINE_TOLERANCE_ABS, LINE_TOLERANCE_PCT
from .schema import ExtractedInvoice, ExtractedLine


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    # A value the check needs is missing - never counts as passed.
    INDETERMINATE = "indeterminate"


class FieldStatus(StrEnum):
    GREEN = "green"
    AMBER = "amber"


class LineCheck(BaseModel):
    """Arithmetic result for one line. `status` covers the arithmetic-bound
    fields (qty, unit_price, line_total): the check ties them together, so
    they are green or amber as a set."""

    model_config = ConfigDict(extra="forbid")

    line_index: int
    arith: CheckStatus
    expected: Decimal | None = None  # qty * unit_price, set only when arith failed
    extracted: Decimal | None = None  # the extracted line_total, set only when arith failed
    # WP-22 snapping hook: None means snapping is not available yet and never
    # counts against the line; False will mean "did not snap" and forces amber.
    snapped: bool | None = None
    status: FieldStatus


class DocumentCheck(BaseModel):
    """Totals-block result. `status` covers subtotal, tax, and total."""

    model_config = ConfigDict(extra="forbid")

    arith: CheckStatus  # line sum + tax vs total
    subtotal_check: CheckStatus  # extracted subtotal vs line sum, when subtotal present
    line_sum: Decimal | None = None  # None when any line_total is missing
    expected: Decimal | None = None  # line_sum + tax, set only when arith failed
    extracted: Decimal | None = None  # the extracted total, set only when arith failed
    notes: list[str] = Field(default_factory=list)
    status: FieldStatus


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[LineCheck]
    document: DocumentCheck


def _snap_status(line: ExtractedLine) -> bool | None:
    """WP-22 hook: fuzzy-snap raw_name to a supplier item at a plausible
    price. Until that lands, always None - snapping is unavailable, which
    must never count against a line."""
    return None


def check_line(line_index: int, line: ExtractedLine) -> LineCheck:
    """C4 line check: |qty * unit_price - line_total| within
    max(LINE_TOLERANCE_ABS, LINE_TOLERANCE_PCT * |line_total|)."""
    snapped = _snap_status(line)
    if line.qty is None or line.unit_price is None or line.line_total is None:
        return LineCheck(
            line_index=line_index,
            arith=CheckStatus.INDETERMINATE,
            snapped=snapped,
            status=FieldStatus.AMBER,
        )
    expected = line.qty * line.unit_price
    tolerance = max(LINE_TOLERANCE_ABS, LINE_TOLERANCE_PCT * abs(line.line_total))
    if abs(expected - line.line_total) <= tolerance:
        green = snapped is not False  # None (no snapping yet) still allows green
        return LineCheck(
            line_index=line_index,
            arith=CheckStatus.PASSED,
            snapped=snapped,
            status=FieldStatus.GREEN if green else FieldStatus.AMBER,
        )
    return LineCheck(
        line_index=line_index,
        arith=CheckStatus.FAILED,
        expected=expected,
        extracted=line.line_total,
        snapped=snapped,
        status=FieldStatus.AMBER,
    )


def check_document(invoice: ExtractedInvoice, line_checks: list[LineCheck]) -> DocumentCheck:
    """C4 document check: |line_sum + tax - total| within DOC_TOLERANCE_ABS,
    plus a subtotal-vs-line-sum cross-check when subtotal was extracted."""
    notes: list[str] = []

    missing_totals = sum(1 for ln in invoice.lines if ln.line_total is None)
    if missing_totals:
        line_sum = None
        notes.append(f"line_total missing on {missing_totals} line(s); line sum unknown")
    else:
        line_sum = sum((ln.line_total for ln in invoice.lines), Decimal("0"))

    tax = invoice.tax
    if tax is None:
        tax = Decimal("0")
        notes.append("tax missing; treated as 0")

    if invoice.subtotal is None or line_sum is None:
        subtotal_check = CheckStatus.INDETERMINATE
    elif abs(invoice.subtotal - line_sum) <= DOC_TOLERANCE_ABS:
        subtotal_check = CheckStatus.PASSED
    else:
        subtotal_check = CheckStatus.FAILED

    expected: Decimal | None = None
    extracted: Decimal | None = None
    if invoice.total is None or line_sum is None:
        arith = CheckStatus.INDETERMINATE
    elif abs(line_sum + tax - invoice.total) <= DOC_TOLERANCE_ABS:
        arith = CheckStatus.PASSED
    else:
        arith = CheckStatus.FAILED
        expected = line_sum + tax
        extracted = invoice.total

    # A failed line taints the line sum: if its wrong number is the
    # line_total, a reconciling total proves nothing - stay amber. Lines that
    # are merely indeterminate do not taint it: sum == total is still two
    # independent readings agreeing.
    failed_lines = sum(1 for lc in line_checks if lc.arith == CheckStatus.FAILED)
    if failed_lines and arith == CheckStatus.PASSED:
        notes.append(f"{failed_lines} line check(s) failed; totals stay amber")

    green = (
        arith == CheckStatus.PASSED and subtotal_check != CheckStatus.FAILED and failed_lines == 0
    )
    return DocumentCheck(
        arith=arith,
        subtotal_check=subtotal_check,
        line_sum=line_sum,
        expected=expected,
        extracted=extracted,
        notes=notes,
        status=FieldStatus.GREEN if green else FieldStatus.AMBER,
    )


def validate_invoice(invoice: ExtractedInvoice) -> ValidationResult:
    """Run every deterministic check over one extracted invoice."""
    lines = [check_line(i, line) for i, line in enumerate(invoice.lines)]
    return ValidationResult(lines=lines, document=check_document(invoice, lines))
