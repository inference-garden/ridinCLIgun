# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — tldr page store

"""Offline tldr-pages store.

Loads the bundled ``data/tldr_catalog.json`` (MIT-licensed community command
documentation, common + Linux + macOS subset) and exposes fast locale-aware
lookups.

The English catalog is loaded lazily on first access; per-locale overlay
catalogs (``tldr_catalog_de.json``, ``tldr_catalog_fr.json``) are loaded on
demand when a non-English locale is requested.

Lookup falls back to English if a translated page is not available for the
requested locale — coverage is ~800 pages per locale vs. ~6600 in English.

All operations are synchronous and in-memory — no network, no disk I/O
after the first load per locale.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

# ── Data types ────────────────────────────────────────────────────

@dataclass(frozen=True)
class TldrExample:
    """One usage example from a tldr page."""
    description: str   # human description of what the example does
    command: str       # the command with {{placeholders}}


@dataclass(frozen=True)
class TldrPage:
    """A parsed tldr page for a single command."""
    command: str
    description: str
    examples: list[TldrExample]


# ── Store ─────────────────────────────────────────────────────────

class TldrStore:
    """Offline tldr page store — loads once per locale, serves forever."""

    def __init__(self, catalog_path: Path | None = None) -> None:
        # catalog_path: explicit path to the English catalog (for tests).
        # When None the bundled data file is used.
        self._catalog_path = catalog_path
        self._pages_en: dict[str, TldrPage] | None = None
        # locale_code → dict of translated pages (lazy, per locale)
        self._locale_pages: dict[str, dict[str, TldrPage]] = {}

    # ── Internal helpers ─────────────────────────────────────────

    def _read_text(self, filename: str) -> str:
        """Return the text content of a catalog file, trying package data then repo layout."""
        if self._catalog_path is not None:
            # Test mode: explicit catalog_path for EN; locale variants sit next to it.
            path = (
                self._catalog_path
                if filename == "tldr_catalog.json"
                else self._catalog_path.parent / filename
            )
            return path.read_text(encoding="utf-8")
        # Installed package data (pip install / hatch build)
        try:
            ref = resources.files("ridincligun") / "data" / filename
            return ref.read_text(encoding="utf-8")
        except (FileNotFoundError, TypeError):
            pass
        # Development layout: <repo>/data/<filename>
        repo = Path(__file__).resolve().parents[3] / "data" / filename
        return repo.read_text(encoding="utf-8")

    def _load_pages(self, filename: str) -> dict[str, TldrPage]:
        """Parse a JSON catalog file into a TldrPage dict."""
        text = self._read_text(filename)
        data: dict[str, dict] = json.loads(text)
        pages: dict[str, TldrPage] = {}
        for command, entry in data.items():
            examples = [
                TldrExample(description=ex["desc"], command=ex["cmd"])
                for ex in entry.get("examples", [])
            ]
            pages[command] = TldrPage(
                command=command,
                description=entry.get("desc", ""),
                examples=examples,
            )
        return pages

    def _ensure_en(self) -> dict[str, TldrPage]:
        if self._pages_en is None:
            self._pages_en = self._load_pages("tldr_catalog.json")
        return self._pages_en

    def _ensure_locale(self, locale: str) -> dict[str, TldrPage]:
        """Load and cache the locale overlay; returns empty dict if unavailable."""
        if locale in self._locale_pages:
            return self._locale_pages[locale]
        filename = f"tldr_catalog_{locale}.json"
        try:
            pages = self._load_pages(filename)
        except (FileNotFoundError, OSError):
            pages = {}
        self._locale_pages[locale] = pages
        return pages

    # ── Public API ───────────────────────────────────────────────

    def lookup(self, command: str, locale: str = "en") -> TldrPage | None:
        """Return the tldr page for *command* in *locale*, with English fallback.

        If a translated page exists in the requested locale it is returned;
        otherwise the English page is used.  Returns ``None`` if the command
        is unknown in both catalogs.
        """
        cmd = command.strip().lower()
        if not cmd:
            return None

        if locale and locale != "en":
            locale_pages = self._ensure_locale(locale)
            page = locale_pages.get(cmd)
            if page is not None:
                return page

        return self._ensure_en().get(cmd)

    def known_commands(self) -> frozenset[str]:
        """Return the set of all command names in the English catalog.

        Used to seed the typo detector — language-independent.
        """
        return frozenset(self._ensure_en().keys())

    def size(self) -> int:
        """Number of commands in the English catalog."""
        return len(self._ensure_en())

    # Backward-compat alias accessed by tests written against the old API
    @property
    def _pages(self) -> dict[str, TldrPage] | None:
        return self._pages_en


# ── Module-level singleton ────────────────────────────────────────
# Shared instance used by AdvisoryEngine.  Tests may construct their own.

_default_store: TldrStore | None = None


def get_default_store() -> TldrStore:
    global _default_store
    if _default_store is None:
        _default_store = TldrStore()
    return _default_store
