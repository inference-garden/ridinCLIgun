"""Mistral AI adapter for ridinCLIgun.

Uses the Mistral Python SDK to send command review requests.
Reuses the same prompt format and response parser as the other adapters.

SDK docs: https://docs.mistral.ai/getting-started/clients
Models:  https://docs.mistral.ai/getting-started/models
"""

from __future__ import annotations

import os
import re

from ridincligun.provider.base import AIReviewResponse, ProviderAdapter, ProviderError
from ridincligun.provider.prompt import SYSTEM_PROMPT, build_review_prompt

# Default model — small, fast, good enough for command review
_DEFAULT_MODEL = "mistral-small-latest"
_MAX_TOKENS = 512


class MistralAdapter(ProviderAdapter):
    """Adapter for Mistral AI's API."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("MISTRAL_API_KEY", "")
        self._model = model or _DEFAULT_MODEL
        self._client = None

    @property
    def name(self) -> str:
        return f"Mistral {self._model}"

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        """Lazy-init the Mistral client."""
        if self._client is None:
            try:
                from mistralai.client import Mistral
            except ImportError as e:
                raise ProviderError(
                    "mistralai package not installed. Run: pip install mistralai",
                    retriable=False,
                ) from e
            self._client = Mistral(api_key=self._api_key)
        return self._client

    async def review_command(
        self,
        command: str,
        context: str = "",
    ) -> AIReviewResponse:
        """Send a command to Mistral for review."""
        if not self.is_configured:
            raise ProviderError(
                "MISTRAL_API_KEY not set. Add it to ~/.config/ridincligun/.env",
                retriable=False,
            )

        user_message = build_review_prompt(command, context)

        try:
            client = self._get_client()
            import asyncio

            # Mistral SDK uses .chat.complete() (not .create())
            response = await asyncio.to_thread(
                client.chat.complete,
                model=self._model,
                max_tokens=_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            )
        except Exception as e:
            error_msg = str(e)
            if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
                raise ProviderError(f"Authentication failed: {error_msg}", retriable=False) from e
            if "rate" in error_msg.lower() and "limit" in error_msg.lower():
                raise ProviderError(f"Rate limited: {error_msg}", retriable=True) from e
            raise ProviderError(f"API call failed: {error_msg}", retriable=True) from e

        raw_text = response.choices[0].message.content or ""

        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "usage") and response.usage:
            input_tokens = getattr(response.usage, "prompt_tokens", 0)
            output_tokens = getattr(response.usage, "completion_tokens", 0)

        return _parse_response(raw_text, input_tokens, output_tokens)


def _parse_response(
    raw_text: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> AIReviewResponse:
    """Parse the structured response format into an AIReviewResponse."""
    risk = _extract_field(raw_text, "RISK") or "caution"
    summary = _extract_field(raw_text, "SUMMARY") or "Could not parse summary."
    explanation = _extract_field(raw_text, "EXPLANATION") or ""
    suggestion = _extract_field(raw_text, "SUGGESTION") or ""

    risk = risk.lower().strip()
    if risk not in ("safe", "caution", "warning", "danger"):
        risk = "caution"

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
