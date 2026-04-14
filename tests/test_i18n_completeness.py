# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Translation completeness checks

"""Verify that all locales have the same keys as the English baseline.

Run with: pytest tests/test_i18n_completeness.py -v
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

# Resolve data/locales path relative to repo root
_LOCALES_DIR = Path(__file__).resolve().parents[1] / "data" / "locales"


def _flatten_toml(data: dict, prefix: str = "") -> set[str]:
    """Recursively flatten TOML into a set of dotted keys."""
    keys: set[str] = set()
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys.update(_flatten_toml(value, full_key))
        else:
            keys.add(full_key)
    return keys


def _load_keys(locale: str, filename: str) -> set[str]:
    """Load all keys from a locale TOML file."""
    filepath = _LOCALES_DIR / locale / filename
    if not filepath.exists():
        return set()
    with open(filepath, "rb") as f:
        data = tomllib.load(f)
    return _flatten_toml(data)


def _non_en_locales() -> list[str]:
    """Return all locale codes except 'en'."""
    if not _LOCALES_DIR.is_dir():
        return []
    return sorted(
        d.name for d in _LOCALES_DIR.iterdir()
        if d.is_dir() and d.name != "en" and (d / "ui.toml").exists()
    )


@pytest.fixture(scope="module")
def en_ui_keys() -> set[str]:
    return _load_keys("en", "ui.toml")


@pytest.fixture(scope="module")
def en_catalog_keys() -> set[str]:
    return _load_keys("en", "catalog.toml")


@pytest.mark.parametrize("locale", _non_en_locales())
def test_ui_completeness(locale: str, en_ui_keys: set[str]):
    """Every EN ui.toml key must exist in the locale's ui.toml."""
    locale_keys = _load_keys(locale, "ui.toml")
    missing = en_ui_keys - locale_keys
    assert not missing, (
        f"Locale '{locale}' ui.toml is missing {len(missing)} keys:\n"
        + "\n".join(sorted(missing)[:20])
    )


@pytest.mark.parametrize("locale", _non_en_locales())
def test_catalog_completeness(locale: str, en_catalog_keys: set[str]):
    """Every EN catalog.toml key must exist in the locale's catalog.toml."""
    locale_keys = _load_keys(locale, "catalog.toml")
    missing = en_catalog_keys - locale_keys
    assert not missing, (
        f"Locale '{locale}' catalog.toml is missing {len(missing)} keys:\n"
        + "\n".join(sorted(missing)[:20])
    )


@pytest.mark.parametrize("locale", _non_en_locales())
def test_no_extra_ui_keys(locale: str, en_ui_keys: set[str]):
    """Locale ui.toml should not have keys that don't exist in EN."""
    locale_keys = _load_keys(locale, "ui.toml")
    extra = locale_keys - en_ui_keys
    assert not extra, (
        f"Locale '{locale}' ui.toml has {len(extra)} extra keys not in EN:\n"
        + "\n".join(sorted(extra)[:20])
    )


@pytest.mark.parametrize("locale", _non_en_locales())
def test_no_extra_catalog_keys(locale: str, en_catalog_keys: set[str]):
    """Locale catalog.toml should not have keys that don't exist in EN."""
    locale_keys = _load_keys(locale, "catalog.toml")
    extra = locale_keys - en_catalog_keys
    assert not extra, (
        f"Locale '{locale}' catalog.toml has {len(extra)} extra keys not in EN:\n"
        + "\n".join(sorted(extra)[:20])
    )
