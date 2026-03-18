"""Application state for ridinCLIgun.

Single source of truth. Widgets read this; only app.py mutates it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class Phase(Enum):
    """Visible user-facing phases. Keep this list small."""

    TYPING = auto()
    REVIEW_LOADING = auto()
    REVIEW_READY = auto()
    SHELL_UNAVAILABLE = auto()


class RiskLevel(Enum):
    """Risk levels for command classification."""

    SAFE = "safe"
    CAUTION = "caution"
    DANGER = "danger"


@dataclass
class Warning:
    """A single advisory warning about a command."""

    severity: RiskLevel
    title: str
    detail: str
    suggestion: str | None = None


@dataclass
class ReviewResult:
    """Combined result of local + AI review."""

    local_warnings: list[Warning] = field(default_factory=list)
    ai_review: str | None = None
    ai_error: str | None = None


@dataclass
class AppState:
    """Central application state. Mutated only by app.py."""

    phase: Phase = Phase.TYPING
    ai_enabled: bool = False
    secret_mode: bool = False
    secrets_detected: bool = False  # True when live input contains likely secrets
    current_input: str = ""
    last_review: ReviewResult | None = None
    leader_active: bool = False
    shell_name: str = "zsh"
    split_ratio: tuple[int, int] = (3, 2)  # 60/40 default as fr units
