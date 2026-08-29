"""The Gemini provider maps SDK responses to the pinned C3 models (bake-off
lane, 2026-08-29).

The SDK client is faked at the aio.models.generate_content seam - no network,
no API key. The fake validates canned JSON through the response_schema the
provider passes, mirroring what the real SDK's constrained decoding returns
as text. google-genai is an optional extra, so the whole module skips when it
is not installed (CI installs [dev] alone; the bake-off venv adds [gemini])."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

pytest.importorskip("google.genai", reason="gemini extra not installed (pip install -e .[gemini])")

from google.genai import types  # noqa: E402

from faida_api.extraction.gemini_provider import (  # noqa: E402
    MODEL_ID,
    GeminiExtractionProvider,
)
from faida_api.extraction.prompts import PROMPT_VERSION, SYSTEM_PROMPT  # noqa: E402
from faida_api.extraction.provider import ExtractionProvider, ProviderUsage  # noqa: E402
from faida_api.extraction.schema import (  # noqa: E402
    Classification,
    ExtractionResult,
    RepairResult,
    RepairTarget,
)

INVOICE_JSON = """\
{
  "classification": "invoice",
  "invoice": {
    "supplier_name": "Gulf Foods Trading LLC",
    "invoice_no": "INV-1041",
    "invoice_date_text": "20/08/2026",
    "currency": "AED",
    "payment_kind": "credit",
    "lines": [
      {"raw_name": "MILK PWDR 2.5KG NIDO", "qty": "12", "unit": "sack",
       "pack_size": "2.5kg", "unit_price": "54.50", "line_total": "654.00"}
    ],
    "subtotal": "654.00",
    "tax": "32.70",
    "total": "686.70"
  }
}
"""

REPAIR_JSON = """\
{
  "lines": [
    {"line_index": 3,
     "line": {"raw_name": "KARAK TEA DUST", "qty": "12", "unit": null, "pack_size": null,
              "unit_price": "4.50", "line_total": "54.00"}}
  ],
  "subtotal": null,
  "tax": null,
  "total": "745.76"
}
"""


class FakeAioModels:
    def __init__(
        self,
        output_json: str | None,
        finish_reason: types.FinishReason | None = types.FinishReason.STOP,
    ):
        self._output_json = output_json
        self._finish_reason = finish_reason
        self.calls: list[dict] = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        candidates = (
            [types.Candidate(finish_reason=self._finish_reason)]
            if self._finish_reason is not None
            else []
        )
        # The envelope is a namespace (the real response derives .text from
        # nested parts), but usage and candidates are the SDK's own types: the
        # first live run failed on a usage field name the fake had invented
        # (response_token_count for candidates_token_count), which is exactly
        # the drift a fake at a real seam must not allow.
        return SimpleNamespace(
            candidates=candidates,
            text=self._output_json,
            model_version=MODEL_ID,
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=2411,
                candidates_token_count=387,
                thoughts_token_count=121,
            ),
        )


class FakeClient:
    def __init__(self, fake: FakeAioModels):
        self.aio = SimpleNamespace(models=fake)


def make_provider(
    output_json: str | None,
    finish_reason: types.FinishReason | None = types.FinishReason.STOP,
) -> tuple[ExtractionProvider, FakeAioModels]:
    fake = FakeAioModels(output_json, finish_reason)
    return GeminiExtractionProvider(client=FakeClient(fake)), fake


async def test_extract_maps_response_to_result_and_usage():
    provider, fake = make_provider(INVOICE_JSON)
    image = b"\xff\xd8fake-jpeg"

    result, usage = await provider.extract(image, "image/jpeg")

    assert isinstance(result, ExtractionResult)
    assert result.classification is Classification.INVOICE
    line = result.invoice.lines[0]
    assert line.qty == Decimal("12")
    assert line.unit_price == Decimal("54.50")
    assert isinstance(line.unit_price, Decimal)
    assert result.invoice.total == Decimal("686.70")

    assert isinstance(usage, ProviderUsage)
    assert usage.model_id == MODEL_ID
    assert usage.prompt_version == PROMPT_VERSION
    assert usage.input_tokens == 2411
    # Thinking tokens bill at the output rate, so they count as output.
    assert usage.output_tokens == 387 + 121
    assert usage.latency_ms >= 0

    call = fake.calls[0]
    assert call["model"] == MODEL_ID
    config = call["config"]
    assert config.system_instruction == SYSTEM_PROMPT
    assert config.response_mime_type == "application/json"
    # Raw JSON Schema on the wire; the proto response_schema flavor rejects
    # C3's additionalProperties (see the provider docstring) and stays unset.
    assert config.response_json_schema == ExtractionResult.model_json_schema()
    assert config.response_schema is None
    media = call["contents"][0]
    assert media.inline_data.mime_type == "image/jpeg"
    assert media.inline_data.data == image


async def test_other_classification_returns_no_invoice():
    provider, _ = make_provider('{"classification": "other"}')

    result, _usage = await provider.extract(b"a meme", "image/png")

    assert result.classification is Classification.OTHER
    assert result.invoice is None


async def test_pdf_goes_inline_with_its_own_mime():
    """Gemini reads PDFs inline - no separate document block type exists or
    is needed (the Anthropic wire's image/document split is provider-local)."""
    provider, fake = make_provider('{"classification": "other"}')
    pdf = b"%PDF-1.4 fake"

    await provider.extract(pdf, "application/pdf")

    media = fake.calls[0]["contents"][0]
    assert media.inline_data.mime_type == "application/pdf"
    assert media.inline_data.data == pdf


async def test_repair_targets_only_the_named_cells_and_parses_the_patch():
    provider, fake = make_provider(REPAIR_JSON)
    targets = [
        RepairTarget(
            line_index=3,
            fields=["qty", "unit_price", "line_total"],
            reason="qty 12 x 4.50 != extracted 58.00",
        ),
        RepairTarget(
            line_index=None,
            fields=["total"],
            reason="subtotal 710.25 + tax 35.51 != extracted 745.00",
        ),
    ]

    result, usage = await provider.repair(b"img", "image/jpeg", targets)

    assert isinstance(result, RepairResult)
    assert set(result.lines) == {3}
    assert result.lines[3].raw_name == "KARAK TEA DUST"
    assert result.lines[3].line_total == Decimal("54.00")
    assert result.total == Decimal("745.76")
    assert result.subtotal is None
    assert usage.prompt_version == PROMPT_VERSION

    prompt = fake.calls[0]["contents"][1]
    assert "Line 3" in prompt
    assert "qty, unit_price, line_total" in prompt
    assert "qty 12 x 4.50 != extracted 58.00" in prompt
    # The document-level target names the totals block, not a line.
    assert "subtotal 710.25 + tax 35.51 != extracted 745.00" in prompt
    assert "Totals block" in prompt


async def test_truncated_response_raises_instead_of_returning_a_partial_invoice():
    """WP-19's rule at the provider boundary: MAX_TOKENS means the JSON body
    stopped mid-read, and a truncated line list can still parse as a shorter,
    valid invoice - so the finish reason decides, not parseability."""
    truncated = INVOICE_JSON[: len(INVOICE_JSON) // 2]
    provider, _ = make_provider(truncated, finish_reason=types.FinishReason.MAX_TOKENS)

    with pytest.raises(ValueError, match="finish_reason"):
        await provider.extract(b"img", "image/jpeg")


async def test_no_candidates_raises():
    """A blocked or empty response carries no candidate at all; that is a
    failure-path raise (plan.md §5 layer 6), never a silent empty invoice."""
    provider, _ = make_provider(None, finish_reason=None)

    with pytest.raises(ValueError, match="finish_reason"):
        await provider.extract(b"img", "image/jpeg")


async def test_stop_with_no_text_raises():
    provider, _ = make_provider(None, finish_reason=types.FinishReason.STOP)

    with pytest.raises(ValueError, match="no text"):
        await provider.extract(b"img", "image/jpeg")
