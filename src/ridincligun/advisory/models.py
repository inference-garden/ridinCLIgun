# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Risk levels and warning models

"""Data models for the advisory system.

Simple dataclasses — no logic, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RiskLevel(Enum):
    """Risk severity levels for command warnings."""

    SAFE = "safe"          # No known risk
    CAUTION = "caution"    # Mild heads-up (yellow/dim)
    WARNING = "warning"    # Significant risk (amber/bold)
    DANGER = "danger"      # Critical risk (red/bold)


@dataclass(frozen=True)
class Warning:
    """A single warning matched against a command."""

    risk: RiskLevel
    summary: str
    suggestion: str
    family: str        # e.g. "rm", "curl_pipe"
    pattern_source: str  # the regex that matched


@dataclass
class ReviewResult:
    """The combined result of analyzing a command."""

    command: str
    warnings: list[Warning] = field(default_factory=list)

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
