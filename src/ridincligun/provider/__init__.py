# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Provider factory

"""Provider package — AI adapter factory and shared types."""

from __future__ import annotations

from ridincligun.advisory.router import DEEP, FAST
from ridincligun.config import Config
from ridincligun.provider.base import ProviderAdapter
from ridincligun.provider.manager import ProviderManager
from ridincligun.provider.registry import get_models, normalize_kind


def _build_adapter(kind: str, api_key: str, model: str) -> ProviderAdapter:
    """Build a single provider adapter for *kind* pinned to *model*.

    SDK imports stay lazy (per kind) so an optional provider's SDK is only imported
    when that provider is actually selected.
    """
    if kind == "openai":
        from ridincligun.provider.openai import OpenAIAdapter

        return OpenAIAdapter(api_key=api_key, model=model)
    if kind == "mistral":
        from ridincligun.provider.mistral import MistralAdapter

        return MistralAdapter(api_key=api_key, model=model)
    from ridincligun.provider.anthropic import AnthropicAdapter

    return AnthropicAdapter(api_key=api_key, model=model)


def create_provider(config: Config) -> ProviderManager:
    """Create a tier-aware ProviderManager for the configured provider.

    Builds a Fast and a Deep adapter from the provider→model registry; the router
    chooses which tier answers each review. Supports 'anthropic' (default), 'openai',
    'mistral'; an unrecognized kind falls back to Anthropic (provider default, not a
    model substitution — the active model is still always shown).
    """
    import os

    kind = normalize_kind(config.provider.kind)
    models = get_models(kind)

    # Resolve the appropriate API key for the provider
    _KEY_ENV = {  # noqa: N806
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "mistral": "MISTRAL_API_KEY",
    }
    key_name = _KEY_ENV.get(kind, "ANTHROPIC_API_KEY")
    api_key = config.api_key or os.environ.get(key_name, "")

    adapters = {
        FAST: _build_adapter(kind, api_key, models.fast),
        DEEP: _build_adapter(kind, api_key, models.deep),
    }

    return ProviderManager(
        adapters,
        timeout=config.provider.timeout_seconds,
        provider_kind=kind,
        provider_display=models.display,
    )
