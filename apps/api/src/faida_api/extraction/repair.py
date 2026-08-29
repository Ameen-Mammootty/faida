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


def _same_row(patched_name: str | None, original_name: str | None) -> bool:
    """Does the patch's raw_name confirm it re-read the row we asked about?

    The repair prompt asks for "raw_name exactly as printed (to confirm the
    row)" precisely so a patch keyed to the wrong index cannot silently rewrite
    another line's money. The check is deliberately not equality: the first
    pass sometimes folds a handwritten margin note into the name (EDGE-01,
    "Avocado Credit: one box returned, soft fruit") and a cleaner second read
    is a better answer, not a wrong row. So either name may extend the other,
    and only a genuine disagreement rejects the patch.
    """
    left = " ".join((patched_name or "").split()).casefold()
    right = " ".join((original_name or "").split()).casefold()
    if not left or not right:
        return False
    return left.startswith(right) or right.startswith(left)


def apply_repair(
    invoice: ExtractedInvoice, patch: RepairResult, targets: list[RepairTarget]
) -> ExtractedInvoice:
    """Pure merge of a *partial* patch. The input is never mutated.

    A repair patch is not a replacement line, and treating it as one was a
    silent data-loss bug: `build_repair_prompt` tells the model to return
    "null for every other field", so a patched line arrives carrying nulls for
    `unit` and `pack_size` by instruction. Swapping the line wholesale wrote
    those nulls over values the first pass had read correctly, and `pack_size`
    is the denominator M5 divides a price by. It never bit only because Gemini
    3 Flash reconciles the whole corpus with zero repair rounds, so this path
    has never run in anger.

    Four rules, all of them refusals:

    - **Only targeted fields move.** Everything else on the line is kept,
      which is what `RepairResult` has always claimed ("repair never touches
      fields that passed").
    - **A null on a targeted field keeps the old value.** The prompt says a
      cell the model still cannot read stays null; that is "I could not read
      it", not "it is empty". The old value stays, still fails its check, and
      goes amber for the question flow (§5 layer 5).
    - **Unrequested indices are dropped**, along with indices out of range: a
      patch for a line nobody asked about is not evidence about that line.
    - **The row must confirm itself** via raw_name, so a mis-keyed patch
      cannot rewrite a different line's money.
    """
    line_fields: dict[int, set[str]] = {}
    totals_fields: set[str] = set()
    for target in targets:
        if target.line_index is None:
            totals_fields.update(target.fields)
        else:
            line_fields.setdefault(target.line_index, set()).update(target.fields)

    lines = list(invoice.lines)
    for index, patched in patch.lines.items():
        if index not in line_fields or not 0 <= index < len(lines):
            continue
        original = lines[index]
        if not _same_row(patched.raw_name, original.raw_name):
            continue
        moved = {
            field: getattr(patched, field)
            for field in line_fields[index]
            if getattr(patched, field, None) is not None
        }
        if moved:
            lines[index] = original.model_copy(update=moved)

    header = {
        field: value
        for field, value in (
            ("subtotal", patch.subtotal),
            ("tax", patch.tax),
            ("total", patch.total),
        )
        if field in totals_fields and value is not None
    }
    return invoice.model_copy(update={"lines": lines, **header})


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
        invoice = apply_repair(invoice, patch, targets)
        validation = validate_invoice(invoice)
        targets = build_repair_targets(invoice, validation)
        if not targets:
            break
    return RepairOutcome(invoice=invoice, validation=validation, usage=usage, applied=True)
