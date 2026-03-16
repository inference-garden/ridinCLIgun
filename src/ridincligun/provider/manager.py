"""Provider manager — orchestrates AI review requests.

Handles timeouts, error recovery, and graceful degradation.
The app talks to the manager; the manager talks to adapters.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ridincligun.provider.base import AIReviewResponse, ProviderAdapter, ProviderError

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
    def is_configured(self) -> bool:
        return self._adapter.is_configured

    async def review(self, command: str, context: str = "") -> ReviewStatus:
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
                self._adapter.review_command(command, context),
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
            return ReviewStatus(
                success=False,
                error_message=str(e),
                provider_name=self._adapter.name,
            )
        except Exception as e:
            return ReviewStatus(
                success=False,
                error_message=f"Unexpected error: {e}",
                provider_name=self._adapter.name,
            )
