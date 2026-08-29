"""build_provider selects the shipped default and the fallback explicitly
(2026-08-29 Decision Log): gemini = Gemini 3 Flash, anthropic = Opus 5, a
missing key for the selected provider yields None (extract jobs then fail
into the §5 layer 6 path), and an unknown name raises at boot instead of
silently disabling extraction."""

import pytest

from faida_api.extraction.anthropic_provider import AnthropicExtractionProvider
from faida_api.extraction.gemini_provider import GeminiExtractionProvider
from faida_api.extraction.pipeline import build_provider


def test_gemini_key_builds_the_shipped_provider():
    provider = build_provider("gemini", gemini_api_key="test-key")
    assert isinstance(provider, GeminiExtractionProvider)


def test_anthropic_key_builds_the_fallback_provider():
    provider = build_provider("anthropic", anthropic_api_key="test-key")
    assert isinstance(provider, AnthropicExtractionProvider)


def test_missing_key_for_the_selected_provider_yields_none():
    assert build_provider("gemini", anthropic_api_key="unused") is None
    assert build_provider("anthropic", gemini_api_key="unused") is None


def test_unknown_provider_raises_at_boot():
    with pytest.raises(ValueError, match="unknown extraction provider"):
        build_provider("openai", gemini_api_key="key")
