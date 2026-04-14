# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Internationalization support

"""Lightweight i18n with TOML string tables.

Provides a ``t(key)`` function that returns the translated string for the
current locale.  Translations live in ``data/locales/{locale}/ui.toml``
and ``data/locales/{locale}/catalog.toml``.

Fallback chain: requested locale → "en" → the key itself (visible bug signal).
"""

from __future__ import annotations

import os
import tomllib
from importlib import resources
from pathlib import Path

# ── Module state ────────────────────────────────────────────────

_current_locale: str = "en"
_strings: dict[str, dict[str, str]] = {}  # locale -> flat_key -> string
_data_path: Path | None = None

# ── Data path resolution ────────────────────────────────────────

_LOCALE_FILES = ("ui.toml", "catalog.toml")


def _resolve_data_path() -> Path:
    """Locate the data/locales directory (package or repo layout)."""
    global _data_path
    if _data_path is not None:
        return _data_path

    # Try installed package data first
    try:
        pkg = resources.files("ridincligun") / "data" / "locales"
        # resources.files may return a Traversable — convert to Path if real
        candidate = Path(str(pkg))
        if candidate.is_dir():
            _data_path = candidate
            return _data_path
    except (FileNotFoundError, TypeError):
        pass

    # Fall back to repo-relative layout
    # i18n.py is at src/ridincligun/i18n.py → parents[2] is the repo root
    repo = Path(__file__).resolve().parents[2] / "data" / "locales"
    if repo.is_dir():
        _data_path = repo
        return _data_path

    # Last resort — return repo path even if missing (load will fail gracefully)
    _data_path = repo
    return _data_path


# ── TOML flattening ────────────────────────────────────────────

def _flatten_toml(data: dict, prefix: str = "") -> dict[str, str]:
    """Recursively flatten nested TOML into dotted keys.

    Example: {"toast": {"ai_on": "..."}} → {"toast.ai_on": "..."}
    """
    flat: dict[str, str] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten_toml(value, full_key))
        else:
            flat[full_key] = str(value)
    return flat


# ── Locale loading ──────────────────────────────────────────────

def _load_locale(locale: str) -> dict[str, str]:
    """Load and merge all TOML string files for a locale."""
    base = _resolve_data_path() / locale
    merged: dict[str, str] = {}

    for filename in _LOCALE_FILES:
        filepath = base / filename
        if not filepath.exists():
            continue
        try:
            with open(filepath, "rb") as f:
                data = tomllib.load(f)
            merged.update(_flatten_toml(data))
        except (tomllib.TOMLDecodeError, OSError):
            pass  # Skip malformed files — EN fallback covers gaps

    return merged


# ── Public API ──────────────────────────────────────────────────

def set_locale(locale: str) -> None:
    """Set the active locale and load its strings.

    Always loads "en" as fallback if not already cached.
    """
    global _current_locale

    # Ensure EN baseline is always available
    if "en" not in _strings:
        _strings["en"] = _load_locale("en")

    if locale != "en" and locale not in _strings:
        _strings[locale] = _load_locale(locale)

    _current_locale = locale


def get_locale() -> str:
    """Return the current locale code (e.g. 'en', 'de', 'fr')."""
    return _current_locale


def t(key: str, **kwargs: object) -> str:
    """Look up a translated string by dotted key.

    Supports ``{name}`` interpolation via keyword arguments.
    Fallback: current locale → "en" → the key itself.
    """
    # Try current locale
    text = _strings.get(_current_locale, {}).get(key)

    # Fallback to EN
    if text is None and _current_locale != "en":
        text = _strings.get("en", {}).get(key)

    # Last resort — return the key (visible debugging signal)
    if text is None:
        return key

    if kwargs:
        try:
            return text.format_map({k: str(v) for k, v in kwargs.items()})
        except (KeyError, ValueError):
            return text

    return text


def available_locales() -> list[str]:
    """Return sorted list of locale codes found in data/locales/."""
    base = _resolve_data_path()
    if not base.is_dir():
        return ["en"]
    locales = sorted(
        d.name for d in base.iterdir()
        if d.is_dir() and (d / "ui.toml").exists()
    )
    return locales if locales else ["en"]


def detect_system_locale() -> str:
    """Auto-detect locale from environment variables.

    Parses $LANG or $LC_MESSAGES to extract a 2-letter language code.
    Returns "en" if detection fails or the locale is not available.
    """
    for var in ("LC_MESSAGES", "LANG"):
        raw = os.environ.get(var, "")
        if raw:
            # Parse formats like "de_DE.UTF-8", "fr_FR", "en"
            code = raw.split("_")[0].split(".")[0].lower()
            if len(code) == 2 and code in available_locales():
                return code
    return "en"


def reload_locale() -> None:
    """Force-reload the current locale's strings from disk.

    Useful after a language switch to refresh cached catalog translations.
    """
    locale = _current_locale
    _strings[locale] = _load_locale(locale)
    if locale != "en":
        _strings["en"] = _load_locale("en")
