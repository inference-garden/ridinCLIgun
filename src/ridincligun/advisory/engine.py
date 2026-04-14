# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Advisory engine (local pattern matching + tldr + typo)

"""Local advisory engine.

Matches commands against the catalog, looks up tldr documentation, and
detects typos in the command name — all offline, synchronous, no network.

v0.4 (4.6): extended with TldrStore and TypoDetector.
"""

from __future__ import annotations

import shlex

from ridincligun.advisory.catalog import CommandCatalog, load_catalog
from ridincligun.advisory.models import ReviewResult, Warning
from ridincligun.advisory.tldr_store import TldrStore, get_default_store
from ridincligun.advisory.typo_detector import TypoDetector


def _first_token(command: str) -> str:
    """Extract the command name (first token), stripping env var assignments."""
    command = command.strip()
    if not command:
        return ""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    # Skip leading VAR=value tokens (e.g. "FOO=bar git commit")
    for token in tokens:
        if "=" not in token or token.startswith("-"):
            return token.lower()
    return tokens[0].lower() if tokens else ""


class AdvisoryEngine:
    """Stateless local command analyzer.

    Combines three offline data sources per keystroke:
    1. Regex catalog  — risk warnings for dangerous patterns
    2. TldrStore      — usage examples for the recognized command
    3. TypoDetector   — "Did you mean X?" for unknown command names
    """

    def __init__(
        self,
        catalog: CommandCatalog | None = None,
        tldr_store: TldrStore | None = None,
        typo_detector: TypoDetector | None = None,
    ) -> None:
        self._catalog = catalog or load_catalog()
        self._tldr = tldr_store if tldr_store is not None else get_default_store()
        self._typo = typo_detector  # may be None until set_extra_commands() called

    def set_extra_commands(self, extra: frozenset[str]) -> None:
        """Extend the typo dictionary with PATH-scanned binaries.

        Called once at app startup after the PATH scan completes.
        Merges tldr known commands + catalog families + PATH binaries.
        """
        base = self._tldr.known_commands()
        catalog_names = frozenset(
            p.family_id.split("_")[0]
            for p in self._catalog.patterns
        )
        self._typo = TypoDetector(base | catalog_names | extra)

    def analyze(self, command: str, locale: str = "en") -> ReviewResult:
        """Analyze a command string. Returns warnings, tldr page, and typo hint.

        Parameters
        ----------
        command:
            Raw command string from the input field.
        locale:
            Active UI locale (e.g. ``"de"``, ``"fr"``, ``"en"``).  Used to
            select a translated tldr page when available; falls back to
            English automatically.

        Returns a ReviewResult with:
        - ``warnings``        — matched catalog patterns, sorted by severity
        - ``tldr_page``       — tldr docs for the command name (if found)
        - ``typo_suggestion`` — closest known command (if name unrecognised)
        """
        command = command.strip()
        if not command:
            return ReviewResult(command=command)

        # ── 1. Risk pattern matching ──────────────────────────────
        warnings: list[Warning] = []
        seen_families: set[str] = set()

        for pattern in self._catalog.patterns:
            if pattern.regex.search(command):
                if pattern.family_id in seen_families:
                    continue
                seen_families.add(pattern.family_id)
                warnings.append(
                    Warning(
                        risk=pattern.risk,
                        summary=pattern.summary,
                        suggestion=pattern.suggestion,
                        family=pattern.family_id,
                        pattern_source=pattern.regex.pattern,
                    )
                )

        risk_order = {"danger": 0, "warning": 1, "caution": 2, "safe": 3}
        warnings.sort(key=lambda w: risk_order.get(w.risk.value, 99))

        # ── 2. tldr lookup + typo detection ──────────────────────
        cmd_name = _first_token(command)
        tldr_page = None
        typo_suggestion = None

        if cmd_name:
            tldr_page = self._tldr.lookup(cmd_name, locale=locale)

            if tldr_page is None and self._typo is not None:
                # Only suggest typos for names we actually know
                # (suppress on very short tokens still being typed)
                typo_suggestion = self._typo.suggest(cmd_name)

        return ReviewResult(
            command=command,
            warnings=warnings,
            tldr_page=tldr_page,
            typo_suggestion=typo_suggestion,
        )
