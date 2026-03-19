"""Shell pane widget for ridinCLIgun.

Wraps a PTY process with pyte terminal emulation and renders into a Textual widget.
All keyboard input when focused goes to the PTY. The shell is real.
Supports mouse-wheel scrollback through pyte HistoryScreen.
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

from ridincligun.shell.input_parser import extract_current_command
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

    class AnyKeyPressed(Message):
        """Posted on every key press that the shell handles. Used for help dismissal."""
        pass

    _HISTORY_SIZE = 1000  # max scrollback lines

    def __init__(self, shell: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pty = PtyProcess(shell=shell or None)
        self._screen = pyte.HistoryScreen(80, 24, history=self._HISTORY_SIZE)
        self._stream = pyte.Stream(self._screen)
        self._read_task: asyncio.Task | None = None
        self._last_command: str = ""
        self._scroll_offset: int = 0  # 0 = live view, >0 = scrolled into history
        self._debounce_task: asyncio.Task | None = None  # debounced command check
        self._cursor_visible: bool = True  # toggled for blink effect
        self._blink_task: asyncio.Task | None = None
        # Text selection state (row, col) — None when no selection
        self._sel_start: tuple[int, int] | None = None
        self._sel_end: tuple[int, int] | None = None
        self._selecting: bool = False  # True during mouse drag

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
        self._blink_task = asyncio.create_task(self._cursor_blink_loop())

    def on_unmount(self) -> None:
        """Clean up PTY and read task."""
        if self._read_task:
            self._read_task.cancel()
        if self._blink_task:
            self._blink_task.cancel()
        self._pty.stop()

    async def _cursor_blink_loop(self) -> None:
        """Toggle cursor visibility every 530ms for a blink effect."""
        while True:
            await asyncio.sleep(0.53)
            self._cursor_visible = not self._cursor_visible
            self.refresh()

    def restart_shell(self) -> None:
        """Stop the current shell and start a fresh one."""
        # Stop existing
        if self._read_task:
            self._read_task.cancel()
        self._pty.stop()

        # Fresh pyte screen
        rows = self.size.height or 24
        cols = self.size.width or 80
        self._screen = pyte.HistoryScreen(cols, rows, history=self._HISTORY_SIZE)
        self._stream = pyte.Stream(self._screen)
        self._last_command = ""
        self._scroll_offset = 0

        # Start new PTY
        self._pty = PtyProcess()
        self._pty.start()
        self._pty.resize(rows, cols)
        self._read_task = asyncio.create_task(self._read_loop())
        self.refresh()

    def on_resize(self, event: events.Resize) -> None:
        """Forward resize events to PTY and pyte screen.

        Strategy (option 5 — "snapshot + Ctrl+L"):
        1. Create a fresh pyte screen at the new dimensions.
        2. Tell the PTY the new size (triggers SIGWINCH).
        3. Send Ctrl+L to the shell so it repaints the current prompt.

        This means: scrollback above the viewport is lost on resize, but the
        current screen is correct. A real fix requires a reflow-capable
        terminal emulator (planned for v0.3).
        """
        rows = event.size.height
        cols = event.size.width
        if rows > 0 and cols > 0:
            # Fresh screen at new dimensions — clean slate
            self._screen = pyte.HistoryScreen(cols, rows, history=self._HISTORY_SIZE)
            self._stream = pyte.Stream(self._screen)
            self._scroll_offset = 0
            # Tell the PTY the new size — shell receives SIGWINCH
            self._pty.resize(rows, cols)
            # Ask the shell to redraw the current prompt
            self._pty.write(b"\x0c")  # Ctrl+L
            self.refresh()

    # ── Mouse selection ───────────────────────────────────────────

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Start text selection on mouse down."""
        if event.button == 1:  # Left click
            self._sel_start = (event.y, event.x)
            self._sel_end = (event.y, event.x)
            self._selecting = True
            self.capture_mouse()
            self.refresh()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Extend selection while dragging."""
        if self._selecting:
            self._sel_end = (event.y, event.x)
            self.refresh()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        """End selection on mouse release."""
        if self._selecting and event.button == 1:
            self._sel_end = (event.y, event.x)
            self._selecting = False
            self.release_mouse()
            # If start == end, it was just a click — clear selection
            if self._sel_start == self._sel_end:
                self.clear_selection()
            self.refresh()

    def clear_selection(self) -> None:
        """Clear any active text selection."""
        self._sel_start = None
        self._sel_end = None
        self._selecting = False
        self.refresh()

    def has_selection(self) -> bool:
        """Whether there is an active text selection."""
        return (
            self._sel_start is not None
            and self._sel_end is not None
            and self._sel_start != self._sel_end
        )

    def get_selected_text(self) -> str:
        """Return the selected text from the pyte screen buffer."""
        if not self.has_selection():
            return ""

        start, end = self._selection_bounds()
        lines = []

        for y in range(start[0], end[0] + 1):
            if y >= self._screen.lines:
                break
            row = self._screen.buffer[y]

            # Determine column range for this row
            col_start = start[1] if y == start[0] else 0
            col_end = end[1] if y == end[0] else self._screen.columns - 1
            col_end = min(col_end, self._screen.columns - 1)

            line = "".join(
                row[x].data if row[x].data else " "
                for x in range(col_start, col_end + 1)
            ).rstrip()
            lines.append(line)

        # Strip trailing empty lines
        while lines and not lines[-1]:
            lines.pop()

        return "\n".join(lines)

    def _selection_bounds(self) -> tuple[tuple[int, int], tuple[int, int]]:
        """Return (start, end) in normalized order (top-left to bottom-right)."""
        s = self._sel_start or (0, 0)
        e = self._sel_end or (0, 0)
        if s > e:
            s, e = e, s
        return s, e

    def _is_selected(self, y: int, x: int) -> bool:
        """Check if a cell is within the current selection."""
        if not self.has_selection():
            return False
        start, end = self._selection_bounds()
        # Linear position comparison for multi-line selection
        pos = (y, x)
        return start <= pos <= end

    # ── Mouse scrollback ─────────────────────────────────────────

    def on_mouse_scroll_up(self, _event: events.MouseScrollUp) -> None:
        """Scroll up into history (show earlier output)."""
        max_offset = len(self._screen.history.top)
        if self._scroll_offset < max_offset:
            self._scroll_offset = min(max_offset, self._scroll_offset + 3)
            self.refresh()

    def on_mouse_scroll_down(self, _event: events.MouseScrollDown) -> None:
        """Scroll down towards live view."""
        if self._scroll_offset > 0:
            self._scroll_offset = max(0, self._scroll_offset - 3)
            self.refresh()

    # Keys reserved for the app (must NOT be sent to PTY)
    _APP_KEYS: set[str] = {
        "ctrl+q",      # quit
        "ctrl+g",      # leader key
        "f6",          # divider left
        "f7",          # divider right
    }

    def on_key(self, event: events.Key) -> None:
        """Forward keyboard input to the PTY.

        Keys in _APP_KEYS are left alone so they bubble up to the App.
        When the app's leader key is active, ALL keys pass through.
        Any keypress snaps back to live view if scrolled.
        """
        # Let app-level keys pass through (don't send to PTY, don't stop)
        if event.key in self._APP_KEYS:
            return

        # Snap to live view on any keypress, reset cursor blink
        if self._scroll_offset > 0:
            self._scroll_offset = 0
        self._cursor_visible = True

        # When leader mode or model selector is active, let keys bubble to App
        from ridincligun.app import RidinCLIgunApp  # noqa: E402

        if isinstance(self.app, RidinCLIgunApp) and (
            self.app._leader.active or self.app._model_select_showing
        ):
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
            self.clear_selection()
            self.post_message(self.AnyKeyPressed())
            self._check_command_changed()
            event.stop()
        elif event.character is not None:
            self._pty.write(event.character.encode("utf-8"))
            self.clear_selection()
            self.post_message(self.AnyKeyPressed())
            self._check_command_changed()
            event.stop()

    # Selection highlight style
    _SEL_STYLE = Style(color="white", bgcolor="#44475a")
    # Cursor style (block cursor via reverse video)
    _CURSOR_STYLE = Style(color="black", bgcolor="#e0e0e0")

    def _get_line_buffer(self, y: int) -> dict | None:
        """Get the character buffer for a display line, accounting for scroll offset.

        When scroll_offset > 0, we index into the combined history + screen buffer.
        Returns None if the line is out of range.
        """
        if self._scroll_offset == 0:
            # Live view — render directly from the screen
            if y >= self._screen.lines:
                return None
            return self._screen.buffer[y]

        # Scrolled view: combine history.top + screen.buffer
        history = self._screen.history.top
        hist_len = len(history)
        screen_lines = self._screen.lines
        total_lines = hist_len + screen_lines

        # Display line index in the combined buffer
        # The viewport shows lines from (total - screen_lines - scroll_offset)
        abs_idx = total_lines - screen_lines - self._scroll_offset + y

        if abs_idx < 0 or abs_idx >= total_lines:
            return None
        if abs_idx < hist_len:
            return history[abs_idx]
        return self._screen.buffer[abs_idx - hist_len]

    def render_line(self, y: int) -> Strip:
        """Render a single line from the pyte screen as Segments."""
        width = self.size.width
        line = self._get_line_buffer(y)
        if line is None:
            return Strip.blank(width)

        segments: list[Segment] = []
        cols = min(self._screen.columns, width)
        has_sel = self.has_selection() and self._scroll_offset == 0
        # Show cursor only in live view, on the cursor line
        show_cursor = (
            self._scroll_offset == 0
            and y == self._screen.cursor.y
            and self.has_focus
        )

        # Batch consecutive characters with the same style + selection state
        current_text = ""
        current_style: Style | None = None

        for x in range(cols):
            char = line[x]
            style = _build_style(char)
            char_data = char.data if char.data else " "

            # Apply cursor highlight (blinks)
            if show_cursor and x == self._screen.cursor.x and self._cursor_visible:
                style = self._CURSOR_STYLE
            # Apply selection highlight (only in live view)
            elif has_sel and self._is_selected(y, x):
                style = self._SEL_STYLE

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

        # Scrollback indicator on first line
        if y == 0 and self._scroll_offset > 0:
            indicator = f" ↑ {self._scroll_offset} lines ↑ "
            ind_style = Style(color="black", bgcolor="#d9a644", bold=True)
            return Strip(
                [Segment(indicator, ind_style), Segment(" " * max(0, width - len(indicator)))],
                width,
            )

        return Strip(segments, width)

    def _check_command_changed(self) -> None:
        """Check if the current command input changed and notify the app."""
        command = extract_current_command(self._screen)
        if command != self._last_command:
            self._last_command = command
            self.post_message(self.InputChanged(command))

    def _schedule_debounced_check(self) -> None:
        """Schedule a debounced command check.

        Paste operations send data in chunks — the PTY echo arrives over
        multiple read cycles. This waits for the stream to settle before
        extracting the command, so the advisory pane sees the full input.
        """
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = asyncio.create_task(self._debounced_check())

    async def _debounced_check(self) -> None:
        """Wait briefly for paste data to settle, then check the command."""
        await asyncio.sleep(0.08)  # 80ms — fast enough to feel instant
        self._check_command_changed()

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
                # Snap to live view when new output arrives
                self._scroll_offset = 0
                self._schedule_debounced_check()
                self.refresh()
            else:
                # No data available, yield to event loop briefly
                await asyncio.sleep(0.02)

        # PTY died — notify app
        self.post_message(self.InputChanged(""))
