# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Command extraction from terminal

"""Input parser — extracts the current command from the PTY screen buffer.

This is inherently heuristic: we read the cursor line from the pyte screen
and strip the shell prompt. It's conservative — prefers returning empty
(no warning) over a false match.

Handles:
- Single-line commands (prompt + command on one line)
- Visual line wrapping (long commands that wrap across multiple screen rows)
- Backslash continuation (explicit multi-line commands with trailing \\)

Known limitations:
- Custom prompts with very unusual formatting may not be stripped correctly.
  (Most common prompt styles are covered.)
"""

from __future__ import annotations

import re

import pyte

# Common prompt patterns to strip.
# These are tried in order; first match wins.
_PROMPT_PATTERNS: list[re.Pattern[str]] = [
    # user@host:path$ or user@host path%
    re.compile(r"^[\w.-]+@[\w.-]+[:\s][^\$#%>]*[\$#%>]\s*"),
    # Bare arrow/symbol prompt (Starship ❯, oh-my-zsh ➜): just symbol + whitespace.
    # Handles two-line Starship prompts where ❯ starts the command line.
    re.compile(r"^[➜→›❯▶]\s+"),
    # Starship info line ending with arrow (two-line prompt, e.g. "...v3.14.3❯")
    # The entire line is prompt — strip it completely.
    re.compile(r"^.*[➜→›❯▶]\s*$"),
    # oh-my-zsh themes: arrow/symbol prefix + path + terminator, e.g. "➜  ~/project $"
    re.compile(r"^[➜→›❯▶][^\$#%>]+[\$#%>]\s*"),
    # Starship / powerline: complex unicode then $ or %
    re.compile(r"^.*?[\$#%>]\s+"),
    # ~/path $ or /path %
    re.compile(r"^[~\/][\w\/._-]*\s*[\$#%>]\s*"),
    # bare $ or % or >>> (with required whitespace after)
    re.compile(r"^[\$#%>]{1,3}\s+"),
]


def _has_prompt(line: str) -> bool:
    """Check if a line contains a shell prompt."""
    for pattern in _PROMPT_PATTERNS:
        if pattern.search(line):
            return True
    return False


def _is_full_width(line: str, columns: int) -> bool:
    """Check if a line fills the full terminal width (visual wrap indicator)."""
    # A visually wrapped line uses all columns — _read_line strips trailing
    # spaces, so a full-width line's raw length equals the column count.
    # We check the raw buffer length instead.
    return len(line) >= columns


def extract_current_command(screen: pyte.Screen) -> str:
    """Extract the current command being typed from the pyte screen.

    Reads the cursor line, strips the prompt, and returns the command text.
    Handles visual line wrapping (long commands that span multiple rows)
    and backslash continuation (explicit multi-line commands).

    Returns empty string if no command is detected.
    """
    cursor_y = screen.cursor.y

    # Read the line at cursor position
    line = _read_line(screen, cursor_y)
    if not line.strip():
        return ""

    # Try to strip prompt from cursor line
    stripped = _strip_prompt(line)
    prompt_on_cursor_line = stripped != line

    if prompt_on_cursor_line:
        # Prompt is on cursor line — single visual line, but check for
        # backslash continuation above
        command = stripped.strip()
        parts = [command]
        y = cursor_y - 1
        while y >= 0:
            prev_line = _read_line(screen, y)
            prev_rstrip = prev_line.rstrip()
            if prev_rstrip.endswith("\\"):
                cont = _strip_prompt(prev_line).rstrip()
                if cont.endswith("\\"):
                    cont = cont[:-1].rstrip()
                parts.insert(0, cont)
                y -= 1
            else:
                break
        return " ".join(parts).strip()

    # No prompt on cursor line — command has visually wrapped.
    # Walk upward to find the prompt line, collecting wrapped segments.
    # Visual wraps produce full-width lines (terminal wraps at column boundary).
    wrapped_parts = [line.rstrip()]
    y = cursor_y - 1
    max_walk = 20  # safety limit — don't walk through pages of output

    while y >= 0 and max_walk > 0:
        prev_line = _read_line(screen, y)

        if _has_prompt(prev_line):
            # Found the prompt line — extract command portion and prepend
            cmd_part = _strip_prompt(prev_line)
            wrapped_parts.insert(0, cmd_part.rstrip())
            break

        # No prompt — could be another wrapped segment or unrelated output.
        # Only join if the line is full-width (visual wrap indicator).
        raw_line = _read_line_raw(screen, y)
        if _is_full_width(raw_line, screen.columns):
            wrapped_parts.insert(0, prev_line.rstrip())
            y -= 1
            max_walk -= 1
        else:
            # Not full-width and no prompt — this is unrelated output
            break

    # Visual wraps are continuous text split at column boundary — join without spaces
    return "".join(wrapped_parts).strip()


def _read_line_raw(screen: pyte.Screen, y: int) -> str:
    """Read a line from the screen buffer WITHOUT rstrip (preserves trailing spaces)."""
    if y < 0 or y >= screen.lines:
        return ""
    line_buf = screen.buffer[y]
    chars = []
    for x in range(screen.columns):
        char = line_buf[x]
        chars.append(char.data if char.data else " ")
    return "".join(chars)


def _strip_prompt(line: str) -> str:
    """Strip the shell prompt from a line using known patterns."""
    for pattern in _PROMPT_PATTERNS:
        result = pattern.sub("", line, count=1)
        if result != line:
            return result
    return line


def _read_line(screen: pyte.Screen, y: int) -> str:
    """Read a single line from the pyte screen buffer as a string."""
    if y < 0 or y >= screen.lines:
        return ""
    line_buf = screen.buffer[y]
    chars = []
    for x in range(screen.columns):
        char = line_buf[x]
        chars.append(char.data if char.data else " ")
    return "".join(chars).rstrip()
