# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — CommandFacts: one local analysis pass for the router

"""CommandFacts — a single local pass producing the facts the router needs.

One deterministic, offline analysis of the typed command yields every signal the
investigation-depth router consumes, so there is **one source of truth** reused by
Layer-2 prompt categorisation and the Layer-3 trigger (no catalog/regex drift):

- ``severity``         — highest local-catalog risk (reuses :class:`AdvisoryEngine`)
- ``boundary_score``   — count of trust-boundary crossings
- ``complexity_score`` — obfuscation/composition signals
- ``evidence_gain``    — can deeper analysis fetch new remote evidence? (reuses the
                         Layer-3 trigger)
- ``category``         — prompt category, resolved here ONCE (not first-match-wins)

The scorers are intentionally **cheap, local, deterministic** — no shell AST, no
network, no I/O. Each signal contributes **at most +1** (the score is the count of
*distinct* boundary/complexity categories that fire). Raw pipe-count and command
length are weak contributors *inside* ``complexity_score`` only — never standalone.

The regexes are kept simple and linear on purpose (the S1 ReDoS lesson: matching
logic is load-bearing; changing it risks silent drift, so behaviour is corpus-pinned
in ``tests/test_command_facts.py``).

Layering note: this module stays provider-free. ``resolve_category`` (prompt
categorisation) and the Layer-3 trigger live in the provider package; they are
**injected** into :func:`build_command_facts` as callables so advisory never imports
provider.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ridincligun.advisory.engine import AdvisoryEngine
from ridincligun.advisory.models import RiskLevel
from ridincligun.advisory.secret_detector import detect_secrets


@dataclass(frozen=True)
class CommandFacts:
    """The local facts a single command analysis pass produces."""

    severity: RiskLevel
    boundary_score: int
    complexity_score: int
    evidence_gain: bool
    evidence_url: str  # the fetchable remote-script URL ("" when evidence_gain is False)
    category: str


# ── Boundary signals (trust-boundary crossings) ──────────────────────
#
# Each compiled pattern is ONE boundary category; boundary_score is the number of
# distinct categories that match. Order is irrelevant — all are checked.

# 1. Privilege escalation — sudo/doas/su as a command (leading or after a separator).
_BOUNDARY_PRIVILEGE = re.compile(r"(?:^|[\s;&|(])(?:sudo|doas|su)\b")

# 2. Write to /etc — redirect / tee / cp / mv / rm / install targeting /etc/.
#    Read-only verbs (cat/less/grep) deliberately excluded — reading /etc is not a write.
_BOUNDARY_WRITE_ETC = re.compile(
    r">>?\s*/etc/"
    r"|\btee\b\s+(?:-a\s+)?/etc/"
    r"|\b(?:cp|mv|rm|install)\b[^;&|]*\s/etc/"
)

# 3. Raw /dev device write — dd of=/dev/…, redirect to /dev/…, or a raw disk node.
#    The safe pseudo-devices (null/stdout/stderr/tty/zero/random/urandom) are excluded.
_BOUNDARY_WRITE_DEV = re.compile(
    r"\bof=/dev/(?!null|stdout|stderr|tty|zero|random|urandom)\w"
    r"|>>?\s*/dev/(?!null|stdout|stderr|tty)\w"
    r"|/dev/(?:sd[a-z]|disk\d)"
)

# 4. Network fetch / remote transport. The negative lookbehind stops a transport
#    keyword from matching *inside* a path/identifier — e.g. "ssh" in "~/.ssh/",
#    where a bare \b would false-fire because "." is a word boundary.
_BOUNDARY_NETWORK = re.compile(
    r"(?<![\w./])(?:curl|wget|nc|ncat|scp|rsync|ssh|sftp|ftp|telnet)\b" r"|https?://"
)

# 5. Public exposure — binding to all interfaces, ad-hoc servers, tunnels, world-rwx.
_BOUNDARY_EXPOSURE = re.compile(
    r"\b0\.0\.0\.0\b"
    r"|-m\s+http\.server"
    r"|\bngrok\b"
    r"|\bchmod\s+(?:-[A-Za-z]+\s+)*0?777\b"
    r"|--host[=\s]+(?:0\.0\.0\.0|\*)"
)

# 6. Secret handling — sensitive files / key material (the value side is covered by
#    detect_secrets()). Mirrors the sanitize/secret patterns; kept local so advisory
#    stays self-contained.
_BOUNDARY_SECRET_FILE = re.compile(
    r"~?/\.ssh/"
    r"|~?/\.aws/"
    r"|~?/\.gnupg/"
    r"|/etc/g?shadow\b"
    r"|~?/\.netrc\b"
    r"|~?/\.pgpass\b"
    r"|\.env\b"
    r"|\bid_rsa\b"
    r"|\bid_ed25519\b"
    r"|\.pem\b"
    r"|\bgpg\b"
)


def score_boundary(command: str) -> int:
    """Count distinct trust-boundary crossings in *command* (0–6).

    Deterministic and offline. Each of the six boundary categories contributes at
    most +1.
    """
    if not command:
        return 0
    score = 0
    if _BOUNDARY_PRIVILEGE.search(command):
        score += 1
    if _BOUNDARY_WRITE_ETC.search(command):
        score += 1
    if _BOUNDARY_WRITE_DEV.search(command):
        score += 1
    if _BOUNDARY_NETWORK.search(command):
        score += 1
    if _BOUNDARY_EXPOSURE.search(command):
        score += 1
    if detect_secrets(command).has_secrets or _BOUNDARY_SECRET_FILE.search(command):
        score += 1
    return score


# ── Complexity signals (obfuscation / composition) ───────────────────

# 1. Command substitution — $(...) or backticks.
_CX_SUBST = re.compile(r"\$\(|`")

# 2. eval.
_CX_EVAL = re.compile(r"\beval\b")

# 3. source — `source` or the `.` builtin (leading or after a separator).
_CX_SOURCE = re.compile(r"\bsource\b|(?:^|[;&|(]\s*)\.\s+\S")

# 4. Heredoc (covers <<, <<-, and the <<< herestring — all composition).
_CX_HEREDOC = re.compile(r"<<")

# 5. Chaining — && / || / ;.
_CX_CHAIN = re.compile(r"&&|\|\||;")

# 6. Single pipes (|, not ||). Counted separately: the signal needs ≥2.
_CX_SINGLE_PIPE = re.compile(r"(?<!\|)\|(?!\|)")

# 7. xargs / find -exec.
_CX_XARGS = re.compile(r"\bxargs\b|\bfind\b[^;&|]*-exec\b")


def score_complexity(command: str) -> int:
    """Count distinct obfuscation/composition signals in *command* (0–7).

    Deterministic and offline. Each signal contributes at most +1. Raw pipe count
    is a weak contributor here only: it fires a single point when there are **two or
    more** single pipes — never a standalone trigger.
    """
    if not command:
        return 0
    score = 0
    if _CX_SUBST.search(command):
        score += 1
    if _CX_EVAL.search(command):
        score += 1
    if _CX_SOURCE.search(command):
        score += 1
    if _CX_HEREDOC.search(command):
        score += 1
    if _CX_CHAIN.search(command):
        score += 1
    if len(_CX_SINGLE_PIPE.findall(command)) >= 2:
        score += 1
    if _CX_XARGS.search(command):
        score += 1
    return score


# ── Evidence trigger protocol (duck-typed; no provider import) ────────


class _Trigger(Protocol):
    """Minimal shape of a Layer-3 trigger result (e.g. DeepAnalysisTrigger)."""

    should_analyze: bool
    url: str


# ── Producer ─────────────────────────────────────────────────────────


def build_command_facts(
    command: str,
    *,
    engine: AdvisoryEngine,
    resolve_category: Callable[[list[str]], str],
    check_trigger: Callable[[str], _Trigger],
    locale: str = "en",
) -> CommandFacts:
    """Run the single local analysis pass and return :class:`CommandFacts`.

    Reuses the local engine for severity + matched families (category resolved
    once here), the two deterministic scorers, and the injected Layer-3 trigger for
    ``evidence_gain``. ``resolve_category`` and ``check_trigger`` are injected so this
    module stays provider-free.
    """
    command = command.strip()
    if not command:
        return CommandFacts(
            severity=RiskLevel.SAFE,
            boundary_score=0,
            complexity_score=0,
            evidence_gain=False,
            evidence_url="",
            category="general",
        )

    result = engine.analyze(command, locale=locale)
    family_ids = [w.family for w in result.warnings]
    category = resolve_category(family_ids)

    trigger = check_trigger(command)

    return CommandFacts(
        severity=result.highest_risk,
        boundary_score=score_boundary(command),
        complexity_score=score_complexity(command),
        evidence_gain=bool(trigger.should_analyze),
        evidence_url=trigger.url if trigger.should_analyze else "",
        category=category,
    )
