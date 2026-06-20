# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Provider → (Fast, Deep) model registry

"""The provider model registry.

The user chooses a **provider they trust** — that is the only model choice. The app
maps each provider to a **Fast** and a **Deep** model and always shows which one is
talking (no silent substitution). This registry is that single mapping; the model ids
are authoritative per ``70_Evaluations/llm_model_evaluation.md §4``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Tier labels are produced by the router; re-exported here so provider code shares the
# router's vocabulary without re-deriving it.
from ridincligun.advisory.router import DEEP, FAST  # noqa: F401  (re-export)


@dataclass(frozen=True)
class ProviderModels:
    """The Fast + Deep model ids (and display name) for one provider."""

    display: str
    fast: str
    deep: str


# Authoritative IDs — 70_Evaluations/llm_model_evaluation.md §4.
PROVIDER_MODELS: dict[str, ProviderModels] = {
    "anthropic": ProviderModels(
        display="Anthropic", fast="claude-haiku-4-5", deep="claude-sonnet-4-6"
    ),
    "openai": ProviderModels(display="OpenAI", fast="gpt-5.4-mini", deep="gpt-5.4"),
    "mistral": ProviderModels(
        display="Mistral", fast="mistral-small-2603", deep="mistral-medium-3-5"
    ),
}

DEFAULT_PROVIDER = "anthropic"


def normalize_kind(kind: str) -> str:
    """Return a known provider kind, defaulting to :data:`DEFAULT_PROVIDER`.

    An unknown kind only arises from a hand-edited config — the selector offers only
    the three known providers. This mirrors the prior ``create_provider`` behaviour
    (unknown → Anthropic). It is a *provider* default, not a model substitution: the
    active model is still always shown, so the no-silent-fallback rule (which forbids
    swapping a model *within* the chosen provider) holds.
    """
    k = kind.lower()
    return k if k in PROVIDER_MODELS else DEFAULT_PROVIDER


def get_models(kind: str) -> ProviderModels:
    """Return the Fast/Deep models for *kind* (normalized to a known provider)."""
    return PROVIDER_MODELS[normalize_kind(kind)]


def provider_kinds() -> list[str]:
    """Return the known provider kinds in registry order (for the selector)."""
    return list(PROVIDER_MODELS.keys())
