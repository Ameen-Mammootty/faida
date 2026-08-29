"""The --provider flag and the --record guard (bake-off lane, 2026-08-29).

The recorded fixtures are the CI baseline for the SHIPPED provider; the guard
pinned here is what stops one careless flag from overwriting them with
another model's answers."""

import pytest

from eval.live import LiveProviderUnavailable, build_live_provider, live_model_id
from eval.run import main


def test_record_is_refused_for_a_non_shipped_provider(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--live", "--provider", "anthropic", "--record"])
    assert excinfo.value.code == 2
    assert "reserved for the shipped provider" in capsys.readouterr().err


def test_record_with_the_shipped_provider_passes_the_guard(capsys, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    # Past the flag guard, the run stops at the default corpus (eval/corpus
    # does not exist here) - the guard is what this test pins, not the run.
    assert main(["--live", "--record"]) == 1
    assert "no cases found" in capsys.readouterr().err


def test_gemini_without_a_key_fails_before_any_case_runs():
    with pytest.raises(LiveProviderUnavailable, match="GEMINI_API_KEY"):
        build_live_provider(None, "gemini")


def test_unknown_provider_is_refused():
    with pytest.raises(LiveProviderUnavailable, match="unknown provider"):
        build_live_provider("some-key", "openai")


def test_gemini_model_id_env_override(monkeypatch):
    from faida_api.extraction.gemini_provider import MODEL_ID

    monkeypatch.setenv("GEMINI_MODEL_ID", "gemini-3.1-pro-preview-custom")
    assert live_model_id("gemini") == "gemini-3.1-pro-preview-custom"
    monkeypatch.delenv("GEMINI_MODEL_ID")
    assert live_model_id("gemini") == MODEL_ID
