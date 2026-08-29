"""WP-10: the Anthropic provider maps SDK responses to the pinned C3 models.

The SDK client is faked at the messages.parse seam - no network, no API key.
The fake validates canned JSON through the output_format the provider passes,
mirroring what the real SDK does with the model's text."""

import base64
from decimal import Decimal
from types import SimpleNamespace

import pytest

from faida_api.extraction.anthropic_provider import MODEL_ID, AnthropicExtractionProvider
from faida_api.extraction.prompts import PROMPT_VERSION
from faida_api.extraction.provider import ExtractionProvider, ProviderUsage
from faida_api.extraction.schema import (
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
    "invoice_date": "2026-08-20",
    "currency": "AED",
    "payment_kind": "credit",
    "lines": [
      {"raw_name": "MILK PWDR 2.5KG NIDO", "qty": 12, "unit": "sack",
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
     "line": {"raw_name": "KARAK TEA DUST", "qty": 12, "unit": null, "pack_size": null,
              "unit_price": "4.50", "line_total": "54.00"}}
  ],
  "subtotal": null,
  "tax": null,
  "total": "745.76"
}
"""


class FakeMessages:
    def __init__(self, output_json: str, stop_reason: str = "end_turn"):
        self._output_json = output_json
        self._stop_reason = stop_reason
        self.calls: list[dict] = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        parsed = kwargs["output_format"].model_validate_json(self._output_json)
        return SimpleNamespace(
            parsed_output=parsed,
            model=MODEL_ID,
            stop_reason=self._stop_reason,
            usage=SimpleNamespace(input_tokens=2411, output_tokens=387),
        )


class FakeClient:
    def __init__(self, output_json: str, stop_reason: str = "end_turn"):
        self.messages = FakeMessages(output_json, stop_reason)


def make_provider(
    output_json: str, stop_reason: str = "end_turn"
) -> tuple[ExtractionProvider, FakeMessages]:
    client = FakeClient(output_json, stop_reason)
    return AnthropicExtractionProvider(client=client), client.messages


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
    assert usage.output_tokens == 387
    assert usage.latency_ms >= 0

    call = fake.calls[0]
    assert call["model"] == MODEL_ID
    assert call["output_format"] is ExtractionResult
    media_block = call["messages"][0]["content"][0]
    assert media_block["type"] == "image"
    assert media_block["source"]["media_type"] == "image/jpeg"
    assert base64.standard_b64decode(media_block["source"]["data"]) == image


async def test_other_classification_returns_no_invoice():
    provider, _ = make_provider('{"classification": "other"}')

    result, _usage = await provider.extract(b"a meme", "image/png")

    assert result.classification is Classification.OTHER
    assert result.invoice is None


async def test_pdf_media_goes_in_a_document_block():
    provider, fake = make_provider('{"classification": "other"}')
    pdf = b"%PDF-1.4 fake"

    await provider.extract(pdf, "application/pdf")

    media_block = fake.calls[0]["messages"][0]["content"][0]
    assert media_block["type"] == "document"
    assert media_block["source"]["media_type"] == "application/pdf"
    assert base64.standard_b64decode(media_block["source"]["data"]) == pdf


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

    prompt = fake.calls[0]["messages"][0]["content"][1]["text"]
    assert "Line 3" in prompt
    assert "qty, unit_price, line_total" in prompt
    assert "qty 12 x 4.50 != extracted 58.00" in prompt
    # The document-level target names the totals block, not a line.
    assert "subtotal 710.25 + tax 35.51 != extracted 745.00" in prompt
    assert "Totals block" in prompt


# --- WP-19: a truncated read is a failure, never a shorter answer -----------


async def test_truncated_output_raises_even_when_the_json_parses():
    # The old platform's dominant real failure: a perfect header with 2 of 34
    # lines, persisted because the cut-off output still parsed and the header
    # still reconciled. stop_reason is the ground truth for truncation, so it
    # fails the call regardless of how plausible the partial answer looks.
    provider, _ = make_provider(INVOICE_JSON, stop_reason="max_tokens")
    with pytest.raises(ValueError, match="truncated at the 16000-token ceiling"):
        await provider.extract(b"\xff\xd8fake-jpeg", "image/jpeg")


async def test_truncated_repair_raises_too():
    provider, _ = make_provider(REPAIR_JSON, stop_reason="max_tokens")
    with pytest.raises(ValueError, match="truncated"):
        await provider.repair(
            b"img", "image/jpeg", [RepairTarget(line_index=3, fields=["qty"], reason="check")]
        )
