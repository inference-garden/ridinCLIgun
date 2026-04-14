# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for history browser modal

"""Integration-style tests for the history browser screen."""

from __future__ import annotations

import sys

import pytest

from ridincligun.app import RidinCLIgunApp
from ridincligun.config import Config, ProviderSettings
from ridincligun.history import HistoryEntry, ReviewHistory, now_iso
from ridincligun.ui.history_screen import HistoryBrowserScreen


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
    )


def _entry(**kwargs) -> HistoryEntry:
    defaults = {
        "timestamp": now_iso(),
        "command": "ls -la",
        "source": "ai",
        "risk": "safe",
        "summary": "Lists directory contents.",
        "explanation": "Read-only directory listing.",
        "suggestion": "",
        "provider": "OpenAI gpt-4o-mini",
        "tokens": 42,
    }
    defaults.update(kwargs)
    return HistoryEntry(**defaults)


@pytest.mark.asyncio
async def test_history_browser_selection_updates_detail(tmp_path):
    history = ReviewHistory(tmp_path / "history.jsonl")
    history.append(_entry(command="first command", summary="first summary"))
    history.append(_entry(command="second command", summary="second summary"))

    app = RidinCLIgunApp(config=_test_config(tmp_path))
    app._history = history

    async with app.run_test(size=(140, 45)) as pilot:
        await pilot.press("ctrl+g")
        await pilot.press("k")
        await pilot.pause()

        screen = app.screen_stack[-1]
        assert isinstance(screen, HistoryBrowserScreen)
        assert screen._selected_entry().command == "second command"
        list_text = screen._list_plaintext()
        assert "[AI" in list_text
        assert "second command" in list_text

        await pilot.press("down")
        await pilot.pause()

        assert screen._selected_entry().command == "first command"
        detail = screen._detail_plaintext()
        assert "first command" in detail


@pytest.mark.asyncio
async def test_history_browser_shows_legacy_partial_note(tmp_path):
    history_file = tmp_path / "history.jsonl"
    history_file.write_text(
        '{"ts":"2026-04-10T12:00:00+00:00","cmd":"legacy cmd",'
        '"src":"ai","risk":"warning","summary":"legacy summary"}\n'
    )
    history = ReviewHistory(history_file)

    app = RidinCLIgunApp(config=_test_config(tmp_path))
    app._history = history

    async with app.run_test(size=(140, 45)) as pilot:
        await pilot.press("ctrl+g")
        await pilot.press("k")
        await pilot.pause()

        screen = app.screen_stack[-1]
        assert isinstance(screen, HistoryBrowserScreen)
        detail = screen._detail_plaintext()
        assert "Full detail was not stored" in detail


@pytest.mark.asyncio
async def test_history_browser_empty_state(tmp_path):
    history = ReviewHistory(tmp_path / "history.jsonl")
    app = RidinCLIgunApp(config=_test_config(tmp_path))
    app._history = history

    async with app.run_test(size=(140, 45)) as pilot:
        await pilot.press("ctrl+g")
        await pilot.press("k")
        await pilot.pause()

        screen = app.screen_stack[-1]
        assert isinstance(screen, HistoryBrowserScreen)
        list_text = screen._list_plaintext()
        detail_text = screen._detail_plaintext()
        assert "No matching history entries." in list_text
        assert "No matching history entries." in detail_text


@pytest.mark.asyncio
async def test_history_browser_copies_suggestion(monkeypatch, tmp_path):
    history = ReviewHistory(tmp_path / "history.jsonl")
    history.append(_entry(suggestion="rm -i dangerous-file"))

    class _FakePyperclip:
        copied = ""

        @classmethod
        def copy(cls, text: str) -> None:
            cls.copied = text

    monkeypatch.setitem(sys.modules, "pyperclip", _FakePyperclip)

    app = RidinCLIgunApp(config=_test_config(tmp_path))
    app._history = history

    async with app.run_test(size=(140, 45)) as pilot:
        await pilot.press("ctrl+g")
        await pilot.press("k")
        await pilot.pause()

        await pilot.press("c")
        await pilot.pause()

        assert _FakePyperclip.copied == "rm -i dangerous-file"
