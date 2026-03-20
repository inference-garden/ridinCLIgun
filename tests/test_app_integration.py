"""Integration tests for RidinCLIgunApp.

Uses Textual's headless test mode — no real PTY or terminal needed.
Tests app lifecycle, widget composition, and state initialization.
"""

from __future__ import annotations

import pytest

from ridincligun.app import RidinCLIgunApp
from ridincligun.config import Config, ProviderSettings
from ridincligun.state import Phase
from ridincligun.ui.advisory_pane import AdvisoryPane
from ridincligun.ui.shell_pane import ShellPane
from ridincligun.ui.status_bar import StatusBar


def _test_config(tmp_path) -> Config:
    """Create a Config that won't touch the real config directory."""
    config_dir = tmp_path / "ridincligun"
    config_dir.mkdir()
    (config_dir / ".env").write_text("# empty\n")
    (config_dir / "config.toml").write_text(
        "[general]\nai_enabled_default = false\n"
    )
    return Config(
        config_dir=config_dir,
        ai_enabled_default=False,
        api_key="",
        provider=ProviderSettings(),
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
    """Ctrl+G, S toggles secret mode."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        assert not app.state.secret_mode
        # Leader key sequence: Ctrl+G then S
        await pilot.press("ctrl+g")
        await pilot.press("s")
        assert app.state.secret_mode
        # Toggle back
        await pilot.press("ctrl+g")
        await pilot.press("s")
        assert not app.state.secret_mode


@pytest.mark.asyncio
async def test_app_ai_toggle(app_config):
    """Ctrl+G, A toggles AI enabled state."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        assert not app.state.ai_enabled
        await pilot.press("ctrl+g")
        await pilot.press("a")
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
    """Secret mode toggle should use toast, not replace advisory pane."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        advisory = app.query_one("#advisory-pane", AdvisoryPane)
        # Set advisory content that should survive the toggle
        advisory.set_content([("  Important warning", "bold red")])
        before = advisory._raw_lines[:]

        # Toggle secret mode
        await pilot.press("ctrl+g")
        await pilot.press("s")
        assert app.state.secret_mode

        # Advisory pane content should be unchanged
        assert advisory._raw_lines == before


@pytest.mark.asyncio
async def test_ai_off_toggle_uses_toast(app_config):
    """AI toggle off should use toast, not replace advisory pane."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        # First enable AI
        app.state.ai_enabled = True

        advisory = app.query_one("#advisory-pane", AdvisoryPane)
        advisory.set_content([("  Important warning", "bold red")])
        before = advisory._raw_lines[:]

        # Toggle AI off
        await pilot.press("ctrl+g")
        await pilot.press("a")
        assert not app.state.ai_enabled

        # Advisory pane content should be unchanged
        assert advisory._raw_lines == before


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
        await pilot.press("ctrl+g")
        await pilot.press("h")
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
        await pilot.press("ctrl+g")
        await pilot.press("h")
        assert app._help_showing

        # Press Escape — should dismiss help
        await pilot.press("escape")
        assert not app._help_showing
