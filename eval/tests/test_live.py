"""Live-runner tests (WP-16). No key, no network: a fake provider stands in
for Anthropic so the orchestration - repair lift, usage combination, per-case
error isolation, recording - is testable in CI.

Run from the repo root: apps/api/.venv/bin/python -m pytest eval/tests -q
"""

import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest
from faida_api.extraction.provider import ProviderUsage
from faida_api.extraction.schema import (
    Classification,
    ExtractedInvoice,
    ExtractedLine,
    ExtractionResult,
    RepairResult,
)

from eval.live import (
    LiveProviderUnavailable,
    build_live_provider,
    combine_usage,
    run_corpus_live,
)

USAGE = ProviderUsage(
    model_id="claude-opus-5",
    prompt_version="test-v1",
    input_tokens=4000,
    output_tokens=800,
    latency_ms=20_000,
)


def invoice(line_total: str, total: str = "100.00") -> ExtractionResult:
    return ExtractionResult(
        classification=Classification.INVOICE,
        invoice=ExtractedInvoice(
            supplier_name="Gulf Fresh",
            currency="AED",
            total=Decimal(total),
            lines=[
                ExtractedLine(
                    raw_name="Tomato Box 5kg",
                    qty=Decimal(4),
                    unit_price=Decimal("25.00"),
                    line_total=Decimal(line_total),
                )
            ],
        ),
    )


class FakeProvider:
    """Returns a scripted extraction; repair fixes the line total. Records how
    many times each call was made."""

    def __init__(self, result: ExtractionResult, repair_to: str | None = None) -> None:
        self._result = result
        self._repair_to = repair_to
        self.extract_calls = 0
        self.repair_calls = 0

    async def extract(self, image: bytes, mime: str):
        self.extract_calls += 1
        return self._result, USAGE

    async def repair(self, image: bytes, mime: str, targets: list):
        self.repair_calls += 1
        patch = RepairResult(
            lines={
                0: self._result.invoice.lines[0].model_copy(
                    update={"line_total": Decimal(self._repair_to)}
                )
            }
        )
        return patch, USAGE.model_copy(update={"input_tokens": 1000, "output_tokens": 100})


class ExplodingProvider:
    async def extract(self, image: bytes, mime: str):
        raise RuntimeError("overloaded_error: 529")

    async def repair(self, image: bytes, mime: str, targets: list):  # pragma: no cover
        raise AssertionError("repair must not run after extract failed")


def write_case(tmp_path: Path, name: str, truth: ExtractionResult) -> Path:
    case = tmp_path / name
    case.mkdir()
    (case / "truth.json").write_text(truth.model_dump_json())
    return case


def test_repair_lift_is_measured_across_the_repair_round(tmp_path):
    """The pre-repair invoice does not reconcile (4 x 25.00 != 90.00); repair
    fixes the line total to 100.00. The case must score post-repair and still
    report that it needed the round - that difference is the lift §5 layer 3
    asks for."""
    truth = invoice("100.00")
    case = write_case(tmp_path, "R-01", truth)
    provider = FakeProvider(invoice("90.00"), repair_to="100.00")

    scores, results, errors = asyncio.run(
        run_corpus_live([(case, b"jpeg-bytes", "image/jpeg")], provider)
    )

    assert errors == {}
    assert provider.repair_calls == 1
    result = scores["R-01"]
    assert result["reconciliation"]["reconciled"] is True
    assert result["reconciliation"]["reconciled_before_repair"] is False
    # Usage covers both calls (plan.md §10 prices the pipeline incl. repair).
    assert result["usage"]["input_tokens"] == 5000
    assert result["usage"]["output_tokens"] == 900
    assert result["cost_usd"] == pytest.approx(5000 * 5 / 1e6 + 900 * 25 / 1e6)
    # The result handed back for the failure report is the repaired one, so a
    # mismatch listing shows what was finally scored, not the first read.
    assert results["R-01"].invoice.lines[0].line_total == Decimal("100.00")


def test_clean_invoice_never_calls_repair(tmp_path):
    truth = invoice("100.00")
    case = write_case(tmp_path, "C-01", truth)
    provider = FakeProvider(invoice("100.00"))

    scores, results, errors = asyncio.run(
        run_corpus_live([(case, b"jpeg-bytes", "image/jpeg")], provider)
    )

    assert errors == {}
    assert provider.repair_calls == 0
    assert scores["C-01"]["reconciliation"]["reconciled_before_repair"] is True
    assert scores["C-01"]["usage"]["input_tokens"] == 4000


def test_one_failing_case_does_not_abort_the_others(tmp_path):
    """An accuracy round that dies on case 2 of 3 wastes the calls already
    spent on the rest."""
    good = write_case(tmp_path, "OK-01", invoice("100.00"))
    bad = write_case(tmp_path, "BAD-01", invoice("100.00"))

    async def run():
        ok_scores, _, ok_errors = await run_corpus_live(
            [(good, b"x", "image/jpeg")], FakeProvider(invoice("100.00"))
        )
        bad_scores, _, bad_errors = await run_corpus_live(
            [(bad, b"x", "image/jpeg")], ExplodingProvider()
        )
        return ok_scores | bad_scores, ok_errors | bad_errors

    scores, errors = asyncio.run(run())
    assert "OK-01" in scores
    assert "BAD-01" not in scores
    assert "overloaded_error" in errors["BAD-01"]
    assert errors["BAD-01"].startswith("RuntimeError:")


def test_record_refreshes_the_replay_files_with_the_pre_repair_extraction(tmp_path):
    """RecordedProvider replays the extract call alone, so the recording must
    be what the model actually returned - not the repaired invoice, which no
    single call ever produced."""
    case = write_case(tmp_path, "R-02", invoice("100.00"))
    provider = FakeProvider(invoice("90.00"), repair_to="100.00")

    asyncio.run(run_corpus_live([(case, b"x", "image/jpeg")], provider, concurrency=1, record=True))

    recorded = json.loads((case / "recorded.json").read_text())
    assert recorded["invoice"]["lines"][0]["line_total"] == "90.00"
    usage = json.loads((case / "usage.json").read_text())
    assert usage["input_tokens"] == 4000  # the extract call, not the sum


def test_a_decline_scores_without_touching_repair(tmp_path):
    """NEG-01's shape: not an invoice, so there is nothing to reconcile."""
    case = write_case(
        tmp_path,
        "NEG-01",
        ExtractionResult(classification=Classification.OTHER, invoice=None),
    )
    provider = FakeProvider(ExtractionResult(classification=Classification.OTHER, invoice=None))

    scores, results, errors = asyncio.run(run_corpus_live([(case, b"x", "image/jpeg")], provider))

    assert errors == {}
    assert provider.repair_calls == 0
    assert scores["NEG-01"]["classification"]["correct"] is True
    assert scores["NEG-01"]["reconciliation"]["applicable"] is False


def test_missing_api_key_fails_before_any_case_runs():
    with pytest.raises(LiveProviderUnavailable, match="ANTHROPIC_API_KEY"):
        build_live_provider(None)


def test_combine_usage_sums_both_calls():
    combined = combine_usage(USAGE, USAGE)
    assert combined.input_tokens == 8000
    assert combined.latency_ms == 40_000
    assert combined.model_id == USAGE.model_id
    assert combine_usage(USAGE, None) is USAGE
