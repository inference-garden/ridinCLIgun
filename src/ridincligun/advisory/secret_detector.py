"""Real-time secret detection for shell input.

Scans command text for likely secrets (API keys, passwords, tokens, credential
URLs, cloud credentials) while the user types. Runs synchronously on every
keystroke — patterns must be fast.

When secrets are detected, the advisory pane warns the user and AI review is
auto-suppressed unless explicitly overridden.

KNOWN LIMITS (best-effort, not a guarantee):
- Only detects patterns listed below; novel credential formats pass through.
- Does not parse shell syntax — variable expansion, backticks, $() can hide secrets.
- Short or unusual tokens may not match the length/prefix heuristics.
- Base64-encoded secrets without a recognisable prefix are not caught.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SecretMatch:
    """A single detected secret in the command."""

    kind: str          # e.g. "api_key", "password_flag", "credential_url"
    description: str   # human-readable explanation


@dataclass
class SecretDetectionResult:
    """Result of scanning a command for secrets."""

    matches: list[SecretMatch] = field(default_factory=list)

    @property
    def has_secrets(self) -> bool:
        return len(self.matches) > 0


# ── Detection patterns ────────────────────────────────────────────
#
# Each entry: (compiled regex, kind, description)
# Order doesn't matter — all patterns are checked.

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # ── API key prefixes (provider-specific) ───────────────────────
    (
        re.compile(r"sk-ant-api\w{2}-[\w-]{20,}"),
        "api_key",
        "Anthropic API key detected",
    ),
    (
        re.compile(r"sk-[a-zA-Z0-9][\w-]{20,}"),
        "api_key",
        "OpenAI-style API key detected",
    ),
    (
        re.compile(r"ghp_[A-Za-z0-9]{30,}"),
        "api_key",
        "GitHub personal access token detected",
    ),
    (
        re.compile(r"gho_[A-Za-z0-9]{30,}"),
        "api_key",
        "GitHub OAuth token detected",
    ),
    (
        re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
        "api_key",
        "GitHub fine-grained PAT detected",
    ),
    (
        re.compile(r"xox[bprs]-[\w-]{10,}"),
        "api_key",
        "Slack token detected",
    ),
    (
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "api_key",
        "AWS access key ID detected",
    ),
    (
        re.compile(r"AIza[0-9A-Za-z_-]{35}"),
        "api_key",
        "Google API key detected",
    ),
    (
        re.compile(r"glpat-[\w-]{20,}"),
        "api_key",
        "GitLab personal access token detected",
    ),
    (
        re.compile(r"npm_[A-Za-z0-9]{30,}"),
        "api_key",
        "npm access token detected",
    ),
    (
        re.compile(r"pypi-[A-Za-z0-9]{30,}"),
        "api_key",
        "PyPI API token detected",
    ),

    # ── Password flags ─────────────────────────────────────────────
    # Require -p followed by a word that looks like a password (letters/symbols,
    # not just digits/colons which are ports like 8080:80)
    (
        re.compile(r"""-p\s*['"]?(?![0-9.:]+(?:\s|$))[^\s'"]{4,}"""),
        "password_flag",
        "Password passed via -p flag",
    ),
    (
        re.compile(r"""--password[=\s]+['"]?[^\s'"]{4,}"""),
        "password_flag",
        "Password passed via --password flag",
    ),

    # ── Credential URLs ────────────────────────────────────────────
    (
        re.compile(r"://[^:/@\s]+:[^:/@\s]+@"),
        "credential_url",
        "Credentials embedded in URL (user:pass@host)",
    ),

    # ── Export / assignment of secrets ──────────────────────────────
    (
        re.compile(
            r"""(?:export\s+)?\w*(?:SECRET|KEY|TOKEN|PASSWORD|CREDENTIAL|AUTH|PASSWD)\w*\s*=\s*['"]?[^\s'"]{8,}""",
            re.IGNORECASE,
        ),
        "env_secret",
        "Secret value assigned to sensitive variable",
    ),

    # ── Private key content ────────────────────────────────────────
    (
        re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----"),
        "private_key",
        "Private key content detected",
    ),

    # ── Bearer / Authorization headers ─────────────────────────────
    (
        re.compile(r"""(?:Authorization|Bearer)[:\s]+['"]?[A-Za-z0-9_.+/=-]{20,}""", re.IGNORECASE),
        "auth_header",
        "Authorization header with token detected",
    ),
]


def detect_secrets(command: str) -> SecretDetectionResult:
    """Scan a command string for likely secrets.

    Returns a SecretDetectionResult with all matches found.
    Fast enough to run on every keystroke.
    """
    if not command or not command.strip():
        return SecretDetectionResult()

    matches: list[SecretMatch] = []
    seen_kinds: set[str] = set()

    for pattern, kind, description in _SECRET_PATTERNS:
        if pattern.search(command):
            # Deduplicate by kind — one warning per category is enough
            key = kind
            if key not in seen_kinds:
                seen_kinds.add(key)
                matches.append(SecretMatch(kind=kind, description=description))

    return SecretDetectionResult(matches=matches)
