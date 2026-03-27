# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for configuration

"""Tests for configuration loading."""


import pytest

from ridincligun.config import Config, load_config, save_split_ratio


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
