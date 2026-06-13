# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Risk levels and warning models

"""Data models for the advisory system.

Simple dataclasses — no logic, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# Re-export tldr types so callers only need to import from models
from ridincligun.advisory.tldr_store import TldrExample, TldrPage  # noqa: F401


class RiskLevel(Enum):
    """Risk severity levels for command warnings."""

    SAFE = "safe"  # No known risk
    CAUTION = "caution"  # Mild heads-up (yellow/dim)
    WARNING = "warning"  # Significant risk (amber/bold)
    DANGER = "danger"  # Critical risk (red/bold)


@dataclass(frozen=True)
class Warning:
    """A single warning matched against a command."""

    risk: RiskLevel
    summary: str
    suggestion: str
    family: str  # e.g. "rm", "curl_pipe"
    pattern_source: str  # the regex that matched


@dataclass
class ReviewResult:
    """The combined result of analyzing a command.

    Fields added in v0.4 (4.6):
    - ``tldr_page``: tldr documentation for the command, if found.
    - ``typo_suggestion``: suggested correction when the command name is
      unrecognised and a close match exists (Levenshtein ≤ 2).

    Offline-help refinement fields (v0.4.6, S4-5) — all optional and
    back-compatible; populated only when a tldr page is resolved:
    - ``matched_command``: the resolved variant key when the lookup narrowed
      to a subcommand page (e.g. ``"git-commit"``), else ``None`` for the base
      command.  Lets the UI show *which* variant is being shown.
    - ``ranked_examples``: the page's examples reordered so the ones matching
      the typed flags/words come first, paired with an ``is_match`` flag for
      highlighting.  ``None`` when there is no page.
    - ``flag_notes``: ``(flag_display, description)`` pairs explaining the typed
      flags that the resolved page documents.  Empty/``None`` when nothing matches.
    """

    command: str
    warnings: list[Warning] = field(default_factory=list)
    tldr_page: TldrPage | None = field(default=None)
    typo_suggestion: str | None = field(default=None)
    matched_command: str | None = field(default=None)
    ranked_examples: list[tuple[TldrExample, bool]] | None = field(default=None)
    flag_notes: list[tuple[str, str]] | None = field(default=None)

    @property
    def highest_risk(self) -> RiskLevel:
        """Return the highest risk level among all warnings."""
        if not self.warnings:
            return RiskLevel.SAFE
        risk_order = [RiskLevel.SAFE, RiskLevel.CAUTION, RiskLevel.WARNING, RiskLevel.DANGER]
        max_idx = max(risk_order.index(w.risk) for w in self.warnings)
        return risk_order[max_idx]

    @property
    def is_safe(self) -> bool:
        return self.highest_risk == RiskLevel.SAFE
