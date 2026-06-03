# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Leader-key state and actions

"""Shortcut bindings for ridinCLIgun.

Implements the Ctrl+G leader key state machine for actions that don't have
a dedicated function key. Frequent actions (Help, Review, Insert, Toggle AI,
Toggle Secret) are bound to F1–F5 directly in app.py BINDINGS.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class LeaderAction(Enum):
    """Actions available through the Ctrl+G leader key.

    Frequent actions (Review/Insert/Help/AI/Secret) live on F1–F5.
    The leader is reserved for less frequent, modal, or destructive actions.
    """

    RESTART_SHELL = auto()  # X — restart shell
    DEBUG = auto()  # D — show provider debug
    QUIT = auto()  # Q — quit ridinCLIgun
    MODEL_SELECT = auto()  # M — model/provider selection
    HISTORY = auto()  # H — open review history (was K in v0.4)
    SETTINGS = auto()  # G — open settings menu
    COPY = auto()  # C — copy current selection to clipboard
    PASTE = auto()  # V — paste clipboard (routed through secret detector)


# Map follow-up keys to actions
LEADER_MAP: dict[str, LeaderAction] = {
    "x": LeaderAction.RESTART_SHELL,
    "d": LeaderAction.DEBUG,
    "q": LeaderAction.QUIT,
    "m": LeaderAction.MODEL_SELECT,
    "h": LeaderAction.HISTORY,
    "g": LeaderAction.SETTINGS,
    "c": LeaderAction.COPY,
    "v": LeaderAction.PASTE,
}


@dataclass
class LeaderState:
    """Tracks the Ctrl+G leader key state machine.

    States:
    - inactive: normal mode, keys go to shell
    - waiting: Ctrl+G was pressed, waiting for follow-up key
    """

    active: bool = False
    _timer_handle: object | None = None

    def activate(self) -> None:
        """Enter leader mode (Ctrl+G was pressed)."""
        self.active = True

    def deactivate(self) -> None:
        """Exit leader mode."""
        self.active = False
        self._timer_handle = None

    def resolve(self, key: str) -> LeaderAction | None:
        """Try to resolve a follow-up key to an action.

        Returns the action if matched, None if no match.
        Always deactivates leader mode afterward.
        """
        action = LEADER_MAP.get(key.lower())
        self.deactivate()
        return action
