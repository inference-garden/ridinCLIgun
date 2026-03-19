"""Shortcut bindings for ridinCLIgun.

Implements the Ctrl+G leader key state machine and all app-level key routing.
The leader pattern: press Ctrl+G, then a follow-up key within a timeout.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class LeaderAction(Enum):
    """Actions available through the Ctrl+G leader key."""

    REVIEW = auto()       # R — review current command
    HELP = auto()         # H — show help overlay
    RESTART_SHELL = auto()  # X — restart shell
    DEBUG = auto()        # D — show provider debug
    TOGGLE_AI = auto()    # A — toggle AI on/off
    TOGGLE_SECRET = auto()  # S — toggle Secret Mode
    COPY = auto()         # C — copy (fallback if Cmd+C unavailable)
    PASTE = auto()        # V — paste (fallback if Cmd+V unavailable)
    QUIT = auto()         # Q — quit (fallback if Cmd+Q unavailable)
    INSERT_SUGGESTION = auto()  # I — insert AI suggestion into shell
    CMD_HELP = auto()     # ? — show --help for current command
    MODEL_SELECT = auto()  # M — model/provider selection


# Map follow-up keys to actions
LEADER_MAP: dict[str, LeaderAction] = {
    "r": LeaderAction.REVIEW,
    "h": LeaderAction.HELP,
    "x": LeaderAction.RESTART_SHELL,
    "d": LeaderAction.DEBUG,
    "a": LeaderAction.TOGGLE_AI,
    "s": LeaderAction.TOGGLE_SECRET,
    "c": LeaderAction.COPY,
    "v": LeaderAction.PASTE,
    "q": LeaderAction.QUIT,
    "i": LeaderAction.INSERT_SUGGESTION,
    "?": LeaderAction.CMD_HELP,
    "question_mark": LeaderAction.CMD_HELP,
    "m": LeaderAction.MODEL_SELECT,
}

# Timeout in seconds for the follow-up key after Ctrl+G
LEADER_TIMEOUT: float = 2.0


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
