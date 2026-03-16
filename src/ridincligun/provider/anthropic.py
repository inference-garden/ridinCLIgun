"""Anthropic Claude adapter for ridinCLIgun.

Uses the Anthropic Python SDK to send command review requests.
Parses the structured response format from prompt.py.
"""

from __future__ import annotations

import os
import re

from ridincligun.provider.base import AIReviewResponse, ProviderAdapter, ProviderError
from ridincligun.provider.prompt import SYSTEM_PROMPT, build_review_prompt

# Default model — fast, cheap, good enough for command review
_DEFAULT_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 512


class AnthropicAdapter(ProviderAdapter):
    """Adapter for Anthropic's Claude API."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model or _DEFAULT_MODEL
        self._client = None

    @property
    def name(self) -> str:
        return f"Anthropic {self._model}"

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        """Lazy-init the Anthropic client."""
        if self._client is None:
            try:
                import anthropic
            except ImportError as e:
                raise ProviderError(
                    "anthropic package not installed. Run: pip install anthropic",
                    retriable=False,
                ) from e
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    async def review_command(
        self,
        command: str,
        context: str = "",
    ) -> AIReviewResponse:
        """Send a command to Claude for review."""
        if not self.is_configured:
            raise ProviderError(
                "ANTHROPIC_API_KEY not set. Add it to ~/.config/ridincligun/.env",
                retriable=False,
            )

        user_message = build_review_prompt(command, context)

        try:
            client = self._get_client()
            # Use sync client in a thread to avoid blocking the event loop
            import asyncio

            response = await asyncio.to_thread(
                client.messages.create,
                model=self._model,
                max_tokens=_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as e:
            error_msg = str(e)
            # Detect common error types
            if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
                raise ProviderError(f"Authentication failed: {error_msg}", retriable=False) from e
            if "rate" in error_msg.lower() and "limit" in error_msg.lower():
                raise ProviderError(f"Rate limited: {error_msg}", retriable=True) from e
            if "content filtering" in error_msg.lower() or "blocked" in error_msg.lower():
                raise ProviderError(
                    "Response blocked by Anthropic content filter. "
                    "The command description likely triggered safety checks. "
                    "Local warnings still apply.",
                    retriable=False,
                ) from e
            raise ProviderError(f"API call failed: {error_msg}", retriable=True) from e

        # Extract text from response
        raw_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw_text += block.text

        # Extract token usage
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "usage") and response.usage:
            input_tokens = getattr(response.usage, "input_tokens", 0)
            output_tokens = getattr(response.usage, "output_tokens", 0)

        return _parse_response(raw_text, input_tokens, output_tokens)


def _parse_response(
    raw_text: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> AIReviewResponse:
    """Parse the structured response format into an AIReviewResponse."""
    # Extract fields using regex
    risk = _extract_field(raw_text, "RISK") or "caution"
    summary = _extract_field(raw_text, "SUMMARY") or "Could not parse summary."
    explanation = _extract_field(raw_text, "EXPLANATION") or ""
    suggestion = _extract_field(raw_text, "SUGGESTION") or ""

    # Normalize risk level
    risk = risk.lower().strip()
    if risk not in ("safe", "caution", "warning", "danger"):
        risk = "caution"

    # Clean up "None" suggestion
    if suggestion.lower().strip() in ("none", "n/a", "none."):
        suggestion = ""

    return AIReviewResponse(
        risk_assessment=risk,
        summary=summary,
        explanation=explanation,
        suggestion=suggestion,
        raw_text=raw_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _extract_field(text: str, field_name: str) -> str | None:
    """Extract a field value from the structured response."""
    pattern = re.compile(rf"^{field_name}:\s*(.+?)(?=\n[A-Z]+:|$)", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    if match:
        return match.group(1).strip()
    return None
