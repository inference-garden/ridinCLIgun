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
from ridincligun.i18n import available_locales, get_locale, reload_locale, set_locale, t

# Available languages — display names (always in their own language)
_LANGUAGE_DISPLAY: dict[str, str] = {
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
}

# Provider → environment variable name mapping
# Available review modes — order determines cycle direction
_REVIEW_MODE_KEYS: list[str] = ["default", "explorer"]

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
                t("settings.key_input_title", provider=self._provider_name),
                classes="key-input-title",
            )
            yield Label(f"  {self._env_var}", classes="key-input-hint")
            yield Input(
                placeholder=t("settings.key_input_placeholder"),
                password=True,
                id="key-input",
            )
            yield Label(
                t("settings.key_input_hint"),
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


class SettingsScreen(ModalScreen[str | None]):
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
        mode_display = t(f"modes.{self._config.review_mode}")
        return t("settings.review_mode_label", mode=mode_display)

    def _build_items(self) -> list[dict]:
        """Build the settings item list from current config state."""
        current_lang = get_locale()
        lang_display = _LANGUAGE_DISPLAY.get(current_lang, current_lang)
        items: list[dict] = [
            {
                "section": t("settings.section_general"),
                "key": "language",
                "label": t("settings.language_label", language=lang_display),
                "value": current_lang,
                "type": "cycle",
            },
            {
                "section": t("settings.section_ai"),
                "key": "ai_enabled_default",
                "label": t("settings.ai_enabled"),
                "value": self._config.ai_enabled_default,
                "type": "toggle",
            },
            {
                "section": t("settings.section_ai"),
                "key": "provider_kind",
                "label": t("settings.provider_label", provider=self._config.provider.kind),
                "value": self._config.provider.kind,
                "type": "action",
                "action": "model_select",
            },
            {
                "section": t("settings.section_ai"),
                "key": "model",
                "label": t("settings.model_label", model=self._config.provider.model),
                "value": self._config.provider.model,
                "type": "action",
                "action": "model_select",
            },
            {
                "section": t("settings.section_ai"),
                "key": "review_mode",
                "label": self._mode_label(),
                "value": self._config.review_mode,
                "type": "cycle",
            },
            {
                "section": t("settings.section_privacy"),
                "key": "show_redaction_preview",
                "label": t("settings.redaction_preview"),
                "value": self._config.show_redaction_preview,
                "type": "toggle",
            },
            {
                "section": t("settings.section_privacy"),
                "key": "clipboard_safety",
                "label": t("settings.clipboard_safety"),
                "value": self._config.clipboard_safety,
                "type": "toggle",
            },
        ]

        # Provider API key items
        for provider_name, env_var in _PROVIDER_KEYS:
            key_val = self._env_keys.get(env_var, "")
            if key_val:
                status = t("settings.key_configured", suffix=key_val[-4:])
            else:
                # Also check os.environ as fallback
                env_val = os.environ.get(env_var, "")
                if env_val:
                    status = t("settings.key_from_env", suffix=env_val[-4:])
                else:
                    status = t("settings.key_not_configured")

            items.append({
                "section": t("settings.section_keys"),
                "key": env_var,
                "label": f"{provider_name}: {status}",
                "value": env_var,
                "type": "provider",
                "provider_name": provider_name,
            })

        return items

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-container"):
            yield Label(t("settings.title"), classes="settings-title")
            yield Static(id="settings-body")
            yield Label(
                t("settings.hint"),
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
                label = f"{prefix}* {item['label']}"
            elif item["type"] == "action":
                label = f"{prefix}↵ {item['label']}"
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
            elif item["type"] == "action" and event.key == "enter":
                self.dismiss(item.get("action"))
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

        if item["key"] == "language":
            locales = available_locales()
            current_idx = locales.index(item["value"]) if item["value"] in locales else 0
            next_idx = (current_idx + 1) % len(locales)
            new_lang = locales[next_idx]

            item["value"] = new_lang
            self._config.language = new_lang
            set_locale(new_lang)
            reload_locale()

            self._persist_string_setting("language", new_lang)

            # Rebuild all items to reflect translated labels
            self._items = self._build_items()

        elif item["key"] == "review_mode":
            current_idx = (
                _REVIEW_MODE_KEYS.index(item["value"])
                if item["value"] in _REVIEW_MODE_KEYS
                else 0
            )
            next_idx = (current_idx + 1) % len(_REVIEW_MODE_KEYS)
            new_mode = _REVIEW_MODE_KEYS[next_idx]

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
        """Close the settings screen (no action)."""
        self.dismiss(None)
