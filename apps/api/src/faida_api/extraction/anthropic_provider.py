"""WP-10: the Claude Opus 5 implementation of the C3 provider seam (plan.md §5
layer 1, §7.3).

One structured vision call classifies and extracts together; repair re-reads
only the targeted cells. The Anthropic SDK is imported nowhere outside this
package (C3) - everything downstream sees ExtractionProvider alone.
"""

import base64
import time
from decimal import Decimal
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ConfigDict, Field

from .images import fit_for_vision
from .prompts import EXTRACT_PROMPT, PROMPT_VERSION, SYSTEM_PROMPT, build_repair_prompt
from .provider import ProviderUsage
from .schema import ExtractedLine, ExtractionResult, RepairResult, RepairTarget

MODEL_ID = "claude-opus-5"
MAX_TOKENS = 16000

T = TypeVar("T", bound=BaseModel)


class _RepairLinePatch(BaseModel):
    """Wire shape for one repaired line. RepairResult's int-keyed dict cannot
    cross the structured-outputs boundary (the SDK's strict-schema transform
    closes open dicts), so the model returns a list and repair() re-keys it."""

    model_config = ConfigDict(extra="forbid")

    line_index: int
    line: ExtractedLine


class _RepairOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[_RepairLinePatch] = Field(default_factory=list)
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None


class AnthropicExtractionProvider:
    """ExtractionProvider on claude-opus-5 with structured outputs
    (client.messages.parse); adaptive thinking left on (plan.md §3)."""

    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        # Injected in tests; the default resolves ANTHROPIC_API_KEY from the env.
        self._client = client if client is not None else anthropic.AsyncAnthropic()

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
        # The ingest path accepts "document" media too (C2); PDFs go in a document block.
        # A phone photo can exceed the API's 10 MB base64 ceiling outright;
        # resize only when it would otherwise be rejected (see images.py).
        image, mime = fit_for_vision(image, mime)
        block_type = "document" if mime == "application/pdf" else "image"
        media_block = {
            "type": block_type,
            "source": {
                "type": "base64",
                "media_type": mime,
                "data": base64.standard_b64encode(image).decode("ascii"),
            },
        }

        started = time.monotonic()
        response = await self._client.messages.parse(
            model=MODEL_ID,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_format=output_format,
            messages=[{"role": "user", "content": [media_block, {"type": "text", "text": prompt}]}],
        )
        latency_ms = int((time.monotonic() - started) * 1000)

        parsed = response.parsed_output
        if parsed is None:
            # e.g. a refusal: no text block to parse. The pipeline's failure
            # path (plan.md §5 layer 6) owns what happens next.
            raise ValueError(f"no structured output (stop_reason={response.stop_reason!r})")
        usage = ProviderUsage(
            model_id=response.model,
            prompt_version=PROMPT_VERSION,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
        )
        return parsed, usage
