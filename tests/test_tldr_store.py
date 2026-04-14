# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for TldrStore

"""Tests for the offline tldr-pages store."""

import json
from pathlib import Path

import pytest

from ridincligun.advisory.tldr_store import TldrExample, TldrPage, TldrStore

# ── Helpers ───────────────────────────────────────────────────────

def _write_catalog(path: Path, entries: dict) -> None:
    """Write a catalog dict as plain JSON."""
    path.write_text(json.dumps(entries), encoding="utf-8")


def _minimal_entries() -> dict:
    return {
        "tar": {
            "desc": "Archive tool.",
            "examples": [
                {"desc": "Extract a tar archive", "cmd": "tar xf file.tar"},
                {"desc": "Create an archive", "cmd": "tar cf archive.tar dir"},
            ],
        },
        "ls": {
            "desc": "List directory contents.",
            "examples": [
                {"desc": "List all files", "cmd": "ls -la"},
            ],
        },
        "git": {
            "desc": "Distributed version control system.",
            "examples": [],
        },
    }


@pytest.fixture
def store(tmp_path: Path) -> TldrStore:
    p = tmp_path / "tldr_catalog.json"
    _write_catalog(p, _minimal_entries())
    return TldrStore(catalog_path=p)


# ── TldrExample / TldrPage dataclasses ───────────────────────────

def test_tldr_example_frozen():
    ex = TldrExample(description="List files", command="ls -la")
    with pytest.raises((AttributeError, TypeError)):
        ex.description = "changed"  # type: ignore[misc]


def test_tldr_page_frozen():
    page = TldrPage(command="ls", description="List.", examples=[])
    with pytest.raises((AttributeError, TypeError)):
        page.command = "changed"  # type: ignore[misc]


# ── TldrStore.lookup ──────────────────────────────────────────────

def test_lookup_known_command(store):
    page = store.lookup("tar")
    assert page is not None
    assert page.command == "tar"
    assert "Archive" in page.description


def test_lookup_case_insensitive(store):
    assert store.lookup("TAR") is not None
    assert store.lookup("Tar") is not None
    assert store.lookup("tar") is not None


def test_lookup_strips_whitespace(store):
    assert store.lookup("  ls  ") is not None


def test_lookup_unknown_returns_none(store):
    assert store.lookup("totally_unknown_cmd_xyz") is None


def test_lookup_empty_string_returns_none(store):
    assert store.lookup("") is None


# ── TldrStore.known_commands ──────────────────────────────────────

def test_known_commands_returns_frozenset(store):
    known = store.known_commands()
    assert isinstance(known, frozenset)


def test_known_commands_contains_all_entries(store):
    known = store.known_commands()
    assert "tar" in known
    assert "ls" in known
    assert "git" in known


def test_known_commands_does_not_contain_unknown(store):
    assert "totally_unknown_cmd_xyz" not in store.known_commands()


# ── TldrStore.size ────────────────────────────────────────────────

def test_size_matches_catalog(store):
    assert store.size() == 3


# ── Examples ─────────────────────────────────────────────────────

def test_examples_are_tldr_example_objects(store):
    page = store.lookup("tar")
    assert page is not None
    assert len(page.examples) == 2
    ex = page.examples[0]
    assert isinstance(ex, TldrExample)
    assert ex.description
    assert ex.command


def test_command_with_no_examples(store):
    page = store.lookup("git")
    assert page is not None
    assert page.examples == []


# ── Lazy loading (cached) ─────────────────────────────────────────

def test_lazy_loading_caches_result(store):
    """Second call should return the same dict object (cached)."""
    _ = store.lookup("tar")
    pages1 = store._pages
    _ = store.lookup("ls")
    pages2 = store._pages
    assert pages1 is pages2


# ── Placeholder stripping (done at build time) ────────────────────

def test_no_double_braces_in_real_catalog():
    """Verify build script stripped {{ }} — no raw placeholder markers in catalog."""
    real_store = TldrStore()
    # Sample a few well-known commands
    for cmd in ("tar", "ls", "curl", "git"):
        page = real_store.lookup(cmd)
        if page is None:
            continue
        for ex in page.examples:
            assert "{{" not in ex.command, (
                f"{cmd}: example still contains {{{{ marker: {ex.command!r}"
            )
            assert "}}" not in ex.command, (
                f"{cmd}: example still contains }}}} marker: {ex.command!r}"
            )


# ── Real catalog (bundled data) ───────────────────────────────────

def test_real_catalog_loads():
    """Smoke test: the bundled tldr_catalog.json loads without error.

    The catalog includes common + linux + osx platforms (~6600 commands).
    Common cross-platform commands (ls, git, tar) live in the 'common' bucket
    and must be present.
    """
    real_store = TldrStore()
    assert real_store.size() > 1000
    assert real_store.lookup("ls") is not None
    assert real_store.lookup("git") is not None
    assert real_store.lookup("tar") is not None
    assert real_store.lookup("lsblk") is not None


def test_real_catalog_known_commands_is_frozenset():
    real_store = TldrStore()
    known = real_store.known_commands()
    assert isinstance(known, frozenset)
    assert len(known) > 1000


# ── Locale-aware lookup ───────────────────────────────────────────

def test_locale_lookup_falls_back_to_english(tmp_path):
    """When no locale overlay exists, lookup() returns English page."""
    p = tmp_path / "tldr_catalog.json"
    _write_catalog(p, {"ls": {"desc": "List files.", "examples": [{"desc": "List", "cmd": "ls"}]}})
    store = TldrStore(catalog_path=p)

    # No de/fr catalog next to this path — must fall back to English
    page = store.lookup("ls", locale="de")
    assert page is not None
    assert page.description == "List files."


def test_locale_lookup_returns_translated_page(tmp_path):
    """When locale overlay exists, its page is preferred over English."""
    en_path = tmp_path / "tldr_catalog.json"
    de_path = tmp_path / "tldr_catalog_de.json"
    _write_catalog(en_path, {"ls": {"desc": "List files.", "examples": []}})
    _write_catalog(de_path, {"ls": {"desc": "Dateien auflisten.", "examples": []}})

    store = TldrStore(catalog_path=en_path)
    page = store.lookup("ls", locale="de")
    assert page is not None
    assert page.description == "Dateien auflisten."


def test_locale_lookup_en_unchanged(tmp_path):
    """locale='en' always returns the English page."""
    en_path = tmp_path / "tldr_catalog.json"
    _write_catalog(en_path, {"ls": {"desc": "List files.", "examples": []}})

    store = TldrStore(catalog_path=en_path)
    page = store.lookup("ls", locale="en")
    assert page is not None
    assert page.description == "List files."


def test_locale_lookup_default_is_english():
    """lookup() without a locale argument returns English."""
    real_store = TldrStore()
    page = real_store.lookup("ls")
    assert page is not None
    en_page = real_store.lookup("ls", locale="en")
    assert page.description == en_page.description


def test_real_de_catalog_loads():
    """Smoke test: DE locale overlay loads and has reasonable coverage."""
    real_store = TldrStore()
    real_store._ensure_locale("de")
    de_pages = real_store._locale_pages.get("de", {})
    assert len(de_pages) > 100


def test_real_fr_catalog_loads():
    """Smoke test: FR locale overlay loads and has reasonable coverage."""
    real_store = TldrStore()
    real_store._ensure_locale("fr")
    fr_pages = real_store._locale_pages.get("fr", {})
    assert len(fr_pages) > 100


def test_unknown_locale_returns_english():
    """An unsupported locale falls back to English gracefully."""
    real_store = TldrStore()
    page_unknown = real_store.lookup("ls", locale="xx")
    page_en = real_store.lookup("ls", locale="en")
    assert page_unknown is not None
    assert page_unknown.description == page_en.description
