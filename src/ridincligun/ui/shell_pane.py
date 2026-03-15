"""Shell pane widget for ridinCLIgun.

Wraps a PTY process with pyte terminal emulation and renders into a Textual widget.
All keyboard input when focused goes to the PTY. The shell is real.
"""

from __future__ import annotations

import asyncio

import pyte
from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.message import Message
from textual.strip import Strip
from textual.widget import Widget

from ridincligun.shell.pty_process import PtyProcess

# Map pyte color names to Rich color names
_PYTE_COLOR_MAP: dict[str, str] = {
    "black": "black",
    "red": "red",
    "green": "green",
    "brown": "yellow",
    "blue": "blue",
    "magenta": "magenta",
    "cyan": "cyan",
    "white": "white",
}


def _pyte_color_to_rich(color: str) -> str | None:
    """Convert a pyte color string to a Rich color string. Returns None for default."""
    if not color or color == "default":
        return None
    if color in _PYTE_COLOR_MAP:
        return _PYTE_COLOR_MAP[color]
    # Numeric 256-color codes
    try:
        code = int(color)
        return f"color({code})"
    except (ValueError, TypeError):
        return None


def _build_style(char: pyte.screens.Char) -> Style:
    """Build a Rich Style from a pyte character."""
    fg = _pyte_color_to_rich(char.fg)
    bg = _pyte_color_to_rich(char.bg)
    return Style(
        color=fg,
        bgcolor=bg,
        bold=char.bold or None,
        italic=char.italics or None,
        underline=char.underscore or None,
        reverse=char.reverse or None,
    )


class ShellPane(Widget, can_focus=True):
    """A terminal emulator widget backed by a real PTY."""

    DEFAULT_CSS = """
    ShellPane {
        background: #1a1a2e;
        color: #e0e0e0;
    }
    """

    class InputChanged(Message):
        """Posted when the detected current command input changes."""

        def __init__(self, command: str) -> None:
            super().__init__()
            self.command = command

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pty = PtyProcess()
        self._screen = pyte.Screen(80, 24)
        self._stream = pyte.Stream(self._screen)
        self._read_task: asyncio.Task | None = None

    @property
    def pty_process(self) -> PtyProcess:
        return self._pty

    @property
    def shell_name(self) -> str:
        return self._pty.shell_name

    def on_mount(self) -> None:
        """Start the PTY and begin the read loop."""
        self._pty.start()
        self._read_task = asyncio.create_task(self._read_loop())

    def on_unmount(self) -> None:
        """Clean up PTY and read task."""
        if self._read_task:
            self._read_task.cancel()
        self._pty.stop()

    def on_resize(self, event: events.Resize) -> None:
        """Forward resize events to PTY and pyte screen."""
        rows = event.size.height
        cols = event.size.width
        if rows > 0 and cols > 0:
            self._pty.resize(rows, cols)
            self._screen.resize(rows, cols)

    # Keys reserved for the app (must NOT be sent to PTY)
    _APP_KEYS: set[str] = {
        "ctrl+q",      # quit
        "ctrl+g",      # leader key
        "ctrl+1",      # focus shell
        "ctrl+2",      # focus advisory
        "f6",          # shrink divider
        "f7",          # grow divider
    }

    def on_key(self, event: events.Key) -> None:
        """Forward keyboard input to the PTY.

        Keys in _APP_KEYS are left alone so they bubble up to the App.
        """
        # Let app-level keys pass through (don't send to PTY, don't stop)
        if event.key in self._APP_KEYS:
            return

        # Key-to-bytes mapping for shell-native special keys
        key_map: dict[str, bytes] = {
            "enter": b"\r",
            "tab": b"\t",
            "backspace": b"\x7f",
            "delete": b"\x1b[3~",
            "escape": b"\x1b",
            "up": b"\x1b[A",
            "down": b"\x1b[B",
            "right": b"\x1b[C",
            "left": b"\x1b[D",
            "home": b"\x1b[H",
            "end": b"\x1b[F",
            "ctrl+c": b"\x03",
            "ctrl+d": b"\x04",
            "ctrl+z": b"\x1a",
            "ctrl+l": b"\x0c",
            "ctrl+r": b"\x12",
            "ctrl+a": b"\x01",
            "ctrl+e": b"\x05",
            "ctrl+u": b"\x15",
            "ctrl+w": b"\x17",
            "ctrl+s": b"\x13",
        }

        if event.key in key_map:
            self._pty.write(key_map[event.key])
            event.stop()
        elif event.character is not None:
            self._pty.write(event.character.encode("utf-8"))
            event.stop()

    def render_line(self, y: int) -> Strip:
        """Render a single line from the pyte screen as Segments."""
        width = self.size.width
        if y >= self._screen.lines:
            return Strip.blank(width)

        line = self._screen.buffer[y]
        segments: list[Segment] = []
        cols = min(self._screen.columns, width)

        # Batch consecutive characters with the same style
        current_text = ""
        current_style: Style | None = None

        for x in range(cols):
            char = line[x]
            style = _build_style(char)
            char_data = char.data if char.data else " "

            if style == current_style:
                current_text += char_data
            else:
                if current_text:
                    segments.append(Segment(current_text, current_style))
                current_text = char_data
                current_style = style

        # Flush remaining
        if current_text:
            segments.append(Segment(current_text, current_style))

        # Pad to width if needed
        cell_len = sum(len(s.text) for s in segments)
        if cell_len < width:
            segments.append(Segment(" " * (width - cell_len)))

        return Strip(segments, width)

    async def _read_loop(self) -> None:
        """Continuously read from PTY and update the pyte screen."""
        while self._pty.running:
            data = self._pty.read()
            if data:
                try:
                    self._stream.feed(data.decode("utf-8", errors="replace"))
                except Exception:
                    # pyte can occasionally choke on malformed sequences
                    pass
                self.refresh()
            else:
                # No data available, yield to event loop briefly
                await asyncio.sleep(0.02)

        # PTY died — notify app
        self.post_message(self.InputChanged(""))
