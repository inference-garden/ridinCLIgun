# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for PTY process management

"""Tests for PtyProcess.

Regression anchor for the v0.3 finding FINDING-02 (audit T05): provider API
keys must never be inherited by the embedded shell or its children. These tests
spawn no real shell — `subprocess.Popen` is monkeypatched so we can inspect the
exact environment that *would* be handed to the child.
"""

from __future__ import annotations

import pytest

from ridincligun.shell import pty_process
from ridincligun.shell.pty_process import PtyProcess


@pytest.fixture
def captured_env(monkeypatch):
    """Monkeypatch Popen to capture the child env; return a mutable holder."""
    captured: dict[str, object] = {}

    class _FakePopen:
        def __init__(self, *args, **kwargs):
            captured["argv"] = args[0] if args else kwargs.get("args")
            captured["env"] = kwargs.get("env")
            self.pid = 4242

    monkeypatch.setattr(pty_process.subprocess, "Popen", _FakePopen)
    return captured


def test_provider_keys_stripped_from_child_env(captured_env, monkeypatch):
    """FINDING-02: *_API_KEY / *_SECRET_KEY must not reach the shell child env."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-leak")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-should-not-leak")
    monkeypatch.setenv("MISTRAL_API_KEY", "should-not-leak")
    monkeypatch.setenv("AWS_SECRET_KEY", "should-not-leak")

    proc = PtyProcess()
    try:
        proc.start()
    finally:
        proc.stop()

    env = captured_env["env"]
    assert env is not None
    leaked = [k for k in env if k.endswith("_API_KEY") or k.endswith("_SECRET_KEY")]
    assert leaked == [], f"provider credentials leaked into shell env: {leaked}"


def test_normal_env_and_term_survive(captured_env, monkeypatch):
    """Stripping must be surgical: ordinary env vars and TERM still pass through."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setenv("RIDIN_HARMLESS_VAR", "keep-me")

    proc = PtyProcess()
    try:
        proc.start()
    finally:
        proc.stop()

    env = captured_env["env"]
    assert env.get("RIDIN_HARMLESS_VAR") == "keep-me"
    assert env.get("TERM") == "xterm-256color"
    assert "PATH" in env  # inherited baseline env preserved
    assert "ANTHROPIC_API_KEY" not in env
