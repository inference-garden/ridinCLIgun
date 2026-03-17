"""Provider package — AI adapter factory and shared types."""

from __future__ import annotations

from ridincligun.config import Config
from ridincligun.provider.base import ProviderAdapter
from ridincligun.provider.manager import ProviderManager


def create_provider(config: Config) -> ProviderManager:
    """Create the appropriate ProviderManager based on config.

    Supports: 'anthropic' (default), 'openai'.
    Falls back to Anthropic if the provider kind is unrecognized.
    """
    adapter: ProviderAdapter

    kind = config.provider.kind.lower()

    if kind == "openai":
        from ridincligun.provider.openai import OpenAIAdapter

        # Resolve OpenAI key from .env or env var
        import os

        api_key = config.api_key or os.environ.get("OPENAI_API_KEY", "")
        adapter = OpenAIAdapter(api_key=api_key, model=config.provider.model)
    else:
        # Default: Anthropic
        from ridincligun.provider.anthropic import AnthropicAdapter

        adapter = AnthropicAdapter(
            api_key=config.api_key,
            model=config.provider.model,
        )

    return ProviderManager(adapter, timeout=config.provider.timeout_seconds)
