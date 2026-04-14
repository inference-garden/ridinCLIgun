# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — i18n unit tests

"""Tests for the i18n module."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from ridincligun.i18n import (
    _flatten_toml,
    _strings,
    available_locales,
    detect_system_locale,
    get_locale,
    set_locale,
    t,
)


@pytest.fixture(autouse=True)
def _reset_i18n():
    """Reset i18n state before each test."""
    _strings.clear()
    set_locale("en")
    yield
    _strings.clear()


class TestFlattenToml:
    """Tests for TOML dict flattening."""

    def test_flat_dict(self):
        assert _flatten_toml({"a": "1", "b": "2"}) == {"a": "1", "b": "2"}

    def test_nested_dict(self):
        data = {"toast": {"ai_on": "AI on", "ai_off": "AI off"}}
        assert _flatten_toml(data) == {
            "toast.ai_on": "AI on",
            "toast.ai_off": "AI off",
        }

    def test_deeply_nested(self):
        data = {"a": {"b": {"c": "deep"}}}
        assert _flatten_toml(data) == {"a.b.c": "deep"}

    def test_mixed_types(self):
        data = {"x": "flat", "y": {"z": "nested"}}
        assert _flatten_toml(data) == {"x": "flat", "y.z": "nested"}


class TestSetAndGetLocale:
    """Tests for locale switching."""

    def test_default_is_en(self):
        assert get_locale() == "en"

    def test_set_locale_changes_current(self):
        set_locale("de")
        assert get_locale() == "de"

    def test_set_locale_back_to_en(self):
        set_locale("de")
        set_locale("en")
        assert get_locale() == "en"


class TestTranslation:
    """Tests for the t() function."""

    def test_known_key_returns_value(self):
        result = t("toast.ai_on")
        assert result == "AI review: on"

    def test_unknown_key_returns_key(self):
        result = t("nonexistent.key.here")
        assert result == "nonexistent.key.here"

    def test_interpolation(self):
        result = t("toast.copied", source="selection")
        assert result == "Copied selection to clipboard."

    def test_interpolation_missing_kwarg(self):
        # Should return the template string without crashing
        result = t("toast.copied")
        assert "{source}" in result

    def test_fallback_to_en(self):
        """When DE locale is active but a key is missing, fall back to EN."""
        set_locale("de")
        # This key should exist in EN; if DE is incomplete, it falls back
        result = t("toast.ai_on")
        # Should return something (either DE translation or EN fallback)
        assert result != "toast.ai_on"


class TestAvailableLocales:
    """Tests for locale discovery."""

    def test_includes_en(self):
        locales = available_locales()
        assert "en" in locales

    def test_returns_sorted(self):
        locales = available_locales()
        assert locales == sorted(locales)


class TestDetectSystemLocale:
    """Tests for system locale auto-detection."""

    def test_detect_from_lang(self):
        with patch.dict(os.environ, {"LANG": "de_DE.UTF-8", "LC_MESSAGES": ""}):
            # Only returns "de" if it's in available_locales()
            result = detect_system_locale()
            locales = available_locales()
            if "de" in locales:
                assert result == "de"
            else:
                assert result == "en"

    def test_detect_fallback_en(self):
        with patch.dict(os.environ, {"LANG": "", "LC_MESSAGES": ""}, clear=False):
            result = detect_system_locale()
            assert result == "en"

    def test_detect_unknown_locale(self):
        with patch.dict(os.environ, {"LANG": "xx_XX.UTF-8", "LC_MESSAGES": ""}):
            result = detect_system_locale()
            assert result == "en"


class TestPromptLocale:
    """Tests for locale-aware prompt building."""

    def test_en_prompt_has_no_language_instruction(self):
        from ridincligun.provider.prompt import build_system_prompt

        prompt = build_system_prompt(locale="en")
        assert "IMPORTANT: Write all" not in prompt

    def test_de_prompt_has_german_instruction(self):
        from ridincligun.provider.prompt import build_system_prompt

        prompt = build_system_prompt(locale="de")
        assert "German" in prompt
        assert "IMPORTANT:" in prompt

    def test_fr_prompt_has_french_instruction(self):
        from ridincligun.provider.prompt import build_system_prompt

        prompt = build_system_prompt(locale="fr")
        assert "French" in prompt

    def test_deep_analysis_locale(self):
        from ridincligun.provider.deep_analysis import build_deep_analysis_prompt

        prompt = build_deep_analysis_prompt("http://example.com", "echo hello", locale="de")
        assert "German" in prompt

    def test_deep_analysis_en_no_instruction(self):
        from ridincligun.provider.deep_analysis import build_deep_analysis_prompt

        prompt = build_deep_analysis_prompt("http://example.com", "echo hello", locale="en")
        assert "IMPORTANT: Write all" not in prompt
