"""C3: the provider seam (plan.md §7.2, PRD §25.1).

The vision call sits behind this interface so the model swaps in one place.
WP-10 supplies the Anthropic implementation; tests and the eval harness supply
recorded/fake ones.
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from .schema import ExtractionResult, RepairResult, RepairTarget


class ProviderUsage(BaseModel):
    """Recorded on every run (plan.md §5 layer 1); cost derives from tokens."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class ExtractionProvider(Protocol):
    async def extract(self, image: bytes, mime: str) -> tuple[ExtractionResult, ProviderUsage]: ...

    async def repair(
        self, image: bytes, mime: str, targets: list[RepairTarget]
    ) -> tuple[RepairResult, ProviderUsage]: ...
