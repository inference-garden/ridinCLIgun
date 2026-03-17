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


def _default_config_dir() -> Path:
    """Return the default config directory."""
    return Path.home() / ".config" / "ridincligun"


@dataclass
class ProviderSettings:
    """Settings for a specific AI provider."""

    kind: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    timeout_seconds: float = 10.0
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

    # UI settings
    split_ratio: tuple[int, int] = (3, 2)  # shell:advisory as fr units

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
            "\n"
            "[provider]\n"
            'kind = "anthropic"\n'
            'model = "claude-sonnet-4-20250514"\n'
            "timeout_seconds = 10.0\n"
            "max_tokens = 1024\n"
            "\n"
            "[ui]\n"
            "# Split ratio as shell:advisory (fr units)\n"
            "split_ratio = [3, 2]\n"
        )


def load_config(config_dir: Path | None = None) -> Config:
    """Load configuration from disk.

    Creates default config files if they don't exist.
    Loads .env for API secrets into os.environ.
    """
    config_dir = config_dir or _default_config_dir()
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
        with open(config_file, "rb") as f:
            data = tomllib.load(f)

        # General settings
        general = data.get("general", {})
        if "ai_enabled_default" in general:
            config.ai_enabled_default = bool(general["ai_enabled_default"])

        # Provider settings
        provider_data = data.get("provider", {})
        if provider_data:
            config.provider = ProviderSettings(
                kind=provider_data.get("kind", config.provider.kind),
                model=provider_data.get("model", config.provider.model),
                timeout_seconds=float(
                    provider_data.get("timeout_seconds", config.provider.timeout_seconds)
                ),
                max_tokens=int(provider_data.get("max_tokens", config.provider.max_tokens)),
            )

        # UI settings
        ui_data = data.get("ui", {})
        if "split_ratio" in ui_data:
            ratio = ui_data["split_ratio"]
            if isinstance(ratio, list) and len(ratio) == 2:
                config.split_ratio = (int(ratio[0]), int(ratio[1]))

    # Resolve API key: .env takes priority, fall back to os.environ.
    # The key stays in Config — never injected into os.environ (FINDING-02).
    config.api_key = (
        env_vars.get("ANTHROPIC_API_KEY", "")
        or os.environ.get("ANTHROPIC_API_KEY", "")
        or ""
    )

    return config
