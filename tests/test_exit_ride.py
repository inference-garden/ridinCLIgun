# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for the `exit ride` clean-exit verb (S4-3)

"""`exit ride` is the app-specific quit verb: typed at a shell prompt and
intercepted before the line reaches the PTY.  It must match exactly (no
substring), run the app's quit path, and never forward a carriage return.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import ridincligun.ui.shell_pane as shellmod
from ridincligun.config import Config, ProviderSettings
from ridincligun.ui.shell_pane import ShellPane, _is_exit_ride

# ── Pure matcher rules (the security-relevant core) ───────────────


@pytest.mark.parametrize(
    "command",
    ["exit ride", "Exit Ride", "EXIT RIDE", "  exit ride  ", "exit   ride", "exit\tride"],
)
def test_is_exit_ride_matches(command):
    assert _is_exit_ride(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "exit ride && rm -rf /",  # MUST NOT trigger — exact match only
        "exit",  # bare exit is the shell's own builtin
        "exit rides",
        "ride",
        "echo exit ride",
        '"exit ride"',  # quoting reaches the shell as one argument
        "",
    ],
)
def test_is_exit_ride_rejects(command):
    assert _is_exit_ride(command) is False


# ── Wiring: Enter on `exit ride` quits, never forwards \r ──────────


def _test_config(tmp_path) -> Config:
    config_dir = tmp_path / "ridincligun"
    config_dir.mkdir()
    (config_dir / ".env").write_text("# empty\n")
    (config_dir / "config.toml").write_text("[general]\nai_enabled_default = false\n")
    return Config(
        config_dir=config_dir,
        ai_enabled_default=False,
        api_key="",
        provider=ProviderSettings(),
        language="en",
    )


@pytest.mark.asyncio
async def test_exit_ride_quits_without_carriage_return(tmp_path, monkeypatch):
    from ridincligun.app import RidinCLIgunApp

    # The current shell input line is exactly `exit ride`.
    monkeypatch.setattr(shellmod, "extract_current_command", lambda screen: "exit ride")
    app = RidinCLIgunApp(config=_test_config(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        shell = app.query_one("#shell-pane", ShellPane)
        writes: list[bytes] = []
        monkeypatch.setattr(shell._pty, "write", lambda data: writes.append(data))
        quit_mock = MagicMock()
        monkeypatch.setattr(app, "action_quit", quit_mock)

        await pilot.press("enter")
        await pilot.pause()

        quit_mock.assert_called_once()
        joined = b"".join(writes)
        assert b"\x15" in joined, "input line must be cleared with Ctrl+U"
        assert b"\r" not in joined, "`exit ride` must NOT forward a carriage return"


@pytest.mark.asyncio
async def test_normal_command_still_forwards_enter(tmp_path, monkeypatch):
    """A non-`exit ride` line is untouched: Enter forwards \\r, no quit."""
    from ridincligun.app import RidinCLIgunApp

    monkeypatch.setattr(shellmod, "extract_current_command", lambda screen: "echo hi")
    app = RidinCLIgunApp(config=_test_config(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        shell = app.query_one("#shell-pane", ShellPane)
        writes: list[bytes] = []
        monkeypatch.setattr(shell._pty, "write", lambda data: writes.append(data))
        quit_mock = MagicMock()
        monkeypatch.setattr(app, "action_quit", quit_mock)

        await pilot.press("enter")
        await pilot.pause()

        quit_mock.assert_not_called()
        assert b"\r" in b"".join(writes)
