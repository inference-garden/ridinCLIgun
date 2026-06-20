# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — TOML and .env configuration

"""Configuration loading for ridinCLIgun.

Reads config.toml from ~/.config/ridincligun/ and .env for API secrets.
Creates default config directory and files if they don't exist.
API keys are read into the Config object and passed explicitly
to the provider adapter — never injected into os.environ (FINDING-02).
"""

from __future__ import annotations

import os
import stat
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values


class ConfigError(Exception):
    """Raised when config.toml exists but cannot be parsed.

    Carries a clean, actionable, secret-free message (config.toml holds no
    credentials — those live in .env). The entry point shows it verbatim and
    exits, rather than dumping a raw traceback. We fail closed — a broken config
    is never silently replaced by defaults.
    """


def _default_config_dir() -> Path:
    """Return the default config directory."""
    return Path.home() / ".config" / "ridincligun"


@dataclass
class ProviderSettings:
    """Settings for the chosen AI provider.

    Provider-only: the user picks a provider and the app maps it to a Fast and a Deep
    model via the registry (``provider/registry.py``). There is no per-model field — a
    legacy ``model`` key in an existing config.toml is read and silently ignored (no
    migration), and the provider-only form is persisted going forward.
    """

    kind: str = "anthropic"
    timeout_seconds: float = 15.0
    max_tokens: int = 1024


@dataclass
class Config:
    """Application configuration. Loaded once at startup."""

    # Paths
    config_dir: Path = field(default_factory=_default_config_dir)

    # AI settings
    ai_enabled_default: bool = False
    provider: ProviderSettings = field(default_factory=ProviderSettings)

    # API key — held in memory, never injected into os.environ (FINDING-02)
    api_key: str = ""

    # Review mode — "default" or "explorer" (kid-friendly)
    review_mode: str = "default"

    # Language — "en", "de", "fr", or "" (auto-detect from $LANG)
    language: str = ""

    # Shell settings
    shell: str = ""  # empty = use $SHELL or /bin/zsh

    # UI settings
    split_ratio: tuple[int, int] = (3, 2)  # shell:advisory as fr units

    # Privacy settings
    show_redaction_preview: bool = True  # show what gets sent to AI before sending
    clipboard_safety: bool = True  # warn before pasting secrets

    # Lifecycle
    first_run: bool = False  # True when config was created fresh (no prior config.toml)

    @property
    def env_file(self) -> Path:
        return self.config_dir / ".env"

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def log_dir(self) -> Path:
        return self.config_dir / "logs"


def _ensure_config_dir(config_dir: Path) -> None:
    """Create config directory and default files if they don't exist."""
    config_dir.mkdir(parents=True, exist_ok=True)

    env_file = config_dir / ".env"
    if not env_file.exists():
        env_file.write_text(
            "# ridinCLIgun API credentials\n"
            "# ANTHROPIC_API_KEY=\n"
            "# OPENAI_API_KEY=\n"
            "# MISTRAL_API_KEY=\n"
        )
        # SECURITY: Restrict .env to owner-only read/write (AMENDMENT-01)
        env_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    else:
        # Harden permissions on existing .env files too
        current_mode = env_file.stat().st_mode
        if current_mode & (stat.S_IRGRP | stat.S_IROTH):
            env_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

    config_file = config_dir / "config.toml"
    if not config_file.exists():
        config_file.write_text(
            "# ridinCLIgun configuration\n"
            "\n"
            "[general]\n"
            "ai_enabled_default = false\n"
            '# language = ""  # "en", "de", "fr", or "" for auto-detect\n'
            '# review_mode = "default"  # "default" or "explorer" (kid-friendly)\n'
            '# shell = "/bin/zsh"  # override default shell\n'
            "\n"
            "[provider]\n"
            'kind = "anthropic"  # "anthropic", "openai", or "mistral"\n'
            "# Fast/Deep models are chosen automatically per command — no model id to set.\n"
            "timeout_seconds = 10.0\n"
            "max_tokens = 1024\n"
            "\n"
            "[privacy]\n"
            "# Show what will be sent to AI before sending (true/false)\n"
            "show_redaction_preview = true\n"
            "\n"
            "[ui]\n"
            "# Split ratio as shell:advisory (fr units)\n"
            "split_ratio = [3, 2]\n"
        )


def load_config(config_dir: Path | None = None) -> Config:
    """Load configuration from disk.

    Creates default config files if they don't exist.
    Reads .env for API secrets into Config (not os.environ).
    """
    config_dir = config_dir or _default_config_dir()
    is_first_run = not (config_dir / "config.toml").exists()
    _ensure_config_dir(config_dir)

    # Load .env into a dict — NOT into os.environ (FINDING-02)
    env_file = config_dir / ".env"
    env_vars: dict[str, str | None] = {}
    if env_file.exists():
        env_vars = dotenv_values(env_file)

    # Load config.toml
    config = Config(config_dir=config_dir)
    config_file = config_dir / "config.toml"

    if config_file.exists():
        try:
            with open(config_file, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            # Fail closed with a clear, actionable message (the error already names
            # the line/column). Never fall back to defaults silently.
            raise ConfigError(
                f"Invalid config file {config_file}: {e}. "
                "Fix it, or delete the file to regenerate defaults."
            ) from e

        # General settings
        general = data.get("general", {})
        if "ai_enabled_default" in general:
            config.ai_enabled_default = bool(general["ai_enabled_default"])
        if "shell" in general:
            config.shell = str(general["shell"])
        if "review_mode" in general:
            mode = str(general["review_mode"]).lower()
            if mode in ("default", "explorer"):
                config.review_mode = mode
        if "language" in general:
            config.language = str(general["language"]).lower()

        # Provider settings. A legacy ``model`` key is intentionally NOT read — provider
        # selection is provider-only now; any vestigial model id is silently ignored.
        provider_data = data.get("provider", {})
        if provider_data:
            config.provider = ProviderSettings(
                kind=provider_data.get("kind", config.provider.kind),
                timeout_seconds=float(
                    provider_data.get("timeout_seconds", config.provider.timeout_seconds)
                ),
                max_tokens=int(provider_data.get("max_tokens", config.provider.max_tokens)),
            )

        # Privacy settings
        privacy_data = data.get("privacy", {})
        if "show_redaction_preview" in privacy_data:
            config.show_redaction_preview = bool(privacy_data["show_redaction_preview"])
        if "clipboard_safety" in privacy_data:
            config.clipboard_safety = bool(privacy_data["clipboard_safety"])

        # UI settings
        ui_data = data.get("ui", {})
        if "split_ratio" in ui_data:
            ratio = ui_data["split_ratio"]
            if isinstance(ratio, list) and len(ratio) == 2:
                config.split_ratio = (int(ratio[0]), int(ratio[1]))

    # Resolve API key based on provider kind.
    # .env takes priority, fall back to os.environ.
    # The key stays in Config — never injected into os.environ (FINDING-02).
    _KEY_MAP = {  # noqa: N806
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "mistral": "MISTRAL_API_KEY",
    }
    key_name = _KEY_MAP.get(config.provider.kind.lower(), "ANTHROPIC_API_KEY")
    config.api_key = env_vars.get(key_name, "") or os.environ.get(key_name, "") or ""

    config.first_run = is_first_run
    return config


def save_split_ratio(config: Config, ratio: tuple[int, int]) -> None:
    """Persist the split ratio to config.toml.

    Rewrites the [ui] split_ratio value while preserving the rest of the file.
    Fails silently on I/O errors — this is a convenience feature, not critical.
    """
    import re as _re

    config_file = config.config_file
    if not config_file.exists():
        return

    try:
        text = config_file.read_text()
        new_value = f"split_ratio = [{ratio[0]}, {ratio[1]}]"

        if _re.search(r"^split_ratio\s*=", text, _re.MULTILINE):
            text = _re.sub(
                r"^split_ratio\s*=\s*\[.*?\]",
                new_value,
                text,
                count=1,
                flags=_re.MULTILINE,
            )
        elif "[ui]" in text:
            text = text.replace("[ui]", f"[ui]\n{new_value}", 1)
        else:
            text += f"\n[ui]\n{new_value}\n"

        config_file.write_text(text)
    except OSError:
        pass  # Non-critical — ratio resets to default next launch


def save_provider_config(config: Config, kind: str) -> None:
    """Persist the provider kind to config.toml.

    Provider-only: updates the [provider] ``kind`` value in-place and leaves any
    vestigial ``model`` line untouched (it is ignored on load). Fails silently on I/O
    errors — the in-session switch remains active.
    """
    import re as _re

    config_file = config.config_file
    if not config_file.exists():
        return

    try:
        text = config_file.read_text()

        if _re.search(r"^kind\s*=", text, _re.MULTILINE):
            text = _re.sub(
                r'^kind\s*=\s*"[^"]*"',
                f'kind = "{kind}"',
                text,
                count=1,
                flags=_re.MULTILINE,
            )

        config_file.write_text(text)
    except OSError:
        pass  # Non-critical — provider choice resets on next launch
