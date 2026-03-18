"""Tests for the input parser — command extraction from PTY screen buffer."""

import pyte
import pytest

from ridincligun.shell.input_parser import extract_current_command


def _make_screen(lines: list[str], cursor_y: int, cols: int = 80) -> pyte.Screen:
    """Create a pyte screen pre-filled with the given lines and cursor position."""
    rows = max(len(lines), cursor_y + 1, 24)
    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)
    # Feed lines separated by newlines
    for i, line in enumerate(lines):
        # Move to row i and write the line
        stream.feed(f"\033[{i + 1};1H{line}")
    # Position cursor
    screen.cursor.y = cursor_y
    screen.cursor.x = 0
    return screen


# ── Single-line commands ───────────────────────────────────────────

@pytest.mark.parametrize(
    "prompt_line,expected",
    [
        ("user@host:~/project$ ls -la", "ls -la"),
        ("user@host:~/project$ git status", "git status"),
        ("$ echo hello", "echo hello"),
        ("% pwd", "pwd"),
        (">>> print('hi')", "print('hi')"),
    ],
)
def test_single_line_command(prompt_line: str, expected: str) -> None:
    screen = _make_screen([prompt_line], cursor_y=0)
    assert extract_current_command(screen) == expected


def test_empty_prompt_returns_empty() -> None:
    screen = _make_screen(["user@host:~/project$ "], cursor_y=0)
    result = extract_current_command(screen)
    assert result == ""


def test_blank_line_returns_empty() -> None:
    screen = _make_screen([""], cursor_y=0)
    assert extract_current_command(screen) == ""


# ── Visual line wrapping ──────────────────────────────────────────

def test_wrapped_command_detected() -> None:
    """A command that wraps to a second line should be fully extracted."""
    cols = 40
    # Simulate: prompt + command fills line 0 completely, rest wraps to line 1
    prompt = "user@host:~$ "  # 14 chars
    cmd = "export ANTHROPIC_API_KEY=sk-ant-api03-realkey123456789"
    full = prompt + cmd

    # Line 0: first 40 chars (full width), Line 1: remainder
    line0 = full[:cols]
    line1 = full[cols:]

    screen = _make_screen([line0, line1], cursor_y=1, cols=cols)
    # Make line 0 full-width by padding to exactly cols
    for x in range(len(line0), cols):
        screen.buffer[0][x] = pyte.screens.Char(" ")

    result = extract_current_command(screen)
    assert "ANTHROPIC_API_KEY" in result
    assert "realkey" in result


def test_wrapped_command_joins_without_spaces() -> None:
    """Visual wraps are continuous text — joined without extra spaces."""
    cols = 30
    prompt = "$ "
    cmd = "echo abcdefghijklmnopqrstuvwxyz1234567890"
    full = prompt + cmd

    line0 = full[:cols]
    line1 = full[cols:]

    screen = _make_screen([line0, line1], cursor_y=1, cols=cols)
    for x in range(len(line0), cols):
        screen.buffer[0][x] = pyte.screens.Char(" ")

    result = extract_current_command(screen)
    assert "abcdefghijklmnopqrstuvwxyz1234567890" in result


# ── Backslash continuation ────────────────────────────────────────

def test_backslash_continuation() -> None:
    """Commands with trailing \\ should be joined across lines."""
    lines = [
        "user@host:~$ echo hello \\",
        "  world",
    ]
    screen = _make_screen(lines, cursor_y=1)
    result = extract_current_command(screen)
    assert "hello" in result
    assert "world" in result


# ── Previous output doesn't bleed in ──────────────────────────────

def test_previous_output_not_included() -> None:
    """Output from previous commands should not be included."""
    lines = [
        "some previous output",
        "more output",
        "user@host:~$ ls",
    ]
    screen = _make_screen(lines, cursor_y=2)
    result = extract_current_command(screen)
    assert result == "ls"
    assert "output" not in result
