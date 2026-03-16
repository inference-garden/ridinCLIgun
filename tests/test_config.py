"""Tests for configuration loading."""


import pytest

from ridincligun.config import Config, load_config


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


def test_config_paths(tmp_config_dir):
    """Config path properties resolve correctly."""
    config = Config(config_dir=tmp_config_dir)

    assert config.env_file == tmp_config_dir / ".env"
    assert config.config_file == tmp_config_dir / "config.toml"
    assert config.log_dir == tmp_config_dir / "logs"
