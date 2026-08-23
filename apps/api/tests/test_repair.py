"""Unit tests for the targeted repair pass (plan.md §5 layer 3, WP-12).

Fake provider only - no SDK, no network. What must hold: targets come from
FAILED checks alone, the merge touches only targeted cells, and the round cap
is exactly one provider call, never a second.
"""

from decimal import Decimal

from faida_api.extraction.provider import ProviderUsage
from faida_api.extraction.repair import apply_repair, build_repair_targets, repair_invoice
from faida_api.extraction.schema import (
    ExtractedInvoice,
    ExtractedLine,
    RepairResult,
    RepairTarget,
)
from faida_api.extraction.validate import CheckStatus, FieldStatus, validate_invoice

USAGE = ProviderUsage(
    model_id="fake-model",
    prompt_version="v0",
    input_tokens=100,
    output_tokens=20,
    latency_ms=5,
)


class FakeProvider:
    """Counts repair calls and returns a canned patch."""

    def __init__(self, patch: RepairResult):
        self._patch = patch
        self.repair_calls: list[list[RepairTarget]] = []

    async def extract(self, image, mime):
        raise AssertionError("the repair pass must never call extract")

    async def repair(self, image, mime, targets):
        self.repair_calls.append(targets)
        return self._patch, USAGE


def _line(qty: str | None, price: str | None, total: str | None, name: str = "item"):
    return ExtractedLine(
        raw_name=name,
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


# --- build_repair_targets ---


def test_targets_only_from_failed_checks():
    # One passing, one failed, one indeterminate line; no document total, so
    # the doc check is indeterminate - exactly one line target comes out.
    invoice = _invoice(
        [
            _line("2", "5.00", "10.00", name="ok"),
            _line("12", "4.50", "58.00", name="bad"),
            _line(None, "3.00", "9.00", name="smudged"),
        ]
    )
    validation = validate_invoice(invoice)
    targets = build_repair_targets(invoice, validation)
    assert len(targets) == 1
    target = targets[0]
    assert target.line_index == 1
    assert target.fields == ["qty", "unit_price", "line_total"]


def test_line_target_reason_quotes_the_arithmetic():
    invoice = _invoice([_line("12", "4.50", "58.00")])
    targets = build_repair_targets(invoice, validate_invoice(invoice))
    reason = targets[0].reason
    assert "Line 0" in reason
    for number in ("12", "4.50", "54.00", "58.00"):
        assert number in reason


def test_document_failure_yields_totals_target():
    # Total 120.00 fits neither C4 identity: exclusive wants 105.00 (line sum
    # + tax), inclusive wants 100.00 (line sum, tax inside). The old fixture
    # here used 100.00, which the amended C4 correctly reads as a valid
    # VAT-inclusive invoice - it is no longer a failure to repair.
    lines = [_line("2", "30.00", "60.00"), _line("4", "10.00", "40.00")]
    invoice = _invoice(lines, tax="5.00", total="120.00")
    targets = build_repair_targets(invoice, validate_invoice(invoice))
    assert len(targets) == 1
    target = targets[0]
    assert target.line_index is None
    assert target.fields == ["subtotal", "tax", "total"]
    for number in ("100.00", "5.00", "105.00"):
        assert number in target.reason


def test_no_failed_checks_yields_no_targets():
    # All-green invoice and an all-indeterminate one both produce nothing:
    # missing values are the question flow's job (§5 layer 5), not repair's.
    green = _invoice([_line("2", "5.00", "10.00")], tax="0.50", total="10.50")
    assert build_repair_targets(green, validate_invoice(green)) == []
    smudged = _invoice([ExtractedLine(raw_name="smudged")])
    assert build_repair_targets(smudged, validate_invoice(smudged)) == []


# --- apply_repair ---


def test_apply_repair_replaces_only_targeted_lines():
    invoice = _invoice(
        [_line("2", "5.00", "10.00", name="keep"), _line("12", "4.50", "58.00", name="fix")],
        subtotal="64.00",
        tax="3.20",
        total="70.00",
    )
    fixed = _line("12", "4.50", "54.00", name="fix")
    patch = RepairResult(lines={1: fixed, 5: _line("9", "9.00", "81.00")}, total="67.20")
    result = apply_repair(invoice, patch)

    assert len(result.lines) == 2  # out-of-range index 5 ignored
    assert result.lines[0] == invoice.lines[0]
    assert result.lines[1] == fixed
    assert result.total == Decimal("67.20")
    # None in the patch means "not re-read": subtotal and tax keep their values.
    assert result.subtotal == Decimal("64.00")
    assert result.tax == Decimal("3.20")


def test_apply_repair_does_not_mutate_the_input():
    invoice = _invoice([_line("12", "4.50", "58.00")], total="58.00")
    snapshot = invoice.model_copy(deep=True)
    result = apply_repair(
        invoice, RepairResult(lines={0: _line("12", "4.50", "54.00")}, total="54.00")
    )
    assert result is not invoice
    assert invoice == snapshot


def test_apply_repair_untouched_fields_survive():
    invoice = ExtractedInvoice(
        supplier_name="Gulf Foods Trading LLC",
        invoice_no="INV-1041",
        currency="AED",
        payment_kind="credit",
        lines=[_line("2", "5.00", "10.00")],
        tax=Decimal("0.50"),
        total=Decimal("10.50"),
    )
    result = apply_repair(invoice, RepairResult())
    assert result == invoice


# --- repair_invoice ---


async def test_repair_invoice_makes_no_call_when_nothing_failed():
    invoice = _invoice([_line("2", "5.00", "10.00")], tax="0.50", total="10.50")
    validation = validate_invoice(invoice)
    fake = FakeProvider(RepairResult())
    outcome = await repair_invoice(fake, b"img", "image/jpeg", invoice, validation)

    assert fake.repair_calls == []
    assert outcome.applied is False
    assert outcome.usage is None
    assert outcome.invoice == invoice
    assert outcome.validation == validation


async def test_repair_invoice_one_call_and_a_fixing_patch_flips_to_passed():
    invoice = _invoice([_line("12", "4.50", "58.00")], tax="0", total="54.00")
    validation = validate_invoice(invoice)
    assert validation.lines[0].arith == CheckStatus.FAILED
    fake = FakeProvider(RepairResult(lines={0: _line("12", "4.50", "54.00")}))
    outcome = await repair_invoice(fake, b"img", "image/jpeg", invoice, validation)

    assert len(fake.repair_calls) == 1
    assert outcome.applied is True
    assert outcome.usage == USAGE
    assert outcome.invoice.lines[0].line_total == Decimal("54.00")
    assert outcome.validation.lines[0].arith == CheckStatus.PASSED
    assert outcome.validation.document.arith == CheckStatus.PASSED


async def test_repair_invoice_non_fixing_patch_stays_failed_after_one_round():
    invoice = _invoice([_line("12", "4.50", "58.00")], tax="0", total="58.00")
    # The patch re-reads the same wrong number - still failing, still amber,
    # and crucially still only ONE provider call: no second round, ever.
    fake = FakeProvider(RepairResult(lines={0: _line("12", "4.50", "58.00")}))
    outcome = await repair_invoice(fake, b"img", "image/jpeg", invoice, validate_invoice(invoice))

    assert len(fake.repair_calls) == 1
    assert outcome.applied is True
    assert outcome.usage == USAGE
    assert outcome.validation.lines[0].arith == CheckStatus.FAILED
    assert outcome.validation.lines[0].status == FieldStatus.AMBER


async def test_repair_invoice_passes_the_built_targets_to_the_provider():
    invoice = _invoice([_line("12", "4.50", "58.00")])
    fake = FakeProvider(RepairResult(lines={0: _line("12", "4.50", "54.00")}))
    await repair_invoice(fake, b"img", "image/jpeg", invoice, validate_invoice(invoice))

    (targets,) = fake.repair_calls
    assert [t.line_index for t in targets] == [0]
    assert "58.00" in targets[0].reason
