# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Pane divider widget

"""Draggable divider widget between shell and advisory panes.

A thin 1-character-wide vertical bar that can be dragged with the mouse
to resize the panes. Subtle but visible.
"""

from __future__ import annotations

from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.message import Message
from textual.strip import Strip
from textual.widget import Widget

# Visual styles
_NORMAL_STYLE = Style(color="#555577", bgcolor="#2a2a40")
_HOVER_STYLE = Style(color="#8888aa", bgcolor="#3a3a55")
_DRAG_STYLE = Style(color="#aaaacc", bgcolor="#4a4a66")
_DIVIDER_CHAR = "│"


class PaneDivider(Widget, can_focus=False):
    """A thin draggable vertical divider between panes."""

    class DividerDragged(Message):
        """Posted when the divider is dragged. delta_x is the horizontal movement."""

        def __init__(self, delta_x: int) -> None:
            super().__init__()
            self.delta_x = delta_x

    DEFAULT_CSS = """
    PaneDivider {
        width: 1;
        height: 100%;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._dragging = False
        self._hover = False
        self._drag_start_x: int = 0
        self._style = _NORMAL_STYLE

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Start drag on mouse down."""
        if event.button == 1:
            self._dragging = True
            self._drag_start_x = event.screen_x
            self._style = _DRAG_STYLE
            self.capture_mouse()
            self.refresh()
            event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Track drag movement."""
        if self._dragging:
            delta = event.screen_x - self._drag_start_x
            if delta != 0:
                self.post_message(self.DividerDragged(delta))
                self._drag_start_x = event.screen_x
            event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        """End drag on mouse release."""
        if self._dragging and event.button == 1:
            self._dragging = False
            self._style = _HOVER_STYLE if self._hover else _NORMAL_STYLE
            self.release_mouse()
            self.refresh()
            event.stop()

    def on_enter(self, _event: events.Enter) -> None:
        """Highlight on hover."""
        self._hover = True
        if not self._dragging:
            self._style = _HOVER_STYLE
            self.refresh()

    def on_leave(self, _event: events.Leave) -> None:
        """Reset on mouse leave."""
        self._hover = False
        if not self._dragging:
            self._style = _NORMAL_STYLE
            self.refresh()

    def render_line(self, y: int) -> Strip:
        """Render one line of the divider."""
        return Strip([Segment(_DIVIDER_CHAR, self._style)], 1)
