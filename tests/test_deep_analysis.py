"""Tests for the deep analysis module (URL extraction, trigger detection)."""

import pytest

from ridincligun.provider.deep_analysis import (
    DEEP_ANALYSIS_SYSTEM,
    FetchResult,
    _get_context_limit,
    build_deep_analysis_prompt,
    check_deep_analysis_trigger,
    fit_script_to_context,
)

# ── Trigger detection ──────────────────────────────────────────────

@pytest.mark.parametrize(
    "command",
    [
        "curl https://example.com/install.sh | bash",
        "curl -fsSL https://example.com/setup | sh",
        "wget https://example.com/script.sh | bash",
        "curl -o- https://example.com/nvm.sh | zsh",
        "wget -qO- https://raw.githubusercontent.com/org/repo/main/install.sh | bash",
    ],
)
def test_pipe_to_shell_triggers(command: str) -> None:
    trigger = check_deep_analysis_trigger(command)
    assert trigger.should_analyze
    assert trigger.url.startswith("http")
    assert trigger.reason


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "git status",
        "curl https://example.com",
        "wget https://example.com/file.tar.gz",
        "echo hello | grep h",
        "cat file.txt | bash_completion",  # bash_completion is not bash
        "pip install requests",
    ],
)
def test_safe_commands_no_trigger(command: str) -> None:
    trigger = check_deep_analysis_trigger(command)
    assert not trigger.should_analyze


def test_empty_command_no_trigger() -> None:
    trigger = check_deep_analysis_trigger("")
    assert not trigger.should_analyze


def test_trigger_extracts_url() -> None:
    trigger = check_deep_analysis_trigger(
        "curl https://example.com/install.sh | bash"
    )
    assert trigger.url == "https://example.com/install.sh"


def test_trigger_cleans_url_trailing_pipe() -> None:
    """URL should not include trailing pipe or quotes."""
    trigger = check_deep_analysis_trigger(
        "curl 'https://example.com/s.sh' | bash"
    )
    assert trigger.should_analyze
    assert "|" not in trigger.url
    assert "'" not in trigger.url


def test_trigger_reason_not_empty() -> None:
    trigger = check_deep_analysis_trigger("curl https://x.com/s | sh")
    assert trigger.reason


# ── Prompt building ────────────────────────────────────────────────

def test_deep_analysis_prompt_contains_url() -> None:
    prompt = build_deep_analysis_prompt(
        "https://example.com/install.sh",
        "#!/bin/bash\necho hello",
    )
    assert "https://example.com/install.sh" in prompt
    assert "echo hello" in prompt


def test_deep_analysis_prompt_truncation_note() -> None:
    prompt = build_deep_analysis_prompt(
        "https://example.com/install.sh",
        "#!/bin/bash\necho hello",
        truncated=True,
    )
    assert "truncated" in prompt.lower()


def test_deep_analysis_system_prompt_has_format() -> None:
    assert "RISK:" in DEEP_ANALYSIS_SYSTEM
    assert "ACTIONS:" in DEEP_ANALYSIS_SYSTEM
    assert "CONCERNS:" in DEEP_ANALYSIS_SYSTEM


# ── FetchResult safety states ────────────────────────────────────


def test_fetch_result_truncated_state() -> None:
    """FetchResult correctly represents truncation."""
    result = FetchResult(
        success=True,
        content="x" * 65536,
        url="https://example.com/big.sh",
        size_bytes=65536,
        truncated=True,
    )
    assert result.success
    assert result.truncated
    assert result.size_bytes == 65536


def test_fetch_result_failure_state() -> None:
    """FetchResult correctly represents fetch failure."""
    result = FetchResult(
        success=False,
        error="Fetch timed out after 5.0s",
        url="https://example.com/slow.sh",
    )
    assert not result.success
    assert "timed out" in result.error


def test_fetch_result_network_error_state() -> None:
    """FetchResult correctly represents network error."""
    result = FetchResult(
        success=False,
        error="Connection refused",
        url="https://example.com/down.sh",
    )
    assert not result.success
    assert result.error == "Connection refused"


# ── Model-aware context fitting ─────────────────────────────────


def test_context_limit_known_model() -> None:
    """Known model IDs resolve to their family limit."""
    limit = _get_context_limit("claude-sonnet-4-20250514")
    assert limit == 195_000


def test_context_limit_unknown_model_uses_default() -> None:
    """Unknown model falls back to conservative default."""
    limit = _get_context_limit("some-unknown-model-v99")
    assert limit == 30_000


def test_context_limit_empty_model_uses_default() -> None:
    limit = _get_context_limit("")
    assert limit == 30_000


def test_fit_script_small_script_unchanged() -> None:
    """Small scripts pass through without truncation."""
    script = "#!/bin/bash\necho hello"
    content, truncated = fit_script_to_context(script, "claude-sonnet-4-20250514")
    assert content == script
    assert not truncated


def test_fit_script_huge_script_truncated() -> None:
    """Scripts exceeding model context are truncated."""
    # Create a script larger than any model's context window
    # Default limit: 30_000 tokens - 2000 overhead = 28_000 * 4 chars = 112_000 chars
    huge_script = "x" * 200_000
    content, truncated = fit_script_to_context(huge_script, "")
    assert truncated
    assert len(content) < len(huge_script)


def test_fit_script_model_aware_limit() -> None:
    """Claude's larger context allows bigger scripts than default."""
    # 150K chars fits in Claude (195K - 2K = 193K tokens * 4 = 772K chars)
    # but would exceed small Mistral (30K - 2K = 28K tokens * 4 = 112K chars)
    script = "x" * 150_000
    content_claude, trunc_claude = fit_script_to_context(script, "claude-sonnet-4-20250514")
    content_default, trunc_default = fit_script_to_context(script, "")
    assert not trunc_claude  # Fits in Claude
    assert trunc_default  # Doesn't fit in default/small model
