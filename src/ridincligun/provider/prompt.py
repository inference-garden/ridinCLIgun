# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Prompt sanitization and templates

"""Prompt templates for AI command review.

Keeps all prompt engineering in one place — easy to tune without
touching adapter or manager code.

The system prompt is composed from three layers:
1. BASE_SYSTEM_PROMPT — always included, defines role + response format
2. Category supplement — domain-specific hints based on matched command families
3. Mode supplement — tone/audience adjustment (default, explorer)

Templates are loaded from data/prompt_templates.toml at import time.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

# ── Base system prompt (always included) ─────────────────────────

_BASE_SYSTEM_PROMPT = """\
You are a technical shell command reviewer in a developer tool called ridinCLIgun.

Your job: classify shell commands by risk and explain them factually.

Rules:
- You only describe and classify. You never execute anything.
- Classify risk as: "safe", "caution", "warning", or "danger".
- Suggest safer alternatives when applicable. For non-safe commands, provide
  a concrete safer alternative command that achieves a similar goal.
- Keep responses short — displayed in a narrow side panel.
- Commands may contain placeholders like [SENSITIVE_FILE] or [REDACTED] — these
  represent privacy-redacted values. Treat them as their real equivalents.
- If the command contains what appears to be a real API key, password, token,
  or credential (not a placeholder), flag this immediately in your response
  and advise the user to rotate it. This is a critical safety check.

Response format (use exactly these headers):
RISK: <safe|caution|warning|danger>
SUMMARY: <one-line factual description>
EXPLANATION: <why this risk level, 1-3 short sentences>
SUGGESTION: <a concrete safer/better command, or "None" if the command is already safe>

Before responding, verify internally:
1. Warnings are specific to the actual flags/arguments passed — not generic.
2. Risk level matches the real danger — do not over-warn safe commands.
3. No unnecessary explanations — be concise.
"""

# ── Template loading ─────────────────────────────────────────────

_TEMPLATES: dict = {}


def _load_templates() -> dict:
    """Load prompt_templates.toml from the data directory."""
    # Try installed package data first, then repo layout
    try:
        data_ref = resources.files("ridincligun") / "data" / "prompt_templates.toml"
        raw = data_ref.read_bytes()
    except (FileNotFoundError, TypeError):
        repo_path = Path(__file__).resolve().parents[3] / "data" / "prompt_templates.toml"
        raw = repo_path.read_bytes()
    return tomllib.loads(raw.decode("utf-8"))


def _get_templates() -> dict:
    """Return cached templates, loading on first access."""
    global _TEMPLATES
    if not _TEMPLATES:
        _TEMPLATES = _load_templates()
    return _TEMPLATES


# ── Category resolution ──────────────────────────────────────────

def resolve_category(family_ids: list[str]) -> str:
    """Map matched command family IDs to a prompt category name.

    Returns the first matching category, or "general" if no families matched.
    """
    if not family_ids:
        return "general"

    templates = _get_templates()
    categories = templates.get("categories", {})

    for cat_name, cat_data in categories.items():
        if cat_name == "general":
            continue
        cat_families = cat_data.get("families", [])
        for fid in family_ids:
            if fid in cat_families:
                return cat_name

    return "general"


# ── System prompt composition ────────────────────────────────────

def build_system_prompt(
    category: str = "general",
    mode: str = "default",
) -> str:
    """Compose the full system prompt from base + category + mode.

    Args:
        category: Prompt category name (e.g. "file_ops", "network", "general").
        mode: User mode (e.g. "default", "explorer").

    Returns:
        The assembled system prompt string.
    """
    templates = _get_templates()
    parts = [_BASE_SYSTEM_PROMPT.rstrip()]

    # Category supplement
    cat_data = templates.get("categories", {}).get(category, {})
    cat_supplement = cat_data.get("supplement", "").strip()
    if cat_supplement:
        parts.append(f"\nCategory-specific guidance:\n{cat_supplement}")

    # Mode supplement
    mode_data = templates.get("modes", {}).get(mode, {})
    mode_supplement = mode_data.get("supplement", "").strip()
    if mode_supplement:
        parts.append(f"\nTone and audience:\n{mode_supplement}")

    return "\n".join(parts)


# Backward-compatible alias — adapters that haven't been updated yet
# get the base prompt (general category, default mode).
SYSTEM_PROMPT = _BASE_SYSTEM_PROMPT

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
