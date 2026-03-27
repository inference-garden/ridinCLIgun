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

from ridincligun.provider.base import AIReviewResponse, ProviderAdapter, ProviderError

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
    """Manages AI provider lifecycle, timeouts, and error handling."""

    def __init__(
        self,
        adapter: ProviderAdapter,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._adapter = adapter
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        return self._adapter.name

    @property
    def model_id(self) -> str:
        return self._adapter.model_id

    @property
    def is_configured(self) -> bool:
        return self._adapter.is_configured

    async def review(
        self, command: str, context: str = "", system_prompt: str = "",
    ) -> ReviewStatus:
        """Request an AI review with timeout and error handling.

        Always returns a ReviewStatus — never raises.
        """
        if not self._adapter.is_configured:
            return ReviewStatus(
                success=False,
                error_message="API key not configured. Add it to ~/.config/ridincligun/.env",
                provider_name=self._adapter.name,
            )

        try:
            response = await asyncio.wait_for(
                self._adapter.review_command(command, context, system_prompt),
                timeout=self._timeout,
            )
            return ReviewStatus(
                success=True,
                response=response,
                provider_name=self._adapter.name,
            )
        except TimeoutError:
            return ReviewStatus(
                success=False,
                error_message=f"Review timed out after {self._timeout:.0f}s.",
                provider_name=self._adapter.name,
            )
        except ProviderError as e:
            # Log full error for debugging; show only safe message to user
            _log.warning("Provider error during review: %s", e)
            return ReviewStatus(
                success=False,
                error_message="AI review failed — check connection and try again.",
                provider_name=self._adapter.name,
            )
        except Exception as e:
            # Log full exception for debugging; never expose raw details to UI
            _log.warning("Unexpected error during review: %s", e)
            return ReviewStatus(
                success=False,
                error_message="AI review failed — check connection and try again.",
                provider_name=self._adapter.name,
            )
