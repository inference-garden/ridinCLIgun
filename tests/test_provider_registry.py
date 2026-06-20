# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for the provider→model registry and the tier-aware manager

"""Provider-only selection: the registry maps a provider to its Fast/Deep models, and
the tier-aware manager always exposes which model answers (no-silent-fallbacks)."""

import asyncio

from ridincligun.config import Config, ProviderSettings
from ridincligun.provider import create_provider
from ridincligun.provider.base import AIReviewResponse, ProviderAdapter
from ridincligun.provider.manager import ProviderManager
from ridincligun.provider.registry import (
    DEFAULT_PROVIDER,
    PROVIDER_MODELS,
    get_models,
    normalize_kind,
    provider_kinds,
)

# ── Registry ────────────────────────────────────────────────────────


def test_registry_has_three_providers():
    assert provider_kinds() == ["anthropic", "openai", "mistral"]


def test_registry_model_ids_are_authoritative():
    # 70_Evaluations/llm_model_evaluation.md §4.
    assert get_models("anthropic").fast == "claude-haiku-4-5"
    assert get_models("anthropic").deep == "claude-sonnet-4-6"
    assert get_models("openai").fast == "gpt-5.4-mini"
    assert get_models("openai").deep == "gpt-5.4"
    assert get_models("mistral").fast == "mistral-small-2603"
    assert get_models("mistral").deep == "mistral-medium-3-5"


def test_registry_displays():
    assert {m.display for m in PROVIDER_MODELS.values()} == {
        "Anthropic",
        "OpenAI",
        "Mistral",
    }


def test_normalize_kind_is_case_insensitive_and_defaults():
    assert normalize_kind("ANTHROPIC") == "anthropic"
    assert normalize_kind("OpenAI") == "openai"
    assert normalize_kind("bogus-provider") == DEFAULT_PROVIDER


# ── create_provider builds tier-aware managers ─────────────────────


def test_create_provider_builds_fast_and_deep_adapters():
    config = Config(provider=ProviderSettings(kind="anthropic"), api_key="sk-ant-test")
    manager = create_provider(config)
    assert manager.provider_kind == "anthropic"
    assert manager.provider_name == "Anthropic"
    assert manager.model_id("fast") == "claude-haiku-4-5"
    assert manager.model_id("deep") == "claude-sonnet-4-6"
    # Default tier is Fast (the floor).
    assert manager.model_id() == "claude-haiku-4-5"


def test_create_provider_unknown_kind_falls_back_to_anthropic():
    config = Config(provider=ProviderSettings(kind="bogus"), api_key="sk-test")
    manager = create_provider(config)
    assert manager.provider_kind == "anthropic"
    assert manager.model_id("deep") == "claude-sonnet-4-6"


# ── Tier-aware manager dispatch ────────────────────────────────────


class _FakeAdapter(ProviderAdapter):
    def __init__(self, model: str) -> None:
        self._model = model

    @property
    def name(self) -> str:
        return f"Fake {self._model}"

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def is_configured(self) -> bool:
        return True

    async def review_command(
        self, command: str, context: str = "", system_prompt: str = ""
    ) -> AIReviewResponse:
        return AIReviewResponse(
            risk_assessment="safe",
            summary=f"reviewed by {self._model}",
            explanation="",
            suggestion="",
            raw_text="",
        )


def test_manager_dispatches_review_to_requested_tier():
    manager = ProviderManager(
        {"fast": _FakeAdapter("fast-model"), "deep": _FakeAdapter("deep-model")},
        provider_kind="fake",
        provider_display="Fake",
    )
    fast = asyncio.run(manager.review("ls", tier="fast"))
    deep = asyncio.run(manager.review("ls", tier="deep"))
    assert fast.response.summary == "reviewed by fast-model"
    assert deep.response.summary == "reviewed by deep-model"
    # Default tier is Fast.
    default = asyncio.run(manager.review("ls"))
    assert default.response.summary == "reviewed by fast-model"


def test_manager_legacy_single_adapter_still_works():
    # Back-compat: a single adapter is used for both tiers; provider_name falls back
    # to the adapter's own name when no display is given.
    manager = ProviderManager(_FakeAdapter("solo-model"))
    assert manager.model_id("fast") == "solo-model"
    assert manager.model_id("deep") == "solo-model"
    assert "solo-model" in manager.provider_name
