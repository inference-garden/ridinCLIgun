# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — ReDoS screening for bundled regexes

"""ReDoS regression tests for every regex the app runs on untrusted input.

Two parts:

1. **Screening harness** — every pattern (command catalog, secret detector,
   prompt sanitizer, deep-analysis triggers) must complete against a suite of
   pathological inputs within a hard per-search time budget. New patterns are
   picked up automatically and screened on every run, so a future
   catastrophic-backtracking regex fails CI instead of freezing the app.

2. **Behavior pins** — the patterns rewritten during ReDoS hardening must
   match/not-match exactly like the originals on realistic commands.

Context: before hardening, the env_secret detector took ~5s and the rm/chmod
catalog entries ~0.7s on a 20KB pathological input (clipboard paste runs
through detect_secrets, so input size is attacker-influenced). After: <5ms.
"""

import time

import pytest

import ridincligun.provider.deep_analysis as da
from ridincligun.advisory.catalog import load_catalog
from ridincligun.advisory.secret_detector import _SECRET_PATTERNS, detect_secrets
from ridincligun.provider.prompt import _SANITIZE_PATTERNS

# ── Screening harness ──────────────────────────────────────────────

_N = 20_000

# Long homogeneous runs maximize backtracking in vulnerable patterns.
_PATHOLOGICAL = [
    "A" * _N,  # word-char run
    "rm -" + "r" * _N,  # non-space run after dash
    "sudo rm -" + "r" * _N,
    "chmod " + "-" * _N + "777",  # many dash anchors
    "export " + "K" * _N + "=" + "v" * _N,  # huge var assignment
    ("SECRET" * 3500) + "=x",  # repeated keyword, no value
    "rm " + "- -" * 7000 + "rf",  # many dash tokens
    "curl " + "a" * _N + " | s",  # almost pipe-to-shell
    "://" + "a" * _N,  # almost credential-URL
    "Bearer " + "A" * _N,  # almost auth header
    "dd " + "o" * _N + "f=/dev/",  # almost dd-to-device
    "https://" + "a" * _N,  # long URL token
]

# Generous for slow CI runners; the vulnerable originals took 700–5200ms.
_BUDGET_MS = 100


def _all_patterns() -> list[tuple[str, "object"]]:
    """Collect every compiled regex the app applies to untrusted input."""
    pats = [
        (f"catalog:{p.family_id}:{p.regex.pattern[:30]}", p.regex) for p in load_catalog().patterns
    ]
    pats += [(f"secret:{kind}", rx) for rx, kind, _desc in _SECRET_PATTERNS]
    pats += [(f"sanitize:{rx.pattern[:30]}", rx) for rx, _repl in _SANITIZE_PATTERNS]
    pats += [
        ("deep:pipe_to_shell", da._PIPE_TO_SHELL),
        ("deep:download_and_exec", da._DOWNLOAD_AND_EXEC),
        ("deep:url", da._URL_PATTERN),
        ("deep:shell_pipe", da._SHELL_PIPE),
    ]
    return pats


@pytest.mark.parametrize("name,rx", _all_patterns(), ids=lambda v: v if isinstance(v, str) else "")
def test_pattern_completes_fast_on_pathological_input(name, rx):
    """No bundled regex may exhibit catastrophic backtracking."""
    for text in _PATHOLOGICAL:
        t0 = time.perf_counter()
        rx.search(text)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert elapsed_ms < _BUDGET_MS, (
            f"{name} took {elapsed_ms:.0f}ms (budget {_BUDGET_MS}ms) "
            f"on pathological input starting {text[:40]!r}"
        )


def test_detect_secrets_fast_on_large_paste():
    """The full detector pass stays fast on a clipboard-sized hostile input.

    detect_secrets runs on pasted clipboard text, so input size is
    attacker-influenced — the whole pass (all patterns) must stay bounded.
    """
    paste = ("export " + "K" * 50_000 + "=" + "v" * 50_000 + "\n") * 2
    t0 = time.perf_counter()
    detect_secrets(paste)
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, f"detect_secrets took {elapsed:.2f}s on a 200KB paste"


# ── Behavior pins for the ReDoS-hardened patterns ──────────────────
# These commands must classify exactly as they did before the rewrite.


@pytest.mark.parametrize(
    "command",
    [
        "export MY_SECRET=abcdefgh",
        "export AWS_SECRET_ACCESS_KEY='1234567890'",
        "API_TOKEN=xyzzy12345",
        "PASSWORD=hunter2hunter2",
        "export AUTHOR_KEY=12345678",  # keyword inside a longer name still hits
        "secret=12345678",  # lowercase (IGNORECASE)
    ],
)
def test_env_secret_still_detected(command):
    result = detect_secrets(command)
    assert any(m.kind == "env_secret" for m in result.matches), command


@pytest.mark.parametrize(
    "command",
    [
        "EDITOR=vim",  # no secret keyword
        "KEY=short",  # value under 8 chars
        "echo KEY",  # no assignment
    ],
)
def test_env_secret_negatives_unchanged(command):
    result = detect_secrets(command)
    assert not any(m.kind == "env_secret" for m in result.matches), command


def _danger_families(command: str) -> set[str]:
    """Family ids of danger-risk catalog patterns matching the command."""
    return {
        p.family_id
        for p in load_catalog().patterns
        if p.risk.value == "danger" and p.regex.search(command)
    }


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /tmp/x",
        "rm -fr x",
        "rm -rvf x",  # flag cluster with extra letter
        "rm -vrf --no-preserve-root /",
        "sudo rm -rf /",
        "chmod -R 777 /var",
        "chmod 777 -R x",
    ],
)
def test_catalog_danger_commands_still_match(command):
    assert _danger_families(command), command


@pytest.mark.parametrize(
    "command",
    [
        "rm file.txt",
        "rm -i x",
        "chmod 644 f",
        "chmod -R 644 d",
    ],
)
def test_catalog_safe_commands_still_clean(command):
    assert not _danger_families(command), command
