"""Eval runner: `python -m eval.run` (plan.md §5).

Runs a case directory against a provider (default: recorded responses on
disk), prints the per-field/per-metric table, and writes
eval/results/<date>.json (gitignored) so runs are comparable. `--smoke` runs
the bundled fixtures and exits nonzero if any score differs from the fixtures'
expected values, which keeps the scorer itself regression-tested in CI.
`--live` is reserved for WP-16.
"""

import argparse
import asyncio
import datetime
import json
import sys
from pathlib import Path

from eval.recorded import RecordedProvider
from eval.score import HEADER_FIELDS, LINE_FIELDS, aggregate, score_case
from faida_api.extraction.provider import ExtractionProvider
from faida_api.extraction.schema import ExtractionResult

EVAL_DIR = Path(__file__).resolve().parent
CORPUS_DIR = EVAL_DIR / "corpus"
FIXTURES_DIR = EVAL_DIR / "fixtures"
RESULTS_DIR = EVAL_DIR / "results"  # gitignored

_IMAGE_MIMES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def discover_cases(corpus: Path) -> list[Path]:
    if not corpus.is_dir():
        return []
    return sorted(d for d in corpus.iterdir() if d.is_dir() and (d / "truth.json").exists())


def _load_image(case_dir: Path) -> tuple[bytes, str]:
    for suffix, mime in _IMAGE_MIMES.items():
        candidate = case_dir / f"image{suffix}"
        if candidate.exists():
            return candidate.read_bytes(), mime
    # Fixture cases ship no image; the recorded provider never reads it.
    return b"", "image/jpeg"


async def run_case(case_dir: Path) -> dict:
    provider: ExtractionProvider = RecordedProvider(case_dir)
    image, mime = _load_image(case_dir)
    result, usage = await provider.extract(image, mime)
    truth = ExtractionResult.model_validate_json((case_dir / "truth.json").read_text())
    return score_case(result, truth, usage)


async def run_corpus(case_dirs: list[Path]) -> dict[str, dict]:
    return {case_dir.name: await run_case(case_dir) for case_dir in case_dirs}


def _pct(rate: float | None) -> str:
    return "-" if rate is None else f"{rate * 100:.1f}%"


def print_table(agg: dict) -> None:
    rows: list[tuple[str, str, str]] = []
    cls = agg["classification"]
    rows.append(("classification", _pct(cls["accuracy"]), f"{cls['correct']}/{cls['total']}"))
    for field in HEADER_FIELDS:
        tally = agg["header_fields"][field]
        rows.append(
            (f"header {field}", _pct(tally["accuracy"]), f"{tally['correct']}/{tally['total']}")
        )
    lines = agg["lines"]
    rows.append(
        ("line recall", _pct(lines["recall"]), f"{lines['matched']}/{lines['truth_count']}")
    )
    rows.append(
        (
            "line precision",
            _pct(lines["precision"]),
            f"{lines['matched']}/{lines['extracted_count']}",
        )
    )
    for field in LINE_FIELDS:
        tally = lines["fields"][field]
        rows.append(
            (f"line {field}", _pct(tally["accuracy"]), f"{tally['correct']}/{tally['total']}")
        )
    rec = agg["reconciliation"]
    rows.append(("reconciliation", _pct(rec["rate"]), f"{rec['reconciled']}/{rec['applicable']}"))

    print(f"{'metric':<24}{'score':>8}  {'n':>6}")
    for name, score, n in rows:
        print(f"{name:<24}{score:>8}  {n:>6}")

    usage = agg["usage"]
    if usage is not None:
        print(
            f"per invoice: {usage['avg_input_tokens']} in / {usage['avg_output_tokens']} out "
            f"tokens, {usage['avg_latency_ms']} ms "
            f"(over {usage['cases_with_usage']} recorded runs; cost arrives with WP-16)"
        )


def _today() -> str:
    return datetime.datetime.now(datetime.UTC).date().isoformat()


def write_results(payload: dict) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{_today()}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def check_expected(case_dirs: list[Path], scores: dict[str, dict], agg: dict) -> list[str]:
    """Compare computed scores against the fixtures' expected values."""
    failures = []
    for case_dir in case_dirs:
        expected = json.loads((case_dir / "expected.json").read_text())
        actual = scores[case_dir.name]
        if actual != expected:
            failures.append(
                f"{case_dir.name}: score differs from expected.json\n"
                f"  expected: {json.dumps(expected, sort_keys=True)}\n"
                f"  actual:   {json.dumps(actual, sort_keys=True)}"
            )
    expected_agg = json.loads((FIXTURES_DIR / "expected_aggregate.json").read_text())
    if agg != expected_agg:
        failures.append(
            "aggregate: differs from expected_aggregate.json\n"
            f"  expected: {json.dumps(expected_agg, sort_keys=True)}\n"
            f"  actual:   {json.dumps(agg, sort_keys=True)}"
        )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m eval.run", description="Score the extraction corpus (plan.md §5)."
    )
    parser.add_argument(
        "--corpus", type=Path, default=None, help="case directory (default: eval/corpus)"
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="run the bundled fixtures and verify the expected scores",
    )
    parser.add_argument(
        "--live", action="store_true", help="reserved for WP-16; not implemented yet"
    )
    args = parser.parse_args(argv)
    if args.live:
        parser.error("--live arrives with WP-16; only the recorded provider exists today")

    corpus = (
        args.corpus if args.corpus is not None else (FIXTURES_DIR if args.smoke else CORPUS_DIR)
    )
    case_dirs = discover_cases(corpus)
    if not case_dirs:
        print(f"no cases found under {corpus} - see eval/README.md for the layout", file=sys.stderr)
        return 1

    scores = asyncio.run(run_corpus(case_dirs))
    agg = aggregate(list(scores.values()))
    print(f"eval: {len(case_dirs)} cases from {corpus}\n")
    print_table(agg)

    payload = {
        "run": {
            "date": _today(),
            "generated_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
            "provider": "recorded",
            "corpus": str(corpus),
            "smoke": args.smoke,
            "cases": len(case_dirs),
        },
        "aggregate": agg,
        "cases": scores,
    }
    path = write_results(payload)
    print(f"\nwrote {path}")

    if args.smoke:
        failures = check_expected(case_dirs, scores, agg)
        if failures:
            print("\nsmoke FAILED: scorer output drifted from the fixtures", file=sys.stderr)
            for failure in failures:
                print(failure, file=sys.stderr)
            return 1
        print("smoke OK: all fixture scores match expected values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
