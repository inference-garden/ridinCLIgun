# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for configuration

"""Tests for configuration loading."""


import pytest

from ridincligun.config import Config, load_config, save_provider_config, save_split_ratio


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Provide a temp directory for config files."""
    return tmp_path / "ridincligun"


def test_load_config_creates_defaults(tmp_config_dir):
    """Loading config from empty dir creates default files."""
    load_config(config_dir=tmp_config_dir)

    assert tmp_config_dir.exists()
    assert (tmp_config_dir / ".env").exists()
    assert (tmp_config_dir / "config.toml").exists()


def test_default_config_values(tmp_config_dir):
    """Default config has expected values."""
    config = load_config(config_dir=tmp_config_dir)

    assert config.ai_enabled_default is False
    assert config.provider.kind == "anthropic"
    assert config.split_ratio == (3, 2)


def test_config_reads_toml(tmp_config_dir):
    """Config reads values from config.toml."""
    tmp_config_dir.mkdir(parents=True, exist_ok=True)
    (tmp_config_dir / "config.toml").write_text(
        '[general]\n'
        'ai_enabled_default = true\n'
        '\n'
        '[provider]\n'
        'kind = "anthropic"\n'
        'model = "claude-haiku-3"\n'
        'timeout_seconds = 5.0\n'
        '\n'
        '[ui]\n'
        'split_ratio = [2, 3]\n'
    )
    (tmp_config_dir / ".env").write_text("")

    config = load_config(config_dir=tmp_config_dir)

    assert config.ai_enabled_default is True
    assert config.provider.model == "claude-haiku-3"
    assert config.provider.timeout_seconds == 5.0
    assert config.split_ratio == (2, 3)


def test_config_reads_shell(tmp_config_dir):
    """Config reads shell override from config.toml."""
    tmp_config_dir.mkdir(parents=True, exist_ok=True)
    (tmp_config_dir / "config.toml").write_text(
        '[general]\n'
        'shell = "/bin/bash"\n'
    )
    (tmp_config_dir / ".env").write_text("")

    config = load_config(config_dir=tmp_config_dir)
    assert config.shell == "/bin/bash"


def test_config_shell_default_empty(tmp_config_dir):
    """Config shell defaults to empty string (use $SHELL)."""
    config = load_config(config_dir=tmp_config_dir)
    assert config.shell == ""


def test_config_env_permissions(tmp_config_dir):
    """Newly created .env file has 0600 permissions."""
    import stat
    load_config(config_dir=tmp_config_dir)
    env_file = tmp_config_dir / ".env"
    mode = env_file.stat().st_mode
    # Owner read+write only
    assert mode & stat.S_IRUSR
    assert mode & stat.S_IWUSR
    # No group or other access
    assert not (mode & stat.S_IRGRP)
    assert not (mode & stat.S_IROTH)


def test_save_split_ratio_persists(tmp_config_dir):
    """save_split_ratio writes ratio to config.toml and it survives reload."""
    config = load_config(config_dir=tmp_config_dir)
    assert config.split_ratio == (3, 2)  # default

    save_split_ratio(config, (5, 3))

    reloaded = load_config(config_dir=tmp_config_dir)
    assert reloaded.split_ratio == (5, 3)


def test_save_split_ratio_no_crash_on_missing_file(tmp_config_dir):
    """save_split_ratio does not crash if config.toml is missing."""
    config = Config(config_dir=tmp_config_dir)
    # config_file doesn't exist — should silently return
    save_split_ratio(config, (4, 4))


def test_config_paths(tmp_config_dir):
    """Config path properties resolve correctly."""
    config = Config(config_dir=tmp_config_dir)

    assert config.env_file == tmp_config_dir / ".env"
    assert config.config_file == tmp_config_dir / "config.toml"
    assert config.log_dir == tmp_config_dir / "logs"


# ── Provider persistence (4.9d) ───────────────────────────────────


def _write_provider_toml(config_dir, kind: str, model: str) -> None:
    """Write a minimal config.toml with the given provider settings."""
    (config_dir / "config.toml").write_text(
        "[general]\n"
        "ai_enabled_default = false\n"
        "\n"
        "[provider]\n"
        f'kind = "{kind}"\n'
        f'model = "{model}"\n'
        "timeout_seconds = 15.0\n"
        "max_tokens = 1024\n"
        "\n"
        "[ui]\n"
        "split_ratio = [3, 2]\n"
    )


def test_save_provider_config_persists_kind_and_model(tmp_config_dir):
    """save_provider_config writes kind and model and load_config reads them back."""
    tmp_config_dir.mkdir(parents=True, exist_ok=True)
    _write_provider_toml(tmp_config_dir, "anthropic", "claude-sonnet-4-20250514")
    (tmp_config_dir / ".env").write_text("")

    config = load_config(config_dir=tmp_config_dir)
    assert config.provider.kind == "anthropic"

    save_provider_config(config, "mistral", "mistral-large-latest")

    reloaded = load_config(config_dir=tmp_config_dir)
    assert reloaded.provider.kind == "mistral"
    assert reloaded.provider.model == "mistral-large-latest"


def test_save_provider_config_no_crash_on_missing_file(tmp_config_dir):
    """save_provider_config does not crash if config.toml is missing."""
    config = Config(config_dir=tmp_config_dir)
    # config_file doesn't exist — should silently return
    save_provider_config(config, "openai", "gpt-4o")


def test_load_config_reads_mistral_api_key(tmp_config_dir):
    """When kind=mistral, load_config resolves MISTRAL_API_KEY from .env."""
    tmp_config_dir.mkdir(parents=True, exist_ok=True)
    _write_provider_toml(tmp_config_dir, "mistral", "mistral-large-latest")
    (tmp_config_dir / ".env").write_text("MISTRAL_API_KEY=test-mistral-key\n")

    config = load_config(config_dir=tmp_config_dir)
    assert config.provider.kind == "mistral"
    assert config.api_key == "test-mistral-key"


def test_load_config_reads_openai_api_key(tmp_config_dir):
    """When kind=openai, load_config resolves OPENAI_API_KEY from .env."""
    tmp_config_dir.mkdir(parents=True, exist_ok=True)
    _write_provider_toml(tmp_config_dir, "openai", "gpt-4o")
    (tmp_config_dir / ".env").write_text("OPENAI_API_KEY=sk-openai-test\n")

    config = load_config(config_dir=tmp_config_dir)
    assert config.provider.kind == "openai"
    assert config.api_key == "sk-openai-test"


def test_load_config_mistral_does_not_load_anthropic_key(tmp_config_dir):
    """When kind=mistral, the Anthropic key must NOT be returned as api_key."""
    tmp_config_dir.mkdir(parents=True, exist_ok=True)
    _write_provider_toml(tmp_config_dir, "mistral", "mistral-small-latest")
    (tmp_config_dir / ".env").write_text(
        "ANTHROPIC_API_KEY=sk-ant-secret\n"
        "MISTRAL_API_KEY=\n"  # empty
    )

    config = load_config(config_dir=tmp_config_dir)
    assert config.provider.kind == "mistral"
    assert config.api_key != "sk-ant-secret"
    assert config.api_key == ""


def test_provider_switch_survives_restart(tmp_config_dir):
    """Full round-trip: switch to OpenAI, reload config, key and kind persist."""
    tmp_config_dir.mkdir(parents=True, exist_ok=True)
    _write_provider_toml(tmp_config_dir, "anthropic", "claude-sonnet-4-20250514")
    (tmp_config_dir / ".env").write_text(
        "ANTHROPIC_API_KEY=sk-ant-old\n"
        "OPENAI_API_KEY=sk-openai-new\n"
    )

    config = load_config(config_dir=tmp_config_dir)
    assert config.provider.kind == "anthropic"

    # Simulate user switching to OpenAI at runtime
    save_provider_config(config, "openai", "gpt-4o-mini")

    # Simulate restart
    reloaded = load_config(config_dir=tmp_config_dir)
    assert reloaded.provider.kind == "openai"
    assert reloaded.provider.model == "gpt-4o-mini"
    assert reloaded.api_key == "sk-openai-new"
