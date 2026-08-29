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


def _line_target(index: int, fields=("qty", "unit_price", "line_total")) -> RepairTarget:
    return RepairTarget(line_index=index, fields=list(fields), reason="arithmetic failed")


def _totals_target(fields=("subtotal", "tax", "total")) -> RepairTarget:
    return RepairTarget(line_index=None, fields=list(fields), reason="totals failed")


# --- apply_repair ---


def test_apply_repair_moves_only_targeted_cells_on_targeted_lines():
    invoice = _invoice(
        [_line("2", "5.00", "10.00", name="keep"), _line("12", "4.50", "58.00", name="fix")],
        subtotal="64.00",
        tax="3.20",
        total="70.00",
    )
    fixed = _line("12", "4.50", "54.00", name="fix")
    patch = RepairResult(lines={1: fixed, 5: _line("9", "9.00", "81.00")}, total="67.20")
    result = apply_repair(invoice, patch, [_line_target(1), _totals_target()])

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
        invoice,
        RepairResult(lines={0: _line("12", "4.50", "54.00")}, total="54.00"),
        [_line_target(0), _totals_target()],
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
    result = apply_repair(invoice, RepairResult(), [])
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


# --- a patch is partial, and the refusals that makes necessary ---------------
#
# build_repair_prompt tells the model to return "null for every other field",
# so a patched line arrives carrying nulls for unit and pack_size by
# instruction. Merging it wholesale wrote those nulls over correctly-read
# values, and pack_size is the denominator M5 divides a unit price by. The
# path has never run in anger because Gemini 3 Flash reconciles the corpus
# with zero repair rounds, which is exactly why it needs pinning.


def test_a_repaired_line_keeps_the_unit_and_pack_size_it_already_had():
    original = ExtractedLine(
        raw_name="MILK PWDR 2.5KG NIDO",
        qty=Decimal("12"),
        unit="sack",
        pack_size="2.5kg",
        unit_price=Decimal("54.50"),
        line_total=Decimal("658.00"),  # wrong: 12 x 54.50 = 654.00
    )
    # What the prompt actually asks for: the row confirmed by name, fresh
    # readings for the targeted cells, null for everything else.
    patched = ExtractedLine(
        raw_name="MILK PWDR 2.5KG NIDO",
        qty=Decimal("12"),
        unit=None,
        pack_size=None,
        unit_price=Decimal("54.50"),
        line_total=Decimal("654.00"),
    )
    result = apply_repair(
        _invoice([original], total="654.00"),
        RepairResult(lines={0: patched}),
        [_line_target(0)],
    )
    line = result.lines[0]
    assert line.line_total == Decimal("654.00")  # the targeted cell moved
    assert (line.unit, line.pack_size) == ("sack", "2.5kg")  # and nothing else went missing


def test_a_null_on_a_targeted_cell_keeps_the_old_value():
    # "A cell you still cannot read stays null; never guess" means the model
    # could not read it, not that the cell is empty. The old value stays, still
    # fails its check, and goes amber for the question flow.
    original = _line("12", "4.50", "58.00", name="fix")
    patched = ExtractedLine(raw_name="fix", qty=None, unit_price=None, line_total=Decimal("54.00"))
    result = apply_repair(
        _invoice([original], total="58.00"), RepairResult(lines={0: patched}), [_line_target(0)]
    )
    assert result.lines[0].qty == Decimal("12")
    assert result.lines[0].unit_price == Decimal("4.50")
    assert result.lines[0].line_total == Decimal("54.00")


def test_a_patch_for_a_line_nobody_asked_about_is_dropped():
    # Only line 1 failed. A patch that also rewrites line 0 is not evidence
    # about line 0, whatever it claims.
    invoice = _invoice(
        [_line("2", "5.00", "10.00", name="keep"), _line("12", "4.50", "58.00", name="fix")],
        total="68.00",
    )
    patch = RepairResult(
        lines={
            0: _line("99", "99.00", "9801.00", name="keep"),
            1: _line("12", "4.50", "54.00", name="fix"),
        }
    )
    result = apply_repair(invoice, patch, [_line_target(1)])
    assert result.lines[0] == invoice.lines[0]
    assert result.lines[1].line_total == Decimal("54.00")


def test_a_patch_whose_row_does_not_match_is_rejected():
    # raw_name is asked for "to confirm the row". A patch keyed to the wrong
    # index must never silently rewrite another line's money.
    invoice = _invoice([_line("12", "4.50", "58.00", name="Basmati Rice 5kg")], total="58.00")
    patch = RepairResult(lines={0: _line("3", "1.00", "3.00", name="Sunflower Oil 5L")})
    assert apply_repair(invoice, patch, [_line_target(0)]) == invoice


def test_a_cleaner_second_read_of_the_same_row_is_still_the_same_row():
    # EDGE-01: the first pass folded a handwritten margin note into the name.
    # A cleaner re-read is a better answer, not a different line.
    invoice = _invoice(
        [_line("5", "92.00", "465.00", name="Avocado Credit: one box returned, soft fruit")],
        total="465.00",
    )
    patch = RepairResult(lines={0: _line("5", "92.00", "460.00", name="Avocado")})
    result = apply_repair(invoice, patch, [_line_target(0)])
    assert result.lines[0].line_total == Decimal("460.00")


def test_totals_move_only_when_the_totals_block_was_targeted():
    invoice = _invoice([_line("2", "5.00", "10.00")], subtotal="10.00", tax="0.50", total="10.50")
    patch = RepairResult(subtotal="99.00", tax="9.00", total="108.00")
    # Only a line failed, so an unrequested totals rewrite is dropped.
    untargeted = apply_repair(invoice, patch, [_line_target(0)])
    assert (untargeted.subtotal, untargeted.tax, untargeted.total) == (
        Decimal("10.00"),
        Decimal("0.50"),
        Decimal("10.50"),
    )
    targeted = apply_repair(invoice, patch, [_totals_target()])
    assert targeted.total == Decimal("108.00")
