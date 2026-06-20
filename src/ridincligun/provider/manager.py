# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Timeout and error handling

"""Provider manager — orchestrates AI review requests.

Handles timeouts, error recovery, and graceful degradation.
The app talks to the manager; the manager talks to adapters.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass

from ridincligun.advisory.router import DEEP, FAST
from ridincligun.provider.base import (
    AIReviewResponse,
    ProviderAdapter,
    ProviderError,
    ProviderRateLimitError,
    ProviderSetupError,
)

# Debug logger — writes to stderr, never to advisory pane or history
_log = logging.getLogger(__name__)
if not _log.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    _log.addHandler(_handler)
    _log.setLevel(logging.WARNING)

# Default timeout for AI review calls (seconds)
_DEFAULT_TIMEOUT = 15.0


@dataclass
class ReviewStatus:
    """Status wrapper for an AI review attempt."""

    success: bool
    response: AIReviewResponse | None = None
    error_message: str = ""
    provider_name: str = ""


class ProviderManager:
    """Manages AI provider lifecycle, timeouts, and error handling.

    Holds one adapter per **tier** (``"fast"`` / ``"deep"``) of the chosen provider and
    runs each review on the tier the router selects. The active model is always a plain
    property lookup (``model_id(tier)``) so it can be shown on every review — the
    no-silent-fallback rule is non-negotiable.

    Backward-compatible construction: pass either a ``{tier: adapter}`` mapping or a
    single :class:`ProviderAdapter` (used for both tiers — the legacy single-model form).
    """

    def __init__(
        self,
        adapter: ProviderAdapter | dict[str, ProviderAdapter],
        timeout: float = _DEFAULT_TIMEOUT,
        *,
        provider_kind: str | None = None,
        provider_display: str | None = None,
    ) -> None:
        if isinstance(adapter, dict):
            self._adapters: dict[str, ProviderAdapter] = dict(adapter)
        else:
            # Legacy single-adapter form: the same model answers both tiers.
            self._adapters = {FAST: adapter, DEEP: adapter}
        self._timeout = timeout
        self._kind = provider_kind
        self._display = provider_display

    def _adapter_for(self, tier: str) -> ProviderAdapter:
        """Return the adapter for *tier*, falling back to Fast (the floor) if unknown."""
        return self._adapters.get(tier) or self._adapters[FAST]

    @property
    def provider_kind(self) -> str | None:
        return self._kind

    @property
    def provider_name(self) -> str:
        # Provider display (e.g. "Anthropic") when known; else the adapter's own name
        # (legacy single-adapter form), which still carries the provider substring.
        return self._display or self._adapters[FAST].name

    def model_id(self, tier: str = FAST) -> str:
        """Return the model id for *tier* (always visible — never silently swapped)."""
        return self._adapter_for(tier).model_id

    @property
    def is_configured(self) -> bool:
        return self._adapters[FAST].is_configured

    async def review(
        self,
        command: str,
        context: str = "",
        system_prompt: str = "",
        tier: str = FAST,
    ) -> ReviewStatus:
        """Request an AI review on *tier* with timeout and error handling.

        Always returns a ReviewStatus — never raises.
        """
        adapter = self._adapter_for(tier)
        if not adapter.is_configured:
            return ReviewStatus(
                success=False,
                error_message="API key not configured. Add it to ~/.config/ridincligun/.env",
                provider_name=adapter.name,
            )

        try:
            response = await asyncio.wait_for(
                adapter.review_command(command, context, system_prompt),
                timeout=self._timeout,
            )
            return ReviewStatus(
                success=True,
                response=response,
                provider_name=adapter.name,
            )
        except TimeoutError:
            return ReviewStatus(
                success=False,
                error_message=f"Review timed out after {self._timeout:.0f}s.",
                provider_name=adapter.name,
            )
        except ProviderRateLimitError as e:
            # Rate limit (429) is transient — tell the user to retry rather than
            # masking it as a connection problem. Clean static message: the raw
            # API body (logged below) is never shown.
            _log.warning("Provider rate-limited during review: %s", e)
            return ReviewStatus(
                success=False,
                error_message="Rate limited by the provider — wait a moment and try again.",
                provider_name=adapter.name,
            )
        except ProviderSetupError as e:
            # Local setup gap (SDK not installed, key not configured). The message
            # is a vetted, secret-free, actionable string — show it verbatim so the
            # user can actually fix it, instead of masking it as a connection error.
            _log.warning("Provider setup error during review: %s", e)
            return ReviewStatus(
                success=False,
                error_message=str(e),
                provider_name=adapter.name,
            )
        except ProviderError as e:
            # Log full error for debugging; show only safe message to user
            _log.warning("Provider error during review: %s", e)
            return ReviewStatus(
                success=False,
                error_message="AI review failed — check connection and try again.",
                provider_name=adapter.name,
            )
        except Exception as e:
            # Log full exception for debugging; never expose raw details to UI
            _log.warning("Unexpected error during review: %s", e)
            return ReviewStatus(
                success=False,
                error_message="AI review failed — check connection and try again.",
                provider_name=adapter.name,
            )
