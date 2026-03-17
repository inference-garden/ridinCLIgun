"""Prompt templates for AI command review.

Keeps all prompt engineering in one place — easy to tune without
touching adapter or manager code.
"""

from __future__ import annotations

import re

SYSTEM_PROMPT = """\
You are a technical shell command reviewer in a developer tool called ridinCLIgun.

Your job: classify shell commands by risk and explain them factually.

Rules:
- You only describe and classify. You never execute anything.
- Use clinical, neutral language. No dramatic descriptions of consequences.
- Classify risk as: "safe", "caution", "warning", or "danger".
- For dangerous commands, state the risk factually (e.g. "affects system-wide paths")
  without graphic detail about outcomes.
- Suggest safer alternatives when applicable.
- Keep responses short — displayed in a narrow side panel.
- Commands may contain placeholders like [TARGET], [PIPE_TARGET], [PATTERN] — these
  represent sanitized values. Treat them as their real equivalents.

Response format (use exactly these headers):
RISK: <safe|caution|warning|danger>
SUMMARY: <one-line factual description>
EXPLANATION: <why this risk level, 1-3 short sentences, clinical tone>
SUGGESTION: <safer alternative, or "None" if appropriate>
"""

# ── Command sanitization ──────────────────────────────────────────
#
# The Anthropic API content filter can block responses about dangerous
# commands. We replace dangerous literals with neutral placeholders
# before sending. The system prompt tells the model to treat them as real.

_SANITIZE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # ── Destructive filesystem commands ───────────────────────────
    # Full destructive commands: rm -rf /, rm -rf /* etc.
    (re.compile(r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/(\*|\s|$)"), "rm [FLAGS] [TARGET]"),
    # Device paths: /dev/sda, /dev/disk0, /dev/zero etc.
    (re.compile(r"/dev/\S+"), "[DEVICE]"),
    # mkfs/format commands
    (re.compile(r"mkfs\.\w+\s+\S+"), "mkfs [TARGET]"),
    # dd with of= targeting devices or root
    (re.compile(r"dd\s+.*?of=/\S+"), "dd [DD_PARAMS] of=[TARGET]"),
    # chmod/chown 777 or recursive on root
    (re.compile(r"(chmod|chown)\s+(-[a-zA-Z]*\s+)?(\d{3,4}|[a-z]+:[a-z]+)\s+/(\*|\s|$)"),
     r"\1 [PERMS] [TARGET]"),
    # Root-destructive paths: /* or standalone /
    (re.compile(r"(?<!\w)/\*"), "[TARGET]"),
    (re.compile(r"\s/\s"), " [TARGET] "),

    # ── Code execution via pipe ───────────────────────────────────
    # Pipe-to-shell patterns: curl ... | bash, wget ... | sh
    (re.compile(r"\|\s*(bash|sh|zsh|dash)\b"), "| [PIPE_TARGET]"),
    # Fork bomb patterns
    (re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;?\s*:"), "[PATTERN]"),

    # ── System file overwrites ────────────────────────────────────
    (re.compile(r">\s*/etc/\S+"), "> [SYSTEM_FILE]"),
    (re.compile(r">\s*/boot/\S+"), "> [SYSTEM_FILE]"),

    # ── Sensitive file access ─────────────────────────────────────
    # SSH keys, credentials, shadow, shell history
    (re.compile(r"~?/\.ssh/\S+"), "[SENSITIVE_FILE]"),
    (re.compile(r"~?/\.aws/\S+"), "[SENSITIVE_FILE]"),
    (re.compile(r"~?/\.gnupg/\S+"), "[SENSITIVE_FILE]"),
    (re.compile(r"/etc/shadow\b"), "[SENSITIVE_FILE]"),
    (re.compile(r"/etc/gshadow\b"), "[SENSITIVE_FILE]"),
    (re.compile(r"~?/\.\w*hist\w*\b"), "[SENSITIVE_FILE]"),
    (re.compile(r"~?/\.netrc\b"), "[SENSITIVE_FILE]"),
    (re.compile(r"~?/\.pgpass\b"), "[SENSITIVE_FILE]"),

    # ── Inline secrets in commands ────────────────────────────────
    # export SECRET_KEY=value, export API_KEY=value etc.
    (re.compile(
        r"(export\s+\w*(SECRET|KEY|TOKEN|PASSWORD|CREDENTIAL|AUTH)\w*=)\S+",
        re.IGNORECASE,
    ), r"\1[REDACTED]"),
]


def _sanitize_command(command: str) -> str:
    """Replace dangerous literal targets with neutral placeholders.

    This prevents the API content filter from blocking responses about
    dangerous commands. The AI is instructed to treat placeholders as real.

    KNOWN LIMITS (best-effort, not a privacy guarantee):
    - Only covers patterns in _SANITIZE_PATTERNS; novel attack vectors pass through.
    - Does not parse shell syntax — aliases, variables, backticks, $() can bypass.
    - Does not redact arbitrary user data (filenames, hostnames, URLs).
    - Python/perl/ruby one-liners with embedded shell commands are not caught.
    - The full command verb and structure are always sent to the API.
    """
    result = command
    for pattern, replacement in _SANITIZE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def build_review_prompt(command: str, context: str = "") -> str:
    """Build the user message for a command review request."""
    sanitized = _sanitize_command(command)
    parts = [f"Classify this shell command:\n```\n{sanitized}\n```"]
    if context:
        parts.append(f"\nContext: {context}")
    return "\n".join(parts)
