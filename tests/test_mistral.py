"""Tests for the Mistral adapter (no real API calls)."""

import asyncio

from ridincligun.provider.manager import ProviderManager
from ridincligun.provider.mistral import MistralAdapter, _parse_response


def test_mistral_adapter_not_configured():
    """Mistral adapter without API key reports not configured."""
    adapter = MistralAdapter(api_key="")
    assert not adapter.is_configured


def test_mistral_adapter_configured():
    """Mistral adapter with API key reports configured."""
    adapter = MistralAdapter(api_key="test-key")
    assert adapter.is_configured


def test_mistral_adapter_name():
    """Mistral adapter name includes provider and model."""
    adapter = MistralAdapter(api_key="test-key", model="mistral-small-latest")
    assert "Mistral" in adapter.name
    assert "mistral-small-latest" in adapter.name


def test_mistral_adapter_default_model():
    """Mistral adapter uses mistral-small-latest by default."""
    adapter = MistralAdapter(api_key="test-key")
    assert "mistral-small-latest" in adapter.name


def test_mistral_parse_response_full():
    """Mistral parser handles well-formed response."""
    raw = (
        "RISK: warning\n"
        "SUMMARY: Deletes a directory.\n"
        "EXPLANATION: Removes the target recursively.\n"
        "SUGGESTION: Double-check the path first."
    )
    result = _parse_response(raw)
    assert result.risk_assessment == "warning"
    assert "Deletes" in result.summary
    assert "Double-check" in result.suggestion


def test_mistral_parse_response_malformed():
    """Mistral parser falls back to caution on malformed input."""
    result = _parse_response("garbage text")
    assert result.risk_assessment == "caution"


def test_mistral_manager_unconfigured():
    """Manager returns error for unconfigured Mistral provider."""
    adapter = MistralAdapter(api_key="")
    manager = ProviderManager(adapter)
    result = asyncio.run(manager.review("ls"))
    assert not result.success
    assert "key" in result.error_message.lower()


# ── Factory tests ───────────────────────────────────────────────

from ridincligun.config import Config, ProviderSettings  # noqa: E402
from ridincligun.provider import create_provider  # noqa: E402


def test_factory_creates_mistral():
    """Factory creates Mistral provider when configured."""
    config = Config(
        provider=ProviderSettings(kind="mistral", model="mistral-small-latest"),
        api_key="test-key",
    )
    manager = create_provider(config)
    assert "Mistral" in manager.provider_name
    assert manager.is_configured
