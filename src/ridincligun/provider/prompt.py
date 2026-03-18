"""Prompt templates for AI command review.

Keeps all prompt engineering in one place — easy to tune without
touching adapter or manager code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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
- Commands may contain placeholders like [SENSITIVE_FILE] or [REDACTED] — these
  represent privacy-redacted values. Treat them as their real equivalents.

Response format (use exactly these headers):
RISK: <safe|caution|warning|danger>
SUMMARY: <one-line factual description>
EXPLANATION: <why this risk level, 1-3 short sentences, clinical tone>
SUGGESTION: <safer alternative, or "None" if appropriate>
"""

# ── Command sanitization ──────────────────────────────────────────
#
# Privacy-only redaction: we only redact values that could leak user
# secrets or sensitive file paths. Command structure (rm -rf /, | bash,
# /dev/sda, etc.) is sent unmodified — the AI needs this context to
# give accurate risk assessments.

_SANITIZE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # ── Sensitive file paths ───────────────────────────────────────
    # SSH keys, credentials, shadow, shell history
    (re.compile(r"~?/\.ssh/\S+"), "[SENSITIVE_FILE]"),
    (re.compile(r"~?/\.aws/\S+"), "[SENSITIVE_FILE]"),
    (re.compile(r"~?/\.gnupg/\S+"), "[SENSITIVE_FILE]"),
    (re.compile(r"/etc/shadow\b"), "[SENSITIVE_FILE]"),
    (re.compile(r"/etc/gshadow\b"), "[SENSITIVE_FILE]"),
    (re.compile(r"~?/\.\w*hist\w*\b"), "[SENSITIVE_FILE]"),
    (re.compile(r"~?/\.netrc\b"), "[SENSITIVE_FILE]"),
    (re.compile(r"~?/\.pgpass\b"), "[SENSITIVE_FILE]"),

    # ── Inline secrets in commands ─────────────────────────────────
    # export SECRET_KEY=value, export API_KEY=value etc.
    (re.compile(
        r"(export\s+\w*(SECRET|KEY|TOKEN|PASSWORD|CREDENTIAL|AUTH)\w*=)\S+",
        re.IGNORECASE,
    ), r"\1[REDACTED]"),
]


def _sanitize_command(command: str) -> str:
    """Redact privacy-sensitive values from a command before sending to AI.

    Only redacts secrets and sensitive file paths. Command structure
    (dangerous verbs, flags, targets, pipe chains) is preserved so the
    AI can give accurate risk assessments.

    KNOWN LIMITS (best-effort, not a privacy guarantee):
    - Only covers patterns in _SANITIZE_PATTERNS; novel secret formats pass through.
    - Does not parse shell syntax — aliases, variables, backticks, $() can bypass.
    - Does not redact arbitrary user data (filenames, hostnames, URLs).
    - The real-time secret detector (advisory/secret_detector.py) is the primary
      defense — this is a secondary safety net.
    """
    result = command
    for pattern, replacement in _SANITIZE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


# Human-readable labels for placeholder types
_PLACEHOLDER_LABELS: dict[str, str] = {
    "[SENSITIVE_FILE]": "Sensitive file path",
    "[REDACTED]": "Secret value",
}


@dataclass(frozen=True)
class RedactionDiff:
    """Comparison of original vs. redacted command."""

    original: str
    redacted: str
    has_changes: bool
    placeholders: list[tuple[str, str]]  # (placeholder, human-readable reason)


def get_redaction_diff(command: str) -> RedactionDiff:
    """Compare a command before and after sanitization.

    Returns the original, the redacted version, and a list of
    placeholders that were inserted with human-readable explanations.
    """
    redacted = _sanitize_command(command)
    has_changes = redacted != command

    # Find which placeholders are present in the redacted output
    seen: set[str] = set()
    placeholders: list[tuple[str, str]] = []
    for placeholder, label in _PLACEHOLDER_LABELS.items():
        if placeholder in redacted and placeholder not in command:
            if placeholder not in seen:
                seen.add(placeholder)
                placeholders.append((placeholder, label))

    return RedactionDiff(
        original=command,
        redacted=redacted,
        has_changes=has_changes,
        placeholders=placeholders,
    )


def build_review_prompt(command: str, context: str = "") -> str:
    """Build the user message for a command review request."""
    sanitized = _sanitize_command(command)
    parts = [f"Classify this shell command:\n```\n{sanitized}\n```"]
    if context:
        parts.append(f"\nContext: {context}")
    return "\n".join(parts)
