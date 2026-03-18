"""Tests for the deep analysis module (URL extraction, trigger detection)."""

import pytest

from ridincligun.provider.deep_analysis import (
    check_deep_analysis_trigger,
    build_deep_analysis_prompt,
    DEEP_ANALYSIS_SYSTEM,
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
