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
    async with app.run_test(size=(120, 40)) as pilot:
        # Verify all core widgets exist
        assert app.query_one("#shell-pane", ShellPane)
        assert app.query_one("#advisory-pane", AdvisoryPane)
        assert app.query_one("#status-bar", StatusBar)


@pytest.mark.asyncio
async def test_app_initial_state(app_config):
    """App starts with correct default state."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
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
    async with app.run_test(size=(120, 40)) as pilot:
        assert not app._provider.is_configured


@pytest.mark.asyncio
async def test_app_no_review_task_at_start(app_config):
    """No AI review task should be running at startup."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        assert app._review_task is None
