"""Abstract base for AI provider adapters.

Each provider (Anthropic, OpenAI, Mistral, ...) implements this interface.
The manager calls it; the adapter handles SDK specifics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class AIReviewResponse:
    """The structured result from an AI review."""

    risk_assessment: str   # e.g. "danger", "warning", "caution", "safe"
    summary: str           # What the command does
    explanation: str       # Why it's risky (or safe)
    suggestion: str        # What to do instead (empty if safe)
    raw_text: str          # Full unstructured response for fallback display
    input_tokens: int = 0  # Tokens used in the request
    output_tokens: int = 0  # Tokens used in the response


class ProviderAdapter(ABC):
    """Abstract adapter for an AI provider."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name, e.g. 'Anthropic Claude'."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Raw model identifier, e.g. 'claude-sonnet-4-20250514'."""

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether the provider has valid credentials."""

    @abstractmethod
    async def review_command(
        self,
        command: str,
        context: str = "",
        system_prompt: str = "",
    ) -> AIReviewResponse:
        """Send a command for AI review and return the structured response.

        Args:
            command: The shell command to review.
            context: Optional context (working directory, recent commands, etc.)
            system_prompt: Composed system prompt (base + category + mode).
                          If empty, the adapter falls back to the default.

        Raises:
            ProviderError: On any provider-specific failure.
        """


class ProviderError(Exception):
    """Raised when a provider call fails."""

    def __init__(self, message: str, retriable: bool = False) -> None:
        super().__init__(message)
        self.retriable = retriable
