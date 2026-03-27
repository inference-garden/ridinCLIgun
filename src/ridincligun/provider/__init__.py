# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Provider factory

"""Provider package — AI adapter factory and shared types."""

from __future__ import annotations

from ridincligun.config import Config
from ridincligun.provider.base import ProviderAdapter
from ridincligun.provider.manager import ProviderManager


def create_provider(config: Config) -> ProviderManager:
    """Create the appropriate ProviderManager based on config.

    Supports: 'anthropic' (default), 'openai', 'mistral'.
    Falls back to Anthropic if the provider kind is unrecognized.
    """
    import os

    adapter: ProviderAdapter
    kind = config.provider.kind.lower()

    # Resolve the appropriate API key for the provider
    _KEY_ENV = {  # noqa: N806
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "mistral": "MISTRAL_API_KEY",
    }
    key_name = _KEY_ENV.get(kind, "ANTHROPIC_API_KEY")
    api_key = config.api_key or os.environ.get(key_name, "")

    if kind == "openai":
        from ridincligun.provider.openai import OpenAIAdapter

        adapter = OpenAIAdapter(api_key=api_key, model=config.provider.model)
    elif kind == "mistral":
        from ridincligun.provider.mistral import MistralAdapter

        adapter = MistralAdapter(api_key=api_key, model=config.provider.model)
    else:
        # Default: Anthropic
        from ridincligun.provider.anthropic import AnthropicAdapter

        adapter = AnthropicAdapter(api_key=api_key, model=config.provider.model)

    return ProviderManager(adapter, timeout=config.provider.timeout_seconds)
