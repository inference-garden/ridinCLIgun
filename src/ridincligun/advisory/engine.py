# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Advisory engine (local pattern matching + tldr + typo)

"""Local advisory engine.

Matches commands against the catalog, looks up tldr documentation, and
detects typos in the command name — all offline, synchronous, no network.

v0.4 (4.6): extended with TldrStore and TypoDetector.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable

from ridincligun.advisory.catalog import CommandCatalog, load_catalog
from ridincligun.advisory.models import ReviewResult, Warning
from ridincligun.advisory.tldr_store import (
    TldrExample,
    TldrPage,
    TldrStore,
    get_default_store,
)
from ridincligun.advisory.typo_detector import TypoDetector

# A command keyword (base command or subcommand word): lowercase, starts
# alphanumeric, no flag dash-prefix.  Used both to find the subcommand run
# and to tell keywords apart from arguments/placeholders.
_KEYWORD_RE = re.compile(r"^[a-z0-9][a-z0-9.+_-]*$")

# tldr stores subcommand pages dash-joined ("git-commit"); the deepest bundled
# key is 4 dashes ("docker-buildx-du") = 5 segments.  Cap the join attempts there.
_MAX_VARIANT_SEGMENTS = 5


def _tokenize(command: str) -> list[str]:
    """Split a command into tokens, dropping leading ``VAR=value`` assignments."""
    command = command.strip()
    if not command:
        return []
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    # Drop leading VAR=value tokens (e.g. "FOO=bar git commit").
    idx = 0
    for token in tokens:
        if "=" in token and not token.startswith("-"):
            idx += 1
        else:
            break
    return tokens[idx:]


def _first_token(command: str) -> str:
    """Extract the command name (first token), stripping env var assignments."""
    tokens = _tokenize(command)
    return tokens[0].lower() if tokens else ""


def _resolve_variant(
    tokens: list[str], lookup: Callable[[str], TldrPage | None]
) -> tuple[TldrPage | None, str, int]:
    """Resolve the longest matching tldr page for a command's leading tokens.

    Tries the dash-joined subcommand keys from longest to shortest (e.g.
    ``git commit`` → ``git-commit`` before ``git``), so the page narrows to the
    typed variant when one exists and falls back to the base command otherwise.
    The bundled catalog bounds correctness: a join that no page uses simply
    misses and we shrink (``git checkout main`` → no ``git-checkout-main`` →
    ``git-checkout``).

    Returns ``(page, matched_key, consumed)`` where *consumed* is how many
    leading tokens formed the matched key (``> 1`` means a real subcommand
    refinement).  ``page`` is ``None`` only when even the base command is unknown.
    """
    if not tokens:
        return None, "", 0
    candidates: list[str] = []
    for token in tokens[:_MAX_VARIANT_SEGMENTS]:
        low = token.lower()
        if _KEYWORD_RE.match(low):
            candidates.append(low)
        else:
            break
    if not candidates:
        base = tokens[0].lower()
        return lookup(base), base, 1
    for length in range(len(candidates), 0, -1):
        key = "-".join(candidates[:length])
        page = lookup(key)
        if page is not None:
            return page, key, length
    return None, candidates[0], 1


def _is_keyword(token: str) -> bool:
    """True if *token* is a plain command keyword, not a flag/arg/placeholder."""
    if not _KEYWORD_RE.match(token.lower()):
        return False
    if token != token.lower():  # uppercase => a placeholder like FILE or GPG
        return False
    if "_" in token or "..." in token or any(c in token for c in "/.\"'"):
        return False
    return True


def _flag_base(token: str) -> str:
    """Normalize a flag token to its bare form (``--msg=x`` → ``--msg``)."""
    return token.split("=", 1)[0].lower()


def _extract_signals(tokens: list[str]) -> tuple[set[str], set[str]]:
    """Collect (flags, keywords) from *typed* tokens for relevance ranking."""
    flags: set[str] = set()
    words: set[str] = set()
    for token in tokens:
        if token.startswith("-") and len(token) > 1:
            flags.add(_flag_base(token))
        elif _is_keyword(token):
            words.add(token.lower())
    return flags, words


def _example_signals(command: str) -> tuple[set[str], set[str]]:
    """Collect (flags, keywords) from a tldr example template.

    Handles the bundled catalog's ``-m|--message`` alternative-flag notation
    (short ``|`` long) and ignores expanded placeholders (``path/to/file``,
    ``"message"``, ``message_text``).
    """
    flags: set[str] = set()
    words: set[str] = set()
    for token in command.split():
        if token.startswith("-") and "|" in token:
            for part in token.split("|"):
                if part.startswith("-"):
                    flags.add(_flag_base(part))
        elif token.startswith("-") and len(token) > 1:
            flags.add(_flag_base(token))
        elif _is_keyword(token):
            words.add(token.lower())
    return flags, words


def _rank_examples(
    page: TldrPage, typed_flags: set[str], typed_words: set[str]
) -> list[tuple[TldrExample, bool]]:
    """Reorder a page's examples so flag/word matches come first.

    Deterministic: score = ``2·|flag overlap| + |word overlap|``; a stable
    descending sort keeps the catalog order for ties.  With no typed signals
    the order is unchanged and nothing is marked as a match (today's behavior).
    """
    scored: list[tuple[TldrExample, int]] = []
    for ex in page.examples:
        ex_flags, ex_words = _example_signals(ex.command)
        score = 2 * len(typed_flags & ex_flags) + len(typed_words & ex_words)
        scored.append((ex, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return [(ex, score > 0) for ex, score in scored]


def _flag_display(command: str, matched: set[str]) -> str:
    """Return the canonical ``-x, --long`` display for matched flags in *command*."""
    for token in command.split():
        if not token.startswith("-"):
            continue
        variants = [part for part in token.split("|") if part.startswith("-")]
        if {_flag_base(v) for v in variants} & matched:
            return ", ".join(_flag_base(v) for v in variants)
    return ", ".join(sorted(matched))


def _flag_notes(page: TldrPage, typed_flags: set[str], limit: int = 3) -> list[tuple[str, str]]:
    """Explain the typed flags the resolved page documents.

    Source is the page's own examples only — no external dictionary, no network.
    Returns up to *limit* ``(flag_display, description)`` pairs.
    """
    if not typed_flags:
        return []
    notes: list[tuple[str, str]] = []
    seen: set[str] = set()
    for ex in page.examples:
        ex_flags, _ = _example_signals(ex.command)
        matched = typed_flags & ex_flags
        if not matched:
            continue
        display = _flag_display(ex.command, matched)
        if display in seen:
            continue
        seen.add(display)
        notes.append((display, ex.description))
        if len(notes) >= limit:
            break
    return notes


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
        catalog_names = frozenset(p.family_id.split("_")[0] for p in self._catalog.patterns)
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

        # ── 2. tldr lookup (variant-aware) + typo detection ──────
        tokens = _tokenize(command)
        tldr_page: TldrPage | None = None
        matched_command: str | None = None
        ranked_examples: list[tuple[TldrExample, bool]] | None = None
        flag_notes: list[tuple[str, str]] | None = None
        typo_suggestion = None

        if tokens:
            # Layer 1 — narrow to the longest matching subcommand page.
            # Rank on the language-independent template; lookup() handles the
            # locale overlay + English fallback for the displayed text.
            tldr_page, matched_key, consumed = _resolve_variant(
                tokens, lambda key: self._tldr.lookup(key, locale=locale)
            )
            if consumed > 1:
                matched_command = matched_key

            if tldr_page is not None and tldr_page.examples:
                # Layers 2 + 3 — rank examples and explain typed flags, using
                # only the tokens *after* the resolved command/subcommand words.
                typed_flags, typed_words = _extract_signals(tokens[consumed:])
                ranked_examples = _rank_examples(tldr_page, typed_flags, typed_words)
                flag_notes = _flag_notes(tldr_page, typed_flags)
            elif tldr_page is None and self._typo is not None:
                # Unknown command name → suggest the closest known command.
                typo_suggestion = self._typo.suggest(_first_token(command))

        return ReviewResult(
            command=command,
            warnings=warnings,
            tldr_page=tldr_page,
            typo_suggestion=typo_suggestion,
            matched_command=matched_command,
            ranked_examples=ranked_examples,
            flag_notes=flag_notes,
        )
