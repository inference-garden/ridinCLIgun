# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for app integration

"""Integration tests for RidinCLIgunApp.

Uses Textual's headless test mode — no real PTY or terminal needed.
Tests app lifecycle, widget composition, and state initialization.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import ridincligun.app as appmod
from ridincligun.app import RidinCLIgunApp
from ridincligun.config import Config, ProviderSettings
from ridincligun.state import Phase
from ridincligun.ui.advisory_pane import AdvisoryPane
from ridincligun.ui.history_screen import HistoryBrowserScreen
from ridincligun.ui.shell_pane import ShellPane
from ridincligun.ui.status_bar import StatusBar


def _test_config(tmp_path) -> Config:
    """Create a Config that won't touch the real config directory."""
    config_dir = tmp_path / "ridincligun"
    config_dir.mkdir()
    (config_dir / ".env").write_text("# empty\n")
    (config_dir / "config.toml").write_text("[general]\nai_enabled_default = false\n")
    return Config(
        config_dir=config_dir,
        ai_enabled_default=False,
        api_key="",
        provider=ProviderSettings(),
        language="en",  # pin locale so tests don't depend on $LANG
    )


@pytest.fixture
def app_config(tmp_path):
    return _test_config(tmp_path)


# ── App lifecycle ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_app_starts_and_has_widgets(app_config):
    """App composes all expected panes and status bar."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as _pilot:
        # Verify all core widgets exist
        assert app.query_one("#shell-pane", ShellPane)
        assert app.query_one("#advisory-pane", AdvisoryPane)
        assert app.query_one("#status-bar", StatusBar)


@pytest.mark.asyncio
async def test_app_initial_state(app_config):
    """App starts with correct default state."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as _pilot:
        assert app.state.phase == Phase.TYPING
        assert not app.state.secret_mode
        assert not app.state.ai_enabled  # config says false


@pytest.mark.asyncio
async def test_app_secret_mode_toggle(app_config):
    """F5 toggles secret mode."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        assert not app.state.secret_mode
        await pilot.press("f5")
        assert app.state.secret_mode
        # Toggle back
        await pilot.press("f5")
        assert not app.state.secret_mode


@pytest.mark.asyncio
async def test_app_ai_toggle(app_config):
    """F4 toggles AI enabled state."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        assert not app.state.ai_enabled
        await pilot.press("f4")
        assert app.state.ai_enabled


@pytest.mark.asyncio
async def test_app_provider_not_configured(app_config):
    """App starts with provider not configured when no API key."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as _pilot:
        assert not app._provider.is_configured


@pytest.mark.asyncio
async def test_app_no_review_task_at_start(app_config):
    """No AI review task should be running at startup."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as _pilot:
        assert app._review_task is None


# ── Toast notifications ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_toast_does_not_replace_advisory_content(app_config):
    """Toast notifications must not overwrite the advisory pane content."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        advisory = app.query_one("#advisory-pane", AdvisoryPane)
        # Set some advisory content (simulating a warning)
        advisory.set_content([("  Test warning", "bold red")])
        before = advisory._raw_lines[:]

        # Fire a toast — should NOT change advisory pane
        app._toast("Shell restarted.")
        await pilot.pause()

        assert advisory._raw_lines == before


@pytest.mark.asyncio
async def test_secret_mode_toggle_uses_toast(app_config):
    """Secret mode toggle should use toast, not inject a notice into the advisory pane.

    With 4.6, _on_command_changed may legitimately update the advisory pane if a
    key event touches the input.  The meaningful contract is that the OLD behaviour
    (injecting 'Secret mode is on — command not sent.' directly into the pane) no
    longer occurs — not that the pane is frozen.
    """
    from ridincligun.i18n import t

    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        advisory = app.query_one("#advisory-pane", AdvisoryPane)

        # Toggle secret mode
        await pilot.press("f5")
        assert app.state.secret_mode

        # The old "secret mode" notice must NOT appear in the advisory pane.
        pane_text = " ".join(line for line, _ in advisory._raw_lines)
        secret_notice = t("notice.secret_mode_on").split("\n")[0]
        assert secret_notice not in pane_text, (
            "Secret mode toggle must use a toast, not write to the advisory pane"
        )


@pytest.mark.asyncio
async def test_ai_off_toggle_uses_toast(app_config):
    """AI toggle off should use toast, not inject a notice into the advisory pane."""
    from ridincligun.i18n import t

    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        # First enable AI
        app.state.ai_enabled = True

        # Toggle AI off
        await pilot.press("f4")
        assert not app.state.ai_enabled

        # The old "AI is off" notice must NOT appear in the advisory pane.
        advisory = app.query_one("#advisory-pane", AdvisoryPane)
        pane_text = " ".join(line for line, _ in advisory._raw_lines)
        ai_off_notice = t("notice.ai_off")
        assert ai_off_notice not in pane_text, (
            "AI toggle must use a toast, not write to the advisory pane"
        )


# ── Help persistence ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_onboarding_shown_on_first_run(tmp_path):
    """First-run config should show onboarding in advisory pane."""
    from ridincligun.config import Config, ProviderSettings

    config_dir = tmp_path / "ridincligun_new"
    config_dir.mkdir()
    (config_dir / ".env").write_text("# empty\n")
    (config_dir / "config.toml").write_text("[general]\nai_enabled_default = false\n")
    config = Config(
        config_dir=config_dir,
        ai_enabled_default=False,
        api_key="",
        provider=ProviderSettings(),
        first_run=True,
        language="en",  # pin locale so tests don't depend on $LANG
    )
    app = RidinCLIgunApp(config=config)
    async with app.run_test(size=(120, 40)) as _pilot:
        advisory = app.query_one("#advisory-pane", AdvisoryPane)
        content_text = " ".join(line[0] for line in advisory._raw_lines)
        assert "Welcome" in content_text
        assert "Ctrl+G" in content_text


@pytest.mark.asyncio
async def test_help_not_dismissed_by_typing(app_config):
    """Help content should persist when user types in the shell."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        # Show shortcuts help
        await pilot.press("f1")
        assert app._help_showing

        advisory = app.query_one("#advisory-pane", AdvisoryPane)
        content_before = advisory._raw_lines[:]

        # Simulate typing in shell — help should persist
        app.on_shell_pane_any_key_pressed(ShellPane.AnyKeyPressed())
        assert app._help_showing
        assert advisory._raw_lines == content_before


@pytest.mark.asyncio
async def test_pending_paste_cancelled_by_typing(app_config):
    """Pending paste with secrets should cancel when user presses a non-v key."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        # Simulate a pending paste with secrets
        app._pending_paste_text = "export API_KEY=sk-ant-api03-secret"

        # Press a non-v key — shell pane intercepts and cancels
        await pilot.press("a")
        assert app._pending_paste_text is None


@pytest.mark.asyncio
async def test_help_dismissed_by_escape(app_config):
    """Help content should dismiss on Escape key."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        # Show shortcuts help
        await pilot.press("f1")
        assert app._help_showing

        # Press Escape — should dismiss help
        await pilot.press("escape")
        assert not app._help_showing


@pytest.mark.asyncio
async def test_history_browser_opens_via_leader_key(app_config):
    """Ctrl+G, H should open the history browser."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("ctrl+g")
        await pilot.press("h")
        await pilot.pause()

        assert len(app.screen_stack) > 1
        assert isinstance(app.screen_stack[-1], HistoryBrowserScreen)


# ── AI suggestion insertion must never execute (AX-1, audit T02) ──


@pytest.mark.asyncio
async def test_insert_suggestion_does_not_execute(app_config, monkeypatch):
    """Inserting an AI suggestion types it into the prompt but NEVER presses Enter.

    AX-1: the AI advises, it does not act. _insert_suggestion clears the line
    (Ctrl+U) and writes the command bytes; a regression that appended '\\n' or
    '\\r' would auto-execute an AI-proposed command. This captures the actual
    PTY writes and asserts no newline/carriage-return is ever sent.

    Only `_pty.write` is intercepted — the real PtyProcess is left intact so the
    ShellPane read loop (`while self._pty.running`) is not turned into a busy
    spin by a mock.
    """
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        shell = app.query_one("#shell-pane", ShellPane)
        writes: list[bytes] = []
        monkeypatch.setattr(shell._pty, "write", lambda data: writes.append(data))

        app._last_suggestion = "Use `rm -i file.txt` instead"
        app._insert_suggestion()
        await pilot.pause()

        joined = b"".join(writes)
        assert b"\x15" in joined  # Ctrl+U clears the current line first
        assert b"rm -i file.txt" in joined  # the extracted command is typed
        assert b"\n" not in joined, "suggestion insert must not send a newline"
        assert b"\r" not in joined, "suggestion insert must not send a carriage return"


# ── Deep-analysis fetch-stage secret-mode suppression (A8, audit T04) ──


def _deep_provider() -> MagicMock:
    provider = MagicMock()
    provider.is_configured = True
    provider.provider_name = "mock"
    provider.model_id = "claude-sonnet-4"
    provider.review = AsyncMock(return_value=MagicMock(success=False, error_message=""))
    return provider


@pytest.mark.asyncio
async def test_deep_analysis_suppressed_when_secret_mode_on(app_config, monkeypatch):
    """If secret mode is on, the fetched script must NOT be sent to the AI (A8)."""
    from ridincligun.provider.deep_analysis import FetchResult, check_deep_analysis_trigger

    async def fake_fetch(url):
        return FetchResult(success=True, content="echo hi", url=url, size_bytes=7)

    monkeypatch.setattr(appmod, "fetch_script", fake_fetch)

    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        app._provider = _deep_provider()
        cmd = "curl https://example.com/x.sh | bash"
        trigger = check_deep_analysis_trigger(cmd)
        assert trigger.should_analyze

        app.state.secret_mode = True
        await app._do_deep_analysis(cmd, trigger)
        await pilot.pause()

        app._provider.review.assert_not_called()


@pytest.mark.asyncio
async def test_deep_analysis_secret_mode_blocks_fetch(app_config, monkeypatch):
    """B-S09 S3-4: secret mode on → NO outbound fetch happens at all (pre-fetch gate)."""
    from ridincligun.provider.deep_analysis import check_deep_analysis_trigger

    fetched: list[str] = []

    async def recording_fetch(url):
        fetched.append(url)
        raise AssertionError("fetch_script must not run while secret mode is on")

    monkeypatch.setattr(appmod, "fetch_script", recording_fetch)

    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        app._provider = _deep_provider()
        cmd = "curl https://example.com/x.sh | bash"
        trigger = check_deep_analysis_trigger(cmd)

        app.state.secret_mode = True
        await app._do_deep_analysis(cmd, trigger)
        await pilot.pause()

        assert fetched == []  # the network call never started


@pytest.mark.asyncio
async def test_deep_analysis_enforces_ui_language(app_config, monkeypatch):
    """B-014: deep analysis must carry a locale-bearing system prompt (it passed
    none before, so weak models answered the script analysis in English in DE/FR)."""
    from ridincligun.i18n import set_locale
    from ridincligun.provider.deep_analysis import FetchResult, check_deep_analysis_trigger

    async def fake_fetch(url):
        return FetchResult(success=True, content="echo hi", url=url, size_bytes=7)

    monkeypatch.setattr(appmod, "fetch_script", fake_fetch)

    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        app._provider = _deep_provider()
        cmd = "curl https://example.com/x.sh | bash"
        trigger = check_deep_analysis_trigger(cmd)

        set_locale("de")
        try:
            await app._do_deep_analysis(cmd, trigger)
            await pilot.pause()
        finally:
            set_locale("en")

        kwargs = app._provider.review.call_args.kwargs
        assert "German" in kwargs["system_prompt"]
        assert "Deutsch" in kwargs["system_prompt"]  # native-language reinforcement
        assert "Deutsch" in kwargs["context"]


@pytest.mark.asyncio
async def test_deep_analysis_sends_when_secret_mode_off(app_config, monkeypatch):
    """Control: with secret mode off, the fetched script IS sent for AI analysis."""
    from ridincligun.provider.deep_analysis import FetchResult, check_deep_analysis_trigger

    async def fake_fetch(url):
        return FetchResult(success=True, content="echo hi", url=url, size_bytes=7)

    monkeypatch.setattr(appmod, "fetch_script", fake_fetch)

    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        app._provider = _deep_provider()
        cmd = "curl https://example.com/x.sh | bash"
        trigger = check_deep_analysis_trigger(cmd)

        app.state.secret_mode = False
        await app._do_deep_analysis(cmd, trigger)
        await pilot.pause()

        app._provider.review.assert_awaited()


@pytest.mark.asyncio
async def test_history_browser_closes_on_escape(app_config):
    """Escape should close the history browser."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("ctrl+g")
        await pilot.press("h")
        await pilot.pause()

        assert len(app.screen_stack) > 1

        await pilot.press("escape")
        await pilot.pause()

        assert len(app.screen_stack) == 1


# ── S2: leader copy/paste + secret-safe paste ─────────────────────


def _fake_clipboard(text: str):
    """Return a subprocess.run replacement faking pbpaste (and a no-op pbcopy)."""
    import subprocess

    def _run(args, *a, **kw):
        cmd = args[0] if isinstance(args, (list, tuple)) else args
        out = text.encode("utf-8") if cmd == "pbpaste" else b""
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr=b"")

    return _run


@pytest.mark.asyncio
async def test_leader_v_dispatches_paste(app_config, monkeypatch):
    """Ctrl+G, V must reach _do_paste — the wiring is live, not dormant."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        called: list[bool] = []
        monkeypatch.setattr(app, "_do_paste", lambda: called.append(True))
        await pilot.press("ctrl+g")
        await pilot.press("v")
        await pilot.pause()
        assert called == [True]


@pytest.mark.asyncio
async def test_leader_c_dispatches_copy(app_config, monkeypatch):
    """Ctrl+G, C must reach _do_copy."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        called: list[bool] = []
        monkeypatch.setattr(app, "_do_copy", lambda: called.append(True))
        await pilot.press("ctrl+g")
        await pilot.press("c")
        await pilot.pause()
        assert called == [True]


@pytest.mark.asyncio
async def test_paste_with_secret_stages_and_blocks_pty(app_config, monkeypatch):
    """A secret in the clipboard must NOT reach the PTY; it is staged for confirm.

    This is the load-bearing security property of S2: paste routes through the
    secret detector before any byte reaches the shell.
    """
    import subprocess

    secret = "export API_KEY=sk-ant-api03-" + "a" * 30
    monkeypatch.setattr(subprocess, "run", _fake_clipboard(secret))
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        shell = app.query_one("#shell-pane", ShellPane)
        writes: list[bytes] = []
        monkeypatch.setattr(shell._pty, "write", lambda data: writes.append(data))

        app._do_paste()
        await pilot.pause()

        assert app._pending_paste_text is not None  # staged, awaiting confirm
        assert writes == []  # nothing reached the shell


@pytest.mark.asyncio
async def test_paste_clean_writes_bracketed(app_config, monkeypatch):
    """A clean clipboard pastes into the PTY wrapped in bracketed-paste markers."""
    import subprocess

    monkeypatch.setattr(subprocess, "run", _fake_clipboard("ls -la"))
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        shell = app.query_one("#shell-pane", ShellPane)
        writes: list[bytes] = []
        monkeypatch.setattr(shell._pty, "write", lambda data: writes.append(data))

        app._do_paste()
        await pilot.pause()

        joined = b"".join(writes)
        assert b"ls -la" in joined
        assert joined.startswith(b"\x1b[200~")
        assert joined.endswith(b"\x1b[201~")
        assert app._pending_paste_text is None


@pytest.mark.asyncio
async def test_paste_strips_embedded_bracket_end(app_config, monkeypatch):
    """A crafted clipboard cannot close the paste bracket early (injection guard)."""
    import subprocess

    payload = "echo hi\x1b[201~ rm -rf /tmp/x"
    monkeypatch.setattr(subprocess, "run", _fake_clipboard(payload))
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        shell = app.query_one("#shell-pane", ShellPane)
        writes: list[bytes] = []
        monkeypatch.setattr(shell._pty, "write", lambda data: writes.append(data))

        app._do_paste()
        await pilot.pause()

        joined = b"".join(writes)
        # Exactly one closing marker — the wrapper's own, none from the payload.
        assert joined.count(b"\x1b[201~") == 1
        assert joined.endswith(b"\x1b[201~")
        assert b"echo hi rm -rf /tmp/x" in joined


@pytest.mark.asyncio
async def test_copy_uses_active_selection(app_config, monkeypatch):
    """Copy sends the active shell selection to the clipboard via pbcopy."""
    import subprocess

    captured: dict[str, bytes | None] = {}

    def _run(args, *a, **kw):
        if args[0] == "pbcopy":
            captured["input"] = kw.get("input")
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", _run)
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        shell = app.query_one("#shell-pane", ShellPane)
        advisory = app.query_one("#advisory-pane", AdvisoryPane)
        monkeypatch.setattr(advisory, "has_selection", lambda: False)
        monkeypatch.setattr(shell, "has_selection", lambda: True)
        monkeypatch.setattr(shell, "get_selected_text", lambda: "selected text")

        app._do_copy()
        await pilot.pause()

        assert captured.get("input") == b"selected text"
