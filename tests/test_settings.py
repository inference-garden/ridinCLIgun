# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for settings screen

"""Tests for the settings screen and config persistence."""

from __future__ import annotations

import pytest

from ridincligun.app import RidinCLIgunApp
from ridincligun.config import Config, ProviderSettings
from ridincligun.shortcuts.bindings import LEADER_MAP, LeaderAction
from ridincligun.ui.settings_screen import SettingsScreen


def _test_config(tmp_path) -> Config:
    """Create a Config that won't touch the real config directory."""
    config_dir = tmp_path / "ridincligun"
    config_dir.mkdir()
    (config_dir / ".env").write_text("# empty\n")
    (config_dir / "config.toml").write_text(
        "[general]\n"
        "ai_enabled_default = false\n"
        "\n"
        "[provider]\n"
        'kind = "anthropic"\n'
        'model = "claude-sonnet-4-20250514"\n'
        "timeout_seconds = 10.0\n"
        "max_tokens = 1024\n"
        "\n"
        "[privacy]\n"
        "show_redaction_preview = true\n"
        "\n"
        "[ui]\n"
        "split_ratio = [3, 2]\n"
    )
    return Config(
        config_dir=config_dir,
        ai_enabled_default=False,
        api_key="",
        provider=ProviderSettings(),
    )


@pytest.fixture
def settings_config(tmp_path):
    return _test_config(tmp_path)


# ── Leader key binding ───────────────────────────────────────────


def test_settings_leader_key_registered():
    """Ctrl+G, G should be mapped to SETTINGS action."""
    assert LEADER_MAP.get("g") == LeaderAction.SETTINGS


# ── Settings screen unit tests ──────────────────────────────────


def test_settings_screen_builds_items(settings_config):
    """Settings screen should have toggle items for key settings."""
    screen = SettingsScreen(settings_config)
    assert len(screen._items) >= 2
    toggle_items = [i for i in screen._items if i["type"] == "toggle"]
    assert len(toggle_items) >= 2
    keys = {i["key"] for i in toggle_items}
    assert "ai_enabled_default" in keys
    assert "show_redaction_preview" in keys


def test_settings_toggle_updates_config(settings_config):
    """Toggling a setting should update the config object."""
    screen = SettingsScreen(settings_config)
    assert not settings_config.ai_enabled_default

    # Find the ai_enabled_default item index
    ai_idx = next(i for i, item in enumerate(screen._items) if item["key"] == "ai_enabled_default")
    screen._cursor = ai_idx
    screen._toggle_current()

    assert settings_config.ai_enabled_default


def test_settings_toggle_persists_to_file(settings_config):
    """Toggling a setting should write to config.toml."""
    screen = SettingsScreen(settings_config)

    # Find and toggle ai_enabled_default
    ai_idx = next(i for i, item in enumerate(screen._items) if item["key"] == "ai_enabled_default")
    screen._cursor = ai_idx
    screen._toggle_current()

    # Read config.toml and check
    text = settings_config.config_file.read_text()
    assert "ai_enabled_default = true" in text


def test_settings_toggle_redaction_preview(settings_config):
    """Toggling redaction preview should update config and file."""
    screen = SettingsScreen(settings_config)
    assert settings_config.show_redaction_preview

    # Find the redaction preview toggle
    for i, item in enumerate(screen._items):
        if item["key"] == "show_redaction_preview":
            screen._cursor = i
            break

    screen._toggle_current()
    assert not settings_config.show_redaction_preview

    text = settings_config.config_file.read_text()
    assert "show_redaction_preview = false" in text


def test_settings_provider_model_are_action_items(settings_config):
    """Provider and model items should be 'action' type (navigable, Enter opens model selector)."""
    screen = SettingsScreen(settings_config)
    action_items = [i for i in screen._items if i["type"] == "action"]
    keys = {i["key"] for i in action_items}
    assert "provider_kind" in keys
    assert "model" in keys


def test_settings_action_items_have_model_select_action(settings_config):
    """Action items for provider/model must carry action='model_select'."""
    screen = SettingsScreen(settings_config)
    for item in screen._items:
        if item["key"] in ("provider_kind", "model"):
            assert item["action"] == "model_select"


def test_settings_action_items_not_toggleable(settings_config):
    """Action items (provider, model) should not respond to _toggle_current."""
    screen = SettingsScreen(settings_config)
    for i, item in enumerate(screen._items):
        if item["type"] == "action":
            screen._cursor = i
            break

    before = screen._items[screen._cursor]["value"]
    screen._toggle_current()  # should be a no-op for non-toggle items
    assert screen._items[screen._cursor]["value"] == before


# ── Integration tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_settings_opens_via_leader_key(settings_config):
    """Ctrl+G, G should open the settings screen."""
    app = RidinCLIgunApp(config=settings_config)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("ctrl+g")
        await pilot.press("g")
        await pilot.pause()

        # Settings screen should be pushed
        assert len(app.screen_stack) > 1
        assert isinstance(app.screen_stack[-1], SettingsScreen)


@pytest.mark.asyncio
async def test_settings_closes_on_escape(settings_config):
    """Escape should close the settings screen."""
    app = RidinCLIgunApp(config=settings_config)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("ctrl+g")
        await pilot.press("g")
        await pilot.pause()

        assert len(app.screen_stack) > 1

        await pilot.press("escape")
        await pilot.pause()

        # Should be back to main screen
        assert len(app.screen_stack) == 1


# ── Provider / API key management ────────────────────────────────


def test_settings_has_provider_items(settings_config):
    """Settings screen should include provider items."""
    screen = SettingsScreen(settings_config)
    provider_items = [i for i in screen._items if i["type"] == "provider"]
    assert len(provider_items) == 3  # mistral, anthropic, openai
    names = {i["provider_name"] for i in provider_items}
    assert names == {"mistral", "anthropic", "openai"}


def test_provider_shows_not_configured(settings_config):
    """Provider with no key should show 'not configured'."""
    screen = SettingsScreen(settings_config)
    for item in screen._items:
        if item["type"] == "provider":
            assert "not configured" in item["label"]


def test_save_api_key_writes_to_env(settings_config):
    """Saving an API key should write it to .env file."""
    screen = SettingsScreen(settings_config)
    screen._save_api_key("MISTRAL_API_KEY", "test-key-12345")

    text = settings_config.env_file.read_text()
    assert "MISTRAL_API_KEY=test-key-12345" in text


def test_save_api_key_updates_existing(settings_config):
    """Saving a key that already exists should update it."""
    # Pre-populate .env
    settings_config.env_file.write_text(
        "# credentials\n"
        "MISTRAL_API_KEY=old-key\n"
    )

    screen = SettingsScreen(settings_config)
    screen._save_api_key("MISTRAL_API_KEY", "new-key-67890")

    text = settings_config.env_file.read_text()
    assert "MISTRAL_API_KEY=new-key-67890" in text
    assert "old-key" not in text


def test_save_api_key_uncomments_existing(settings_config):
    """Saving a key that's commented out should uncomment and set it."""
    # .env has commented key (default template)
    settings_config.env_file.write_text(
        "# ridinCLIgun API credentials\n"
        "# ANTHROPIC_API_KEY=\n"
    )

    screen = SettingsScreen(settings_config)
    screen._save_api_key("ANTHROPIC_API_KEY", "sk-ant-test")

    text = settings_config.env_file.read_text()
    assert "ANTHROPIC_API_KEY=sk-ant-test" in text


def test_save_api_key_sets_permissions(settings_config):
    """API key file should have restrictive permissions (0600)."""
    import stat

    screen = SettingsScreen(settings_config)
    screen._save_api_key("OPENAI_API_KEY", "sk-test-key")

    mode = settings_config.env_file.stat().st_mode
    # Owner read/write only
    assert mode & stat.S_IRUSR
    assert mode & stat.S_IWUSR
    # No group/other access
    assert not (mode & stat.S_IRGRP)
    assert not (mode & stat.S_IROTH)


def test_provider_shows_configured_after_save(settings_config):
    """After saving a key, provider should show as configured."""
    screen = SettingsScreen(settings_config)
    screen._save_api_key("MISTRAL_API_KEY", "test-key-XcF9")

    # Rebuild items to reflect new state
    screen._env_keys = screen._env_keys.__class__(
        {**screen._env_keys, "MISTRAL_API_KEY": "test-key-XcF9"}
    )
    screen._items = screen._build_items()

    for item in screen._items:
        if item["type"] == "provider" and item["provider_name"] == "mistral":
            assert "XcF9" in item["label"]  # last 4 chars shown
            assert "configured" in item["label"]
            break
    else:
        pytest.fail("Mistral provider item not found")
