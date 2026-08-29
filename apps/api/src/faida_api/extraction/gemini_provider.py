"""Gemini implementation of the C3 provider seam - EXPERIMENT LANE ONLY.

Built for the Gemini 3 Pro bake-off against the Opus 5 baseline (plan.md
Progress Log 2026-08-29). The production default stays Anthropic:
`pipeline.build_provider` never constructs this class, only
`eval.live.build_live_provider --provider gemini` does, and `google-genai` is
an optional extra (`pip install -e '.[gemini]'`), never a hard dependency.

The prompt text is shared verbatim with the Anthropic provider (same
PROMPT_VERSION recorded), so eval runs are comparable model-to-model. The one
schema difference: Gemini's response-schema flavor expresses the pinned
ExtractionResult directly (Money fields cross as strings, C4), but not
RepairResult's int-keyed dict - so repair uses the same list-shaped wire
models as `anthropic_provider._RepairOutput` and re-keys the patch.
"""

import time
from decimal import Decimal
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from .images import fit_for_vision
from .prompts import EXTRACT_PROMPT, PROMPT_VERSION, SYSTEM_PROMPT, build_repair_prompt
from .provider import ProviderUsage
from .schema import ExtractedLine, ExtractionResult, RepairResult, RepairTarget

# The Gemini 3 Pro line as served on 2026-08-29 (the original gemini-3-pro-preview
# has left Google's pricing page). Confirm against `client.models.list()` with the
# live key before a bake-off run; eval/live.py takes GEMINI_MODEL_ID to override
# without an edit here.
MODEL_ID = "gemini-3.1-pro-preview"

T = TypeVar("T", bound=BaseModel)


class _RepairLinePatch(BaseModel):
    """Wire shape for one repaired line, same precedent as the Anthropic
    provider: RepairResult's int-keyed dict maps to an open
    additional_properties object in Gemini's schema flavor, which its
    constrained decoding does not honor - so the model returns a list and
    repair() re-keys it."""

    model_config = ConfigDict(extra="forbid")

    line_index: int
    line: ExtractedLine


class _RepairOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[_RepairLinePatch] = Field(default_factory=list)
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None


class GeminiExtractionProvider:
    """ExtractionProvider on Gemini 3 Pro with structured JSON output
    (response_schema); dynamic thinking left at the model default, the same
    posture as the Anthropic provider's adaptive thinking.

    max_output_tokens stays unset: Gemini counts thinking tokens inside that
    budget, so a cap sized for the JSON alone can truncate a long invoice
    mid-read. The finish_reason guard below turns any truncation into a raise.
    """

    def __init__(self, client: genai.Client | None = None, model_id: str = MODEL_ID) -> None:
        # Injected in tests; the default resolves GEMINI_API_KEY from the env.
        self._client = client if client is not None else genai.Client()
        self._model_id = model_id

    async def extract(self, image: bytes, mime: str) -> tuple[ExtractionResult, ProviderUsage]:
        return await self._call(image, mime, EXTRACT_PROMPT, ExtractionResult)

    async def repair(
        self, image: bytes, mime: str, targets: list[RepairTarget]
    ) -> tuple[RepairResult, ProviderUsage]:
        patch, usage = await self._call(image, mime, build_repair_prompt(targets), _RepairOutput)
        result = RepairResult(
            lines={entry.line_index: entry.line for entry in patch.lines},
            subtotal=patch.subtotal,
            tax=patch.tax,
            total=patch.total,
        )
        return result, usage

    async def _call(
        self, image: bytes, mime: str, prompt: str, output_format: type[T]
    ) -> tuple[T, ProviderUsage]:
        # Gemini's inline limit (~20 MB request) is looser than Anthropic's,
        # but the bake-off must show both models the same pixels - the Opus
        # baseline saw PH-01 resized under the 10 MB base64 ceiling, so the
        # same fit runs here. PDFs pass through inline with their own mime;
        # Gemini reads them without a separate block type.
        image, mime = fit_for_vision(image, mime)

        started = time.monotonic()
        response = await self._client.aio.models.generate_content(
            model=self._model_id,
            contents=[types.Part.from_bytes(data=image, mime_type=mime), prompt],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=output_format,
            ),
        )
        latency_ms = int((time.monotonic() - started) * 1000)

        # WP-19's rule at the provider boundary: a short read raises, never
        # returns a partial invoice. MAX_TOKENS is a truncated JSON body that
        # may still parse as a shorter line list; SAFETY and friends carry no
        # complete answer either. Only a clean STOP is an answer.
        candidate = response.candidates[0] if response.candidates else None
        finish = candidate.finish_reason if candidate is not None else None
        if finish is not types.FinishReason.STOP:
            raise ValueError(f"no complete structured output (finish_reason={finish!r})")
        text = response.text
        if not text:
            raise ValueError("structured output finished STOP but returned no text")
        parsed = output_format.model_validate_json(text)

        # Thinking tokens are billed at the output rate (ai.google.dev pricing,
        # 2026-08-29), so they count as output here - otherwise the eval's cost
        # per invoice under-reports the real spend.
        meta = response.usage_metadata
        input_tokens = output_tokens = 0
        if meta is not None:
            input_tokens = meta.prompt_token_count or 0
            output_tokens = (meta.response_token_count or 0) + (meta.thoughts_token_count or 0)
        usage = ProviderUsage(
            model_id=response.model_version or self._model_id,
            prompt_version=PROMPT_VERSION,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
        return parsed, usage
