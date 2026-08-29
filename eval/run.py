"""Eval runner: `python -m eval.run` (plan.md §5).

Runs a case directory against a provider (default: recorded responses on
disk), prints the per-field/per-metric table, and writes
eval/results/<date>.json (gitignored) so runs are comparable. `--smoke` runs
the bundled fixtures and exits nonzero if any score differs from the fixtures'
expected values, which keeps the scorer itself regression-tested in CI.
`--live` (WP-16) calls the real provider instead, scoring the pipeline's own
layers 1-3; see eval/live.py.
"""

import argparse
import asyncio
import datetime
import json
import os
import sys
from pathlib import Path

from faida_api.extraction.normalize import normalize_extracted
from faida_api.extraction.prompts import PROMPT_VERSION
from faida_api.extraction.provider import ExtractionProvider
from faida_api.extraction.schema import ExtractionResult

from eval.live import (
    DEFAULT_CONCURRENCY,
    KEY_ENV,
    LIVE_PROVIDERS,
    SHIPPED_PROVIDER,
    LiveProviderUnavailable,
    build_live_provider,
    live_model_id,
    run_corpus_live,
)
from eval.recorded import RecordedProvider
from eval.score import HEADER_FIELDS, LINE_FIELDS, aggregate, explain_case, score_case

EVAL_DIR = Path(__file__).resolve().parent
CORPUS_DIR = EVAL_DIR / "corpus"
FIXTURES_DIR = EVAL_DIR / "fixtures"
RESULTS_DIR = EVAL_DIR / "results"  # gitignored

_IMAGE_MIMES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".pdf": "application/pdf",
}


def discover_cases(corpus: Path) -> list[Path]:
    if not corpus.is_dir():
        return []
    return sorted(d for d in corpus.iterdir() if d.is_dir() and (d / "truth.json").exists())


def find_image(case_dir: Path) -> tuple[Path, str] | None:
    """The corpus layout names the file `image.jpg`; the generated set names
    it after its case (`TH-01/TH-01.jpg`). Both are read, so `--live` can run
    over either without copying files around."""
    for stem in ("image", case_dir.name):
        for suffix, mime in _IMAGE_MIMES.items():
            candidate = case_dir / f"{stem}{suffix}"
            if candidate.exists():
                return candidate, mime
    return None


def _load_image(case_dir: Path) -> tuple[bytes, str]:
    found = find_image(case_dir)
    if found is None:
        # Fixture cases ship no image; the recorded provider never reads it.
        return b"", "image/jpeg"
    path, mime = found
    return path.read_bytes(), mime


async def run_case(case_dir: Path) -> tuple[dict, ExtractionResult]:
    """Replay one recorded extraction and score it.

    The pipeline's derivation seam runs here too. Without it a replay scores
    the raw provider answer while a live run scores the normalized one, so the
    same recording would produce two different numbers depending on how it was
    read - the harness drifting from the product again, quietly. Repair is not
    replayed (only the extract call is recorded), so lift stays null.
    """
    provider: ExtractionProvider = RecordedProvider(case_dir)
    image, mime = _load_image(case_dir)
    result, usage = await provider.extract(image, mime)
    if result.invoice is not None:
        result = result.model_copy(update={"invoice": normalize_extracted(result.invoice)})
    truth = ExtractionResult.model_validate_json((case_dir / "truth.json").read_text())
    return score_case(result, truth, usage), result


async def run_corpus(
    case_dirs: list[Path],
) -> tuple[dict[str, dict], dict[str, ExtractionResult], dict[str, str]]:
    """A case with no recording is reported, not fatal - the same courtesy the
    live path gives a case that fails mid-run. Five of the generated cases are
    ground truth for images nobody has generated yet, and they must not stop
    the other ten from scoring."""
    scores: dict[str, dict] = {}
    results: dict[str, ExtractionResult] = {}
    errors: dict[str, str] = {}
    for case_dir in case_dirs:
        if not (case_dir / "recorded.json").exists():
            errors[case_dir.name] = (
                "no recorded.json; run --live --record for this case, or drop it from the corpus"
            )
            continue
        scores[case_dir.name], results[case_dir.name] = await run_case(case_dir)
    return scores, results, errors


def _pct(rate: float | None) -> str:
    return "-" if rate is None else f"{rate * 100:.1f}%"


def print_table(agg: dict) -> None:
    rows: list[tuple[str, str, str]] = []
    cls = agg["classification"]
    rows.append(("classification", _pct(cls["accuracy"]), f"{cls['correct']}/{cls['total']}"))
    for field in HEADER_FIELDS:
        tally = agg["header_fields"][field]
        rows.append(
            (
                f"header {field}",
                _pct(tally["accuracy"]),
                f"{tally['correct']}/{tally['total']}",
            )
        )
    lines = agg["lines"]
    rows.append(
        (
            "line recall",
            _pct(lines["recall"]),
            f"{lines['matched']}/{lines['truth_count']}",
        )
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
            (
                f"line {field}",
                _pct(tally["accuracy"]),
                f"{tally['correct']}/{tally['total']}",
            )
        )
    rec = agg["reconciliation"]
    rows.append(
        (
            "reconciliation",
            _pct(rec["rate"]),
            f"{rec['reconciled']}/{rec['applicable']}",
        )
    )

    print(f"{'metric':<24}{'score':>8}  {'n':>6}")
    for name, score, n in rows:
        print(f"{name:<24}{score:>8}  {n:>6}")

    lift = agg["repair_lift"]
    if lift["reconciliation_rate_before_repair"] is not None:
        print(
            f"{'repair lift':<24}"
            f"{_pct(lift['reconciliation_rate_before_repair']):>8} -> "
            f"{_pct(lift['reconciliation_rate_after_repair'])} reconciled"
        )

    usage = agg["usage"]
    if usage is not None:
        cost = usage["avg_cost_usd"]
        cost_text = "cost unpriced" if cost is None else f"${cost:.4f}"
        print(
            f"per invoice: {usage['avg_input_tokens']} in / {usage['avg_output_tokens']} out "
            f"tokens, {usage['avg_latency_ms']} ms, {cost_text} "
            f"(over {usage['cases_with_usage']} runs)"
        )


def print_failures(explanations: dict[str, dict], limit: int = 12) -> None:
    """What actually differed, per case (WP-16). A boolean says a field is
    wrong; this says whether the model or the ground truth is."""
    reported = False
    for name in sorted(explanations):
        detail = explanations[name]
        rows: list[str] = []
        if detail["classification"] is not None:
            c = detail["classification"]
            rows.append(f"    classification: got {c['extracted']!r}, truth {c['truth']!r}")
        for field, pair in detail["header_fields"].items():
            rows.append(f"    {field}: got {pair['extracted']!r}, truth {pair['truth']!r}")
        for entry in detail["lines"][:limit]:
            rows.append(
                f"    line {entry['line']} {entry['field']}: "
                f"got {entry['extracted']!r}, truth {entry['truth']!r}"
            )
        if len(detail["lines"]) > limit:
            rows.append(f"    ... and {len(detail['lines']) - limit} more line fields")
        for entry in detail["unmatched"]:
            rows.append(f"    unmatched ({entry['side']}): {entry['raw_name']!r}")
        if not rows:
            continue
        if not reported:
            print("\nmismatches (got = extracted, truth = ground truth):")
            reported = True
        print(f"  {name}")
        for row in rows:
            print(row)


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
        prog="python -m eval.run",
        description="Score the extraction corpus (plan.md §5).",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=None,
        help="case directory (default: eval/corpus)",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="run the bundled fixtures and verify the expected scores",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="call the real provider instead of replaying recordings (WP-16; spends money)",
    )
    parser.add_argument(
        "--only",
        action="append",
        metavar="CASE",
        help="run just this case (repeatable) - the accuracy loop's inner iteration",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"live cases in flight at once (default {DEFAULT_CONCURRENCY})",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="with --live, refresh each case's recorded.json/usage.json (§5 CI policy)",
    )
    parser.add_argument(
        "--provider",
        choices=LIVE_PROVIDERS,
        default=SHIPPED_PROVIDER,
        help=f"live provider to call (default {SHIPPED_PROVIDER}, the shipped one; "
        "anthropic is the Opus 5 fallback and reads ANTHROPIC_API_KEY)",
    )
    args = parser.parse_args(argv)
    if args.smoke and args.live:
        parser.error("--smoke replays recordings by design (§5 CI policy: no key, no spend)")
    if args.record and not args.live:
        parser.error("--record rewrites recordings from live responses; it needs --live")
    if args.record and args.provider != SHIPPED_PROVIDER:
        # The recorded fixtures are the CI baseline for the SHIPPED provider;
        # overwriting them with another model's answers would silently move
        # what the smoke gate certifies.
        parser.error(f"--record is reserved for the shipped provider ({SHIPPED_PROVIDER})")

    corpus = (
        args.corpus if args.corpus is not None else (FIXTURES_DIR if args.smoke else CORPUS_DIR)
    )
    case_dirs = discover_cases(corpus)
    if args.only:
        wanted = set(args.only)
        case_dirs = [d for d in case_dirs if d.name in wanted]
        missing = wanted - {d.name for d in case_dirs}
        if missing:
            print(
                f"no such case under {corpus}: {', '.join(sorted(missing))}",
                file=sys.stderr,
            )
            return 1
    if not case_dirs:
        print(
            f"no cases found under {corpus} - see eval/README.md for the layout",
            file=sys.stderr,
        )
        return 1

    errors: dict[str, str] = {}
    if args.live:
        try:
            provider = build_live_provider(os.environ.get(KEY_ENV[args.provider]), args.provider)
        except LiveProviderUnavailable as exc:
            print(str(exc), file=sys.stderr)
            return 1
        live_cases = []
        for case_dir in case_dirs:
            found = find_image(case_dir)
            if found is None:
                errors[case_dir.name] = "no image in the case directory; --live needs one"
                continue
            path, mime = found
            live_cases.append((case_dir, path.read_bytes(), mime))
        if not live_cases:
            print(f"no case under {corpus} carries an image to send", file=sys.stderr)
            return 1
        print(
            f"live: {len(live_cases)} cases against {live_model_id(args.provider)} "
            f"prompt {PROMPT_VERSION}, "
            f"{args.concurrency} at a time - this spends money and takes minutes\n"
        )
        scores, results, live_errors = asyncio.run(
            run_corpus_live(live_cases, provider, args.concurrency, args.record)
        )
        errors.update(live_errors)
    else:
        scores, results, recorded_errors = asyncio.run(run_corpus(case_dirs))
        errors.update(recorded_errors)

    agg = aggregate(list(scores.values()))
    print(f"eval: {len(scores)} cases scored from {corpus}\n")
    print_table(agg)

    truths = {
        d.name: ExtractionResult.model_validate_json((d / "truth.json").read_text())
        for d in case_dirs
        if d.name in results
    }
    explanations = {name: explain_case(result, truths[name]) for name, result in results.items()}
    print_failures(explanations)

    payload = {
        "run": {
            "date": _today(),
            "generated_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
            "provider": "live" if args.live else "recorded",
            "corpus": str(corpus),
            "smoke": args.smoke,
            "cases": len(scores),
            # plan.md §5, phase 1: a number measured on generated invoices is
            # never quoted as pilot accuracy. The corpus path is the label.
            "synthetic_corpus": "generated" in corpus.parts or corpus == FIXTURES_DIR,
        },
        "aggregate": agg,
        "cases": scores,
        "mismatches": explanations,
        "errors": errors,
    }
    if args.live:
        # run.provider above stays the live/recorded marker; this names which
        # live implementation answered (the bake-off comparison key).
        payload["run"]["live_provider"] = args.provider
        payload["run"]["model_id"] = live_model_id(args.provider)
        payload["run"]["prompt_version"] = PROMPT_VERSION
    path = write_results(payload)
    print(f"\nwrote {path}")

    if errors:
        print(f"\n{len(errors)} case(s) did not score:", file=sys.stderr)
        for name, message in sorted(errors.items()):
            print(f"  {name}: {message}", file=sys.stderr)
        return 1

    if args.smoke:
        failures = check_expected(case_dirs, scores, agg)
        if failures:
            print(
                "\nsmoke FAILED: scorer output drifted from the fixtures",
                file=sys.stderr,
            )
            for failure in failures:
                print(failure, file=sys.stderr)
            return 1
        print("smoke OK: all fixture scores match expected values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
