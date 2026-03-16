"""Input parser — extracts the current command from the PTY screen buffer.

This is inherently heuristic: we read the cursor line from the pyte screen
and strip the shell prompt. It's conservative — prefers returning empty
(no warning) over a false match.

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
    # oh-my-zsh themes: arrow/symbol prefix + path, e.g. "➜  ~/project"
    re.compile(r"^[➜→›❯▶][^\$#%>]*[\$#%>]?\s*"),
    # Starship / powerline: complex unicode then $ or %
    re.compile(r"^.*?[\$#%>]\s+"),
    # ~/path $ or /path %
    re.compile(r"^[~\/][\w\/._-]*\s*[\$#%>]\s*"),
    # bare $ or % or >>> (with required whitespace after)
    re.compile(r"^[\$#%>]{1,3}\s+"),
]


def extract_current_command(screen: pyte.Screen) -> str:
    """Extract the current command being typed from the pyte screen.

    Reads the cursor line, strips the prompt, and returns the command text.
    Also handles multi-line commands (backslash continuation) by joining
    continuation lines above the cursor.

    Returns empty string if no command is detected.
    """
    cursor_y = screen.cursor.y

    # Read the line at cursor position
    line = _read_line(screen, cursor_y)
    if not line.strip():
        return ""

    # Strip the prompt from the current line
    command = _strip_prompt(line).strip()

    # Check for multi-line continuation: walk upward while lines end with '\'
    parts = [command]
    y = cursor_y - 1
    while y >= 0:
        prev_line = _read_line(screen, y)
        stripped = prev_line.rstrip()
        if stripped.endswith("\\"):
            # This is a continuation line — strip prompt (first line) or take as-is
            cont = _strip_prompt(prev_line).rstrip()
            if cont.endswith("\\"):
                cont = cont[:-1].rstrip()  # remove trailing backslash
            parts.insert(0, cont)
            y -= 1
        else:
            break

    return " ".join(parts).strip()


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
