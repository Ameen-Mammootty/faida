"""Live provider runs for the eval harness (WP-16, plan.md §5).

`python -m eval.run --live` scores real `claude-opus-5` calls instead of the
recorded fixtures, which is what the accuracy loop needs: recorded responses
can only prove the scorer still works, never that a prompt change helped.

The one rule this module exists to keep: a live case runs the layers the
product runs, in the product's order, through the product's modules -
extract (layer 1), the pipeline's currency normalization, `validate_invoice`
(layer 2), one scoped `repair_invoice` round (layer 3). Re-implementing any
of that here would score a program we do not ship, which is the trap
`eval/score.py` fell into with its own copy of C4.
"""

import asyncio
import os
from pathlib import Path

from faida_api.extraction.normalize import normalize_extracted
from faida_api.extraction.pipeline import build_provider
from faida_api.extraction.provider import ExtractionProvider, ProviderUsage
from faida_api.extraction.repair import repair_invoice
from faida_api.extraction.schema import Classification, ExtractionResult
from faida_api.extraction.validate import (
    CheckStatus,
    ValidationResult,
    validate_invoice,
)

from eval.score import score_case

# Live calls are slow (tens of seconds each) and independent, so cases run
# concurrently. Kept modest: the ceiling here is the API's rate limit, and a
# 429 storm costs more wall-clock than it saves.
DEFAULT_CONCURRENCY = 3


class LiveProviderUnavailable(RuntimeError):
    """No API key (or, for gemini, no SDK), so there is nothing to run.
    Raised before any case starts rather than failing every case
    identically."""


# The shipped provider first; gemini is the bake-off lane (2026-08-29) and
# exists here only - pipeline.build_provider never constructs it.
LIVE_PROVIDERS = ("anthropic", "gemini")
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}


def live_model_id(provider_name: str) -> str:
    """The model id a live run would use, for the banner and the results
    payload. One place reads GEMINI_MODEL_ID so the builder and the report
    can never disagree about which model ran."""
    if provider_name == "gemini":
        from faida_api.extraction.gemini_provider import MODEL_ID as gemini_model_id

        return os.environ.get("GEMINI_MODEL_ID") or gemini_model_id
    from faida_api.extraction.anthropic_provider import MODEL_ID as anthropic_model_id

    return anthropic_model_id


def build_live_provider(
    api_key: str | None, provider_name: str = "anthropic"
) -> ExtractionProvider:
    if provider_name == "anthropic":
        provider = build_provider(api_key or "")
        if provider is None:
            raise LiveProviderUnavailable(
                "ANTHROPIC_API_KEY is not set; --live needs a real key (F5). "
                "Run without --live to score recorded responses."
            )
        return provider
    if provider_name == "gemini":
        if not api_key:
            raise LiveProviderUnavailable(
                "GEMINI_API_KEY is not set; --live --provider gemini needs one."
            )
        try:
            from faida_api.extraction.gemini_provider import GeminiExtractionProvider
            from google import genai
        except ImportError as exc:
            raise LiveProviderUnavailable(
                "google-genai is not installed; it is an optional extra - "
                "pip install -e 'apps/api[gemini]'."
            ) from exc
        return GeminiExtractionProvider(
            genai.Client(api_key=api_key), model_id=live_model_id(provider_name)
        )
    raise LiveProviderUnavailable(f"unknown provider {provider_name!r} (see LIVE_PROVIDERS)")


def combine_usage(extract: ProviderUsage, repair: ProviderUsage | None) -> ProviderUsage:
    """One usage row per invoice, extract plus any repair round - plan.md §10
    prices the pipeline "incl. repair pass", so the eval must too. Latency
    sums because the calls are sequential on the demo path."""
    if repair is None:
        return extract
    return ProviderUsage(
        model_id=extract.model_id,
        prompt_version=extract.prompt_version,
        input_tokens=extract.input_tokens + repair.input_tokens,
        output_tokens=extract.output_tokens + repair.output_tokens,
        latency_ms=extract.latency_ms + repair.latency_ms,
    )


def _reconciles(validation: ValidationResult) -> bool:
    """Same verdict as eval.score.invoice_reconciles, from a validation that
    has already been computed (the live path validates twice: before and
    after repair)."""
    return validation.document.arith is CheckStatus.PASSED and all(
        check.arith is CheckStatus.PASSED for check in validation.lines
    )


async def run_case_live(
    provider: ExtractionProvider,
    case_dir: Path,
    image: bytes,
    mime: str,
) -> tuple[dict, ExtractionResult, ExtractionResult, ProviderUsage]:
    """Extract -> validate -> one repair round -> score, mirroring
    `pipeline._persist_extracted`.

    Returns the case score, the post-repair result that was scored (what the
    failure report explains), and the raw pre-repair extraction with its usage,
    which is what `--record` writes - the recorded provider replays the extract
    call alone, so recording the repaired invoice would record a response no
    single call ever produced.
    """
    truth = ExtractionResult.model_validate_json((case_dir / "truth.json").read_text())
    extracted, extract_usage = await provider.extract(image, mime)

    if extracted.classification is not Classification.INVOICE or extracted.invoice is None:
        # Nothing to reconcile or repair: a decline is scored on its
        # classification alone (NEG-01 is exactly this case).
        score = score_case(extracted, truth, extract_usage)
        return score, extracted, extracted, extract_usage

    # The pipeline's own derivation seam (ISO currency, cash-or-credit from the
    # printed terms), called rather than copied, so the eval scores the invoice
    # the database would have stored.
    invoice = normalize_extracted(extracted.invoice)
    validation = validate_invoice(invoice)
    before = _reconciles(validation)

    outcome = await repair_invoice(provider, image, mime, invoice, validation)
    repaired = extracted.model_copy(update={"invoice": outcome.invoice})
    usage = combine_usage(extract_usage, outcome.usage)

    case = score_case(repaired, truth, usage, reconciled_before_repair=before)
    return case, repaired, extracted, extract_usage


async def run_corpus_live(
    cases: list[tuple[Path, bytes, str]],
    provider: ExtractionProvider,
    concurrency: int = DEFAULT_CONCURRENCY,
    record: bool = False,
) -> tuple[dict[str, dict], dict[str, ExtractionResult], dict[str, str]]:
    """Score every case concurrently. One case failing (an overloaded API, a
    refusal, an unreadable response) is recorded and does not abort the run -
    an accuracy round that dies on case 3 of 14 wastes the other eleven
    calls."""
    semaphore = asyncio.Semaphore(max(1, concurrency))
    scores: dict[str, dict] = {}
    results: dict[str, ExtractionResult] = {}
    errors: dict[str, str] = {}

    async def one(case_dir: Path, image: bytes, mime: str) -> None:
        async with semaphore:
            try:
                case, scored, raw, usage = await run_case_live(provider, case_dir, image, mime)
            except Exception as exc:  # noqa: BLE001 - reported per case, never swallowed
                errors[case_dir.name] = f"{type(exc).__name__}: {exc}"
                return
            scores[case_dir.name] = case
            results[case_dir.name] = scored
            if record:
                write_recording(case_dir, raw, usage)

    await asyncio.gather(*(one(d, image, mime) for d, image, mime in cases))
    return scores, results, errors


def write_recording(case_dir: Path, extracted: ExtractionResult, usage: ProviderUsage) -> None:
    """Refresh the recorded provider's replay files for one case (plan.md §5
    CI policy: regenerate whenever the prompt version bumps). Only the extract
    call is recorded, because that is all RecordedProvider replays."""
    (case_dir / "recorded.json").write_text(extracted.model_dump_json(indent=2) + "\n")
    (case_dir / "usage.json").write_text(usage.model_dump_json(indent=2) + "\n")
