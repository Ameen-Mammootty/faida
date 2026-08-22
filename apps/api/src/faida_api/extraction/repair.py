"""Targeted repair pass (plan.md §5 layer 3, WP-12).

Failed arithmetic checks become scoped re-read targets; one provider.repair
call re-reads only those cells, the patch merges over the invoice, and
validation re-runs. Indeterminate checks (missing values) are never targets -
they stay amber for the WhatsApp-question flow (§5 layer 5). MAX_REPAIR_ROUNDS
pins the cap at one round; whatever still fails stays amber, never a
re-extract.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from .constants import MAX_REPAIR_ROUNDS
from .provider import ExtractionProvider, ProviderUsage
from .schema import ExtractedInvoice, RepairResult, RepairTarget
from .validate import CheckStatus, ValidationResult, validate_invoice


class RepairOutcome(BaseModel):
    """What the repair pass hands back to the pipeline (WP-13). `applied` is
    False when nothing had failed, so no provider call was made."""

    model_config = ConfigDict(extra="forbid")

    invoice: ExtractedInvoice
    validation: ValidationResult
    usage: ProviderUsage | None = None
    applied: bool


def build_repair_targets(
    invoice: ExtractedInvoice, validation: ValidationResult
) -> list[RepairTarget]:
    """One target per FAILED arithmetic check, quoting the arithmetic so the
    repair prompt can point at the exact cells."""
    targets: list[RepairTarget] = []
    for check in validation.lines:
        if check.arith != CheckStatus.FAILED:
            continue
        line = invoice.lines[check.line_index]
        targets.append(
            RepairTarget(
                line_index=check.line_index,
                fields=["qty", "unit_price", "line_total"],
                reason=(
                    f"Line {check.line_index}: qty {line.qty} x {line.unit_price} "
                    f"= {check.expected} != extracted {check.extracted}"
                ),
            )
        )
    doc = validation.document
    if doc.arith == CheckStatus.FAILED:
        tax = invoice.tax if invoice.tax is not None else Decimal("0")
        targets.append(
            RepairTarget(
                line_index=None,
                fields=["subtotal", "tax", "total"],
                reason=(
                    f"Totals: line sum {doc.line_sum} + tax {tax} "
                    f"= {doc.expected} != extracted total {doc.extracted}"
                ),
            )
        )
    return targets


def apply_repair(invoice: ExtractedInvoice, patch: RepairResult) -> ExtractedInvoice:
    """Pure merge: a patched line index replaces that line wholesale, indices
    out of range are ignored, totals apply only when non-None in the patch,
    and everything untargeted is untouched. The input is never mutated."""
    lines = [patch.lines.get(i, line) for i, line in enumerate(invoice.lines)]
    return invoice.model_copy(
        update={
            "lines": lines,
            "subtotal": patch.subtotal if patch.subtotal is not None else invoice.subtotal,
            "tax": patch.tax if patch.tax is not None else invoice.tax,
            "total": patch.total if patch.total is not None else invoice.total,
        }
    )


async def repair_invoice(
    provider: ExtractionProvider,
    image: bytes,
    mime: str,
    invoice: ExtractedInvoice,
    validation: ValidationResult,
) -> RepairOutcome:
    """Run the one scoped repair round when any check failed; otherwise return
    the inputs unchanged without touching the provider."""
    targets = build_repair_targets(invoice, validation)
    if not targets:
        return RepairOutcome(invoice=invoice, validation=validation, usage=None, applied=False)

    usage: ProviderUsage | None = None
    # MAX_REPAIR_ROUNDS is 1 (plan.md §5 layer 3): exactly one scoped call,
    # then fields still failing simply stay failed/amber for layer 5.
    for _ in range(MAX_REPAIR_ROUNDS):
        patch, usage = await provider.repair(image, mime, targets)
        invoice = apply_repair(invoice, patch)
        validation = validate_invoice(invoice)
        targets = build_repair_targets(invoice, validation)
        if not targets:
            break
    return RepairOutcome(invoice=invoice, validation=validation, usage=usage, applied=True)
