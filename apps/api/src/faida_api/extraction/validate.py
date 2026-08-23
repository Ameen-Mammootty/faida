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

from .constants import (
    DOC_TOLERANCE_ABS,
    GCC_VAT_RATES,
    LINE_TOLERANCE_ABS,
    LINE_TOLERANCE_PCT,
)
from .schema import ExtractedInvoice, ExtractedLine, TaxTreatment


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

    arith: CheckStatus  # totals reconcile under one of the two C4 identities
    subtotal_check: CheckStatus  # extracted subtotal vs the line sum or the net, per treatment
    line_sum: Decimal | None = None  # None when any line_total is missing
    expected: Decimal | None = None  # line_sum + tax, set only when arith failed
    extracted: Decimal | None = None  # the extracted total, set only when arith failed
    # Which identity reconciled, and at what rate. Derived from the arithmetic
    # (C4), never from the document's own claim. None when arith did not pass.
    tax_treatment: TaxTreatment | None = None
    vat_rate: Decimal | None = None
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


def _effective_vat_rate(tax: Decimal, net_base: Decimal) -> Decimal | None:
    """The rate the document actually used, derived from its own totals rather
    than assumed from a table. Returns None when there is no VAT to describe."""
    if tax <= 0 or net_base <= 0:
        return None
    return (tax / net_base).quantize(Decimal("0.0001"))


def _known_gcc_rate(rate: Decimal | None) -> bool:
    return rate is not None and any(abs(rate - r) <= Decimal("0.0025") for r in GCC_VAT_RATES)


def _check_subtotal(
    subtotal: Decimal | None,
    line_sum: Decimal | None,
    total: Decimal | None,
    tax: Decimal,
    treatment: TaxTreatment | None,
) -> CheckStatus:
    """Cross-check the printed subtotal against whichever figure it should
    equal under the resolved treatment.

    Exclusive: the subtotal is the net, which is the line sum.
    Inclusive: invoices print it either way - some show the gross (equal to the
    total), some show the net (total - tax). Both are legitimate, so accept
    either rather than manufacturing an amber on a correct document."""
    if subtotal is None or line_sum is None:
        return CheckStatus.INDETERMINATE
    if treatment is TaxTreatment.INCLUSIVE and total is not None:
        gross_ok = abs(subtotal - total) <= DOC_TOLERANCE_ABS
        net_ok = abs(subtotal - (total - tax)) <= DOC_TOLERANCE_ABS
        return CheckStatus.PASSED if (gross_ok or net_ok) else CheckStatus.FAILED
    if abs(subtotal - line_sum) <= DOC_TOLERANCE_ABS:
        return CheckStatus.PASSED
    return CheckStatus.FAILED


def check_document(invoice: ExtractedInvoice, line_checks: list[LineCheck]) -> DocumentCheck:
    """C4 document check against **both** identities, because GCC invoices come
    both ways (amended 2026-08-23). With L = line sum, T = tax, G = total:

        exclusive (lines net)    |L + T - G| <= DOC_TOLERANCE_ABS
        inclusive (lines gross)  |L - G|     <= DOC_TOLERANCE_ABS  and T > 0

    While T is material the two are mutually exclusive, so there is nothing to
    disambiguate; when T is absent or zero the distinction is meaningless and
    exclusive is the honest label.

    **Anchored on the line sum, never on the printed subtotal.** An inclusive
    invoice that prints its subtotal as the net figure satisfies S + T = G and
    would masquerade as exclusive; the line sum is the only total we verify
    independently, line by line, so it is the arbiter."""
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

    treatment: TaxTreatment | None = None
    vat_rate: Decimal | None = None
    expected: Decimal | None = None
    extracted: Decimal | None = None

    if invoice.total is None or line_sum is None:
        arith = CheckStatus.INDETERMINATE
    elif abs(line_sum + tax - invoice.total) <= DOC_TOLERANCE_ABS:
        arith = CheckStatus.PASSED
        treatment = TaxTreatment.EXCLUSIVE
        vat_rate = _effective_vat_rate(tax, line_sum)
    elif tax > 0 and abs(line_sum - invoice.total) <= DOC_TOLERANCE_ABS:
        # Lines already sum to the total, so the tax sits inside them. That
        # the lines add up to the stated total is itself the proof; matching a
        # published rate is confirmation, not a gate, or an invoice at a rate
        # we have not listed would be failed for being unfamiliar.
        arith = CheckStatus.PASSED
        treatment = TaxTreatment.INCLUSIVE
        vat_rate = _effective_vat_rate(tax, invoice.total - tax)
        if not _known_gcc_rate(vat_rate):
            notes.append(f"tax-inclusive at an unlisted rate ({vat_rate}); totals still reconcile")
    else:
        arith = CheckStatus.FAILED
        expected = line_sum + tax
        extracted = invoice.total

    subtotal_check = _check_subtotal(invoice.subtotal, line_sum, invoice.total, tax, treatment)

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
        tax_treatment=treatment,
        vat_rate=vat_rate,
        notes=notes,
        status=FieldStatus.GREEN if green else FieldStatus.AMBER,
    )


def validate_invoice(invoice: ExtractedInvoice) -> ValidationResult:
    """Run every deterministic check over one extracted invoice."""
    lines = [check_line(i, line) for i, line in enumerate(invoice.lines)]
    return ValidationResult(lines=lines, document=check_document(invoice, lines))
