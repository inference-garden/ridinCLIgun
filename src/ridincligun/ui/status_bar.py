"""Status bar widget for ridinCLIgun.

Minimal tags at the bottom of the screen. Reads from AppState.
"""

from __future__ import annotations

from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip
from textual.widget import Widget


class StatusBar(Widget):
    """Single-line status bar at the bottom of the app."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: #0f3460;
        color: #e0e0e0;
        dock: bottom;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._ai_enabled = False
        self._secret_mode = False
        self._shell_name = "zsh"
        self._leader_active = False
        self._ai_status: str = ""  # "", "offline", "error"

    def update_state(
        self,
        ai_enabled: bool | None = None,
        secret_mode: bool | None = None,
        shell_name: str | None = None,
        leader_active: bool | None = None,
        ai_status: str | None = None,
    ) -> None:
        """Update displayed state and refresh."""
        if ai_enabled is not None:
            self._ai_enabled = ai_enabled
        if secret_mode is not None:
            self._secret_mode = secret_mode
        if shell_name is not None:
            self._shell_name = shell_name
        if leader_active is not None:
            self._leader_active = leader_active
        if ai_status is not None:
            self._ai_status = ai_status
        self.refresh()

    def render_line(self, y: int) -> Strip:
        """Render the single status line."""
        if y != 0:
            return Strip.blank(self.size.width)

        width = self.size.width
        dim = Style.parse("dim")
        secret_style = Style.parse("bold yellow") if self._secret_mode else Style.parse("dim")
        secret_text = "on" if self._secret_mode else "off"

        # AI status: show connection state when relevant
        if self._ai_status == "offline":
            ai_style = Style.parse("bold red")
            ai_text = "offline"
        elif self._ai_status == "error":
            ai_style = Style.parse("bold red")
            ai_text = "error"
        elif self._ai_enabled:
            ai_style = Style.parse("bold green")
            ai_text = "on"
        else:
            ai_style = Style.parse("dim red")
            ai_text = "off"

        left_segments = [
            Segment("  AI: ", dim),
            Segment(ai_text, ai_style),
            Segment("  ◆  ", dim),
            Segment("Secret: ", dim),
            Segment(secret_text, secret_style),
        ]

        # Show leader key waiting indicator in the right section
        if self._leader_active:
            right_segments = [
                Segment("⌨ Ctrl+G...", Style.parse("bold yellow")),
                Segment("   ", dim),
                Segment(self._shell_name, Style.parse("dim cyan")),
                Segment("  ", dim),
            ]
        else:
            right_segments = [
                Segment("Ctrl+G → help", dim),
                Segment("   ", dim),
                Segment(self._shell_name, Style.parse("dim cyan")),
                Segment("  ", dim),
            ]

        left_len = sum(len(s.text) for s in left_segments)
        right_len = sum(len(s.text) for s in right_segments)
        padding = max(1, width - left_len - right_len)

        segments = [*left_segments, Segment(" " * padding, dim), *right_segments]
        return Strip(segments, width)
