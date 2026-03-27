# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Settings screen

"""Settings screen — modal overlay for configuration.

Opens via Ctrl+G, G. Sections: AI, Privacy, Available API-Keys.
Toggles read current values from config, write changes on toggle.
Provider items allow entering API keys via masked input.
"""

from __future__ import annotations

import os
import re as _re
import stat
from pathlib import Path

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from ridincligun.config import Config

# Provider → environment variable name mapping
# Available review modes — order determines cycle direction
_REVIEW_MODES: list[tuple[str, str]] = [
    ("default", "Default"),
    ("explorer", "Explorer mode (for Kids)"),
]

# Provider → environment variable name mapping
_PROVIDER_KEYS: list[tuple[str, str]] = [
    ("mistral", "MISTRAL_API_KEY"),
    ("anthropic", "ANTHROPIC_API_KEY"),
    ("openai", "OPENAI_API_KEY"),
]


def _read_env_keys(env_file: Path) -> dict[str, str]:
    """Read API keys from .env file without loading into os.environ."""
    keys: dict[str, str] = {}
    if not env_file.exists():
        return keys
    try:
        from dotenv import dotenv_values
        vals = dotenv_values(env_file)
        for _, env_var in _PROVIDER_KEYS:
            v = vals.get(env_var, "") or ""
            if v:
                keys[env_var] = v
    except Exception:  # nosec B110
        pass
    return keys


def _mask_key(key: str) -> str:
    """Mask an API key, showing only last 4 chars."""
    if len(key) <= 4:
        return "●" * len(key)
    return "●" * (len(key) - 4) + key[-4:]


class ApiKeyInputScreen(ModalScreen[str | None]):
    """Small modal for entering an API key (masked)."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    CSS = """
    ApiKeyInputScreen {
        align: center middle;
    }

    #key-input-container {
        width: 55;
        height: auto;
        background: #1a1a2e;
        border: tall #44475a;
        padding: 1 2;
    }

    .key-input-title {
        text-align: center;
        text-style: bold;
        color: #bd93f9;
        margin-bottom: 1;
    }

    .key-input-hint {
        color: #6272a4;
        text-align: center;
        margin-top: 1;
    }
    """

    def __init__(self, provider_name: str, env_var: str) -> None:
        super().__init__()
        self._provider_name = provider_name
        self._env_var = env_var

    def compose(self) -> ComposeResult:
        with Vertical(id="key-input-container"):
            yield Label(
                f"Enter API key for {self._provider_name}",
                classes="key-input-title",
            )
            yield Label(f"  {self._env_var}", classes="key-input-hint")
            yield Input(
                placeholder="Paste your API key here...",
                password=True,
                id="key-input",
            )
            yield Label(
                "Enter to save  Escape to cancel",
                classes="key-input-hint",
            )

    def on_mount(self) -> None:
        self.query_one("#key-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Save the entered key."""
        key = event.value.strip()
        if key:
            self.dismiss(key)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SettingsScreen(ModalScreen[None]):
    """Modal settings overlay with section-based toggles."""

    BINDINGS = [
        ("escape", "dismiss_settings", "Close settings"),
    ]

    CSS = """
    SettingsScreen {
        align: center middle;
    }

    #settings-container {
        width: 55;
        max-height: 35;
        background: #1a1a2e;
        border: tall #44475a;
        padding: 1 2;
    }

    .settings-title {
        text-align: center;
        text-style: bold;
        color: #bd93f9;
        margin-bottom: 1;
    }

    .settings-hint {
        color: #6272a4;
        text-align: center;
        margin-top: 1;
    }
    """

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._cursor = 0
        self._env_keys = _read_env_keys(config.env_file)
        self._items: list[dict] = self._build_items()

    def _mode_label(self) -> str:
        """Return the display label for the current review mode."""
        for key, label in _REVIEW_MODES:
            if key == self._config.review_mode:
                return f"Review mode: {label}"
        return f"Review mode: {self._config.review_mode}"

    def _build_items(self) -> list[dict]:
        """Build the settings item list from current config state."""
        items: list[dict] = [
            {
                "section": "AI",
                "key": "ai_enabled_default",
                "label": "AI enabled at startup",
                "value": self._config.ai_enabled_default,
                "type": "toggle",
            },
            {
                "section": "AI",
                "key": "provider_kind",
                "label": f"Provider: {self._config.provider.kind}",
                "value": self._config.provider.kind,
                "type": "info",
            },
            {
                "section": "AI",
                "key": "model",
                "label": f"Model: {self._config.provider.model}",
                "value": self._config.provider.model,
                "type": "info",
            },
            {
                "section": "AI",
                "key": "review_mode",
                "label": self._mode_label(),
                "value": self._config.review_mode,
                "type": "cycle",
            },
            {
                "section": "Privacy",
                "key": "show_redaction_preview",
                "label": "Show redaction preview before AI review",
                "value": self._config.show_redaction_preview,
                "type": "toggle",
            },
            {
                "section": "Privacy",
                "key": "clipboard_safety",
                "label": "Warn before pasting secrets",
                "value": self._config.clipboard_safety,
                "type": "toggle",
            },
        ]

        # Provider API key items
        for provider_name, env_var in _PROVIDER_KEYS:
            key_val = self._env_keys.get(env_var, "")
            if key_val:
                status = f"configured (...{key_val[-4:]})"
            else:
                # Also check os.environ as fallback
                env_val = os.environ.get(env_var, "")
                if env_val:
                    status = f"from env (...{env_val[-4:]})"
                else:
                    status = "not configured"

            items.append({
                "section": "Available API-Keys",
                "key": env_var,
                "label": f"{provider_name}: {status}",
                "value": env_var,
                "type": "provider",
                "provider_name": provider_name,
            })

        return items

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-container"):
            yield Label("Settings", classes="settings-title")
            yield Static(id="settings-body")
            yield Label(
                "↑↓ navigate  Space toggle/cycle  Enter edit key\n\n  Press ESC to exit",
                classes="settings-hint",
            )

    def on_mount(self) -> None:
        self._render_items()

    def _render_items(self) -> None:
        """Render settings items into the body widget."""
        body = self.query_one("#settings-body", Static)
        lines: list[str] = []
        last_section = ""

        for i, item in enumerate(self._items):
            if item["section"] != last_section:
                last_section = item["section"]
                lines.append(f"\n  [{last_section}]")

            prefix = " ▸ " if i == self._cursor else "   "

            if item["type"] == "toggle":
                indicator = "●" if item["value"] else "○"
                label = f"{prefix}{indicator} {item['label']}"
            elif item["type"] == "cycle":
                label = f"{prefix}◆ {item['label']}"
            elif item["type"] == "provider":
                label = f"{prefix}🔑 {item['label']}"
            else:
                label = f"{prefix}  {item['label']}"

            lines.append(label)

        body.update("\n".join(lines))

    def on_key(self, event: events.Key) -> None:
        if event.key in ("up", "k"):
            self._cursor = max(0, self._cursor - 1)
            self._render_items()
            event.stop()
        elif event.key in ("down", "j"):
            self._cursor = min(len(self._items) - 1, self._cursor + 1)
            self._render_items()
            event.stop()
        elif event.key in ("space", "enter"):
            item = self._items[self._cursor]
            if item["type"] == "toggle":
                self._toggle_current()
            elif item["type"] == "cycle":
                self._cycle_current()
            elif item["type"] == "provider" and event.key == "enter":
                self._prompt_api_key(item)
            event.stop()

    def _toggle_current(self) -> None:
        """Toggle the current item if it's a toggle."""
        item = self._items[self._cursor]
        if item["type"] != "toggle":
            return

        item["value"] = not item["value"]

        # Apply to config
        if item["key"] == "ai_enabled_default":
            self._config.ai_enabled_default = item["value"]
        elif item["key"] == "show_redaction_preview":
            self._config.show_redaction_preview = item["value"]
        elif item["key"] == "clipboard_safety":
            self._config.clipboard_safety = item["value"]

        # Persist to config.toml
        self._persist_setting(item["key"], item["value"])

        if self.is_mounted:
            self._render_items()

    def _cycle_current(self) -> None:
        """Cycle a multi-value setting to the next option."""
        item = self._items[self._cursor]
        if item["type"] != "cycle":
            return

        if item["key"] == "review_mode":
            mode_keys = [k for k, _ in _REVIEW_MODES]
            current_idx = mode_keys.index(item["value"]) if item["value"] in mode_keys else 0
            next_idx = (current_idx + 1) % len(mode_keys)
            new_mode = mode_keys[next_idx]

            item["value"] = new_mode
            self._config.review_mode = new_mode
            item["label"] = self._mode_label()

            self._persist_string_setting("review_mode", new_mode)

        if self.is_mounted:
            self._render_items()

    def _prompt_api_key(self, item: dict) -> None:
        """Open the API key input screen for a provider."""
        env_var = item["value"]
        provider_name = item["provider_name"]

        def on_key_entered(key: str | None) -> None:
            if key:
                self._save_api_key(env_var, key)
                # Refresh env keys and rebuild items
                self._env_keys = _read_env_keys(self._config.env_file)
                self._items = self._build_items()
                if self.is_mounted:
                    self._render_items()

        self.app.push_screen(
            ApiKeyInputScreen(provider_name, env_var),
            callback=on_key_entered,
        )

    def _save_api_key(self, env_var: str, key: str) -> None:
        """Write an API key to .env file securely.

        Updates the existing line if present, appends if not.
        Never logs or displays the key value.
        """
        env_file = self._config.env_file

        try:
            if env_file.exists():
                text = env_file.read_text()
            else:
                text = "# ridinCLIgun API credentials\n"

            # Update existing line or append
            pattern = _re.compile(rf"^#?\s*{env_var}\s*=.*$", _re.MULTILINE)
            if pattern.search(text):
                text = pattern.sub(f"{env_var}={key}", text, count=1)
            else:
                if not text.endswith("\n"):
                    text += "\n"
                text += f"{env_var}={key}\n"

            env_file.write_text(text)
            # Ensure restrictive permissions
            env_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600

        except OSError:
            pass

    def _persist_setting(self, key: str, value: bool) -> None:
        """Write a boolean setting change to config.toml."""
        toml_value = "true" if value else "false"
        self._persist_raw_setting(key, toml_value)

    def _persist_string_setting(self, key: str, value: str) -> None:
        """Write a string setting change to config.toml."""
        self._persist_raw_setting(key, f'"{value}"')

    def _persist_raw_setting(self, key: str, toml_value: str) -> None:
        """Write a raw TOML value to config.toml under [general]."""
        config_file = self._config.config_file
        if not config_file.exists():
            return

        try:
            text = config_file.read_text()

            if _re.search(rf"^#?\s*{key}\s*=", text, _re.MULTILINE):
                text = _re.sub(
                    rf"^#?\s*{key}\s*=\s*.*$",
                    f"{key} = {toml_value}",
                    text,
                    count=1,
                    flags=_re.MULTILINE,
                )
            elif "[general]" in text:
                text = text.replace(
                    "[general]", f"[general]\n{key} = {toml_value}", 1,
                )
            else:
                text += f"\n[general]\n{key} = {toml_value}\n"

            config_file.write_text(text)
        except OSError:
            pass

    def action_dismiss_settings(self) -> None:
        """Close the settings screen."""
        self.dismiss(None)
