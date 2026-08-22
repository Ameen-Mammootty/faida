"""Recorded provider: replays saved responses from disk (plan.md §5 CI policy).

The CI smoke runs against these recordings - no API key, no network, no spend,
no flakiness. Recordings are regenerated whenever the prompt version bumps
(WP-16).
"""

from pathlib import Path

from faida_api.extraction.provider import ProviderUsage
from faida_api.extraction.schema import ExtractionResult, RepairResult, RepairTarget


class RecordedProvider:
    """Satisfies the pinned ExtractionProvider protocol (C3) from a case dir
    holding recorded.json (an ExtractionResult dump) and usage.json (a
    ProviderUsage dump). The image bytes are ignored - the recording is the
    response."""

    def __init__(self, case_dir: Path | str) -> None:
        self._case_dir = Path(case_dir)

    async def extract(self, image: bytes, mime: str) -> tuple[ExtractionResult, ProviderUsage]:
        result = ExtractionResult.model_validate_json(
            (self._case_dir / "recorded.json").read_text()
        )
        usage = ProviderUsage.model_validate_json((self._case_dir / "usage.json").read_text())
        return result, usage

    async def repair(
        self, image: bytes, mime: str, targets: list[RepairTarget]
    ) -> tuple[RepairResult, ProviderUsage]:
        raise NotImplementedError("recorded repair replay arrives with WP-16 live-run recordings")
