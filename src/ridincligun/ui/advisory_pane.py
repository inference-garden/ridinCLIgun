"""Advisory pane widget for ridinCLIgun.

Displays warnings, AI reviews, and status information in the right pane.
Reads state only — never mutates it.
"""

from __future__ import annotations

from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip
from textual.widget import Widget


class AdvisoryPane(Widget, can_focus=True):
    """Right-side advisory panel. Placeholder for Step 1, enriched in Step 3."""

    DEFAULT_CSS = """
    AdvisoryPane {
        background: #16213e;
        color: #a0a0c0;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._lines: list[tuple[str, str]] = []  # (text, style_str)
        self._set_welcome()

    def _set_welcome(self) -> None:
        """Show the initial welcome message."""
        self._lines = [
            ("", ""),
            ("  ridinCLIgun", "bold cyan"),
            ("", ""),
            ("  Your shell companion.", "dim"),
            ("  Advises, never acts.", "dim"),
            ("", ""),
            ("  Ctrl+G → H  show help", "dim green"),
        ]

    def set_content(self, lines: list[tuple[str, str]]) -> None:
        """Replace the advisory content. Each item is (text, style_string)."""
        self._lines = lines
        self.refresh()

    def clear(self) -> None:
        """Reset to welcome message."""
        self._set_welcome()
        self.refresh()

    def render_line(self, y: int) -> Strip:
        """Render a single line of advisory content."""
        width = self.size.width
        if y < len(self._lines):
            text, style_str = self._lines[y]
            style = Style.parse(style_str) if style_str else Style()
            padded = text.ljust(width)[:width]
            return Strip([Segment(padded, style)], width)
        return Strip.blank(width)
