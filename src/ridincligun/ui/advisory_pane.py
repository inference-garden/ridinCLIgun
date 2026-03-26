"""Advisory pane widget for ridinCLIgun.

Displays warnings, AI reviews, and status information in the right pane.
Reads state only — never mutates it.
Text reflows automatically when the pane is resized.
Supports mouse text selection + copy.
"""

from __future__ import annotations

import textwrap

from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.strip import Strip
from textual.widget import Widget

# Selection highlight style (same as shell pane for consistency)
_SEL_STYLE = Style(color="white", bgcolor="#44475a")


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
        self._raw_lines: list[tuple[str, str]] = []  # (text, style_str) — source of truth
        self._wrapped_lines: list[tuple[str, str]] = []  # recomputed on resize
        self._scroll_offset: int = 0  # lines scrolled from top
        # Text selection state
        self._sel_start: tuple[int, int] | None = None
        self._sel_end: tuple[int, int] | None = None
        self._selecting: bool = False
        self._set_welcome()

    def _set_welcome(self) -> None:
        """Show the initial welcome message."""
        self._raw_lines = [
            ("", ""),
            ("  ridinCLIgun", "bold cyan"),
            ("", ""),
            ("  Your shell companion.", "dim"),
            ("  Advises, never acts.", "dim"),
            ("", ""),
            ("  Ctrl+G → H  show help", "dim green"),
        ]
        self._rewrap()

    def set_content(self, lines: list[tuple[str, str]]) -> None:
        """Replace the advisory content. Each item is (text, style_string)."""
        self._raw_lines = lines
        self._rewrap()
        self._scroll_offset = 0
        self.clear_selection()
        self.refresh()

    def append_content(self, lines: list[tuple[str, str]]) -> None:
        """Append lines to the existing advisory content."""
        self._raw_lines.extend(lines)
        self._rewrap()
        self.refresh()

    def remove_lines_containing(self, marker: str) -> None:
        """Remove all raw lines whose text contains the given marker."""
        self._raw_lines = [(t, s) for t, s in self._raw_lines if marker not in t]
        self._rewrap()
        self.refresh()

    def clear(self) -> None:
        """Reset to welcome message."""
        self._set_welcome()
        self.clear_selection()
        self.refresh()

    def on_resize(self, _event) -> None:
        """Reflow text when the pane is resized."""
        self._rewrap()

    def _rewrap(self) -> None:
        """Recompute wrapped lines from raw lines for current width."""
        width = self.size.width if self.size.width > 0 else 40
        self._wrapped_lines = []
        for text, style_str in self._raw_lines:
            if not text or text.isspace():
                self._wrapped_lines.append(("", style_str))
            else:
                # Preserve leading indent
                stripped = text.lstrip()
                indent = text[: len(text) - len(stripped)]
                wrap_width = max(10, width - len(indent))
                wrapped = textwrap.wrap(stripped, width=wrap_width) or [""]
                for wline in wrapped:
                    self._wrapped_lines.append((indent + wline, style_str))

    # ── Mouse selection ───────────────────────────────────────────

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Start text selection on mouse down."""
        if event.button == 1:
            content_y = event.y + self._scroll_offset
            self._sel_start = (content_y, event.x)
            self._sel_end = (content_y, event.x)
            self._selecting = True
            self.capture_mouse()
            self.refresh()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Extend selection while dragging."""
        if self._selecting:
            content_y = event.y + self._scroll_offset
            self._sel_end = (content_y, event.x)
            self.refresh()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        """End selection on mouse release."""
        if self._selecting and event.button == 1:
            content_y = event.y + self._scroll_offset
            self._sel_end = (content_y, event.x)
            self._selecting = False
            self.release_mouse()
            if self._sel_start == self._sel_end:
                self.clear_selection()
            self.refresh()

    def on_mouse_scroll_up(self, _event: events.MouseScrollUp) -> None:
        """Scroll advisory content up (show earlier lines)."""
        if self._scroll_offset > 0:
            self._scroll_offset = max(0, self._scroll_offset - 3)
            self.refresh()

    def on_mouse_scroll_down(self, _event: events.MouseScrollDown) -> None:
        """Scroll advisory content down (show later lines)."""
        max_offset = max(0, len(self._wrapped_lines) - self.size.height)
        if self._scroll_offset < max_offset:
            self._scroll_offset = min(max_offset, self._scroll_offset + 3)
            self.refresh()

    def clear_selection(self) -> None:
        """Clear any active text selection."""
        self._sel_start = None
        self._sel_end = None
        self._selecting = False

    def has_selection(self) -> bool:
        """Whether there is an active text selection."""
        return (
            self._sel_start is not None
            and self._sel_end is not None
            and self._sel_start != self._sel_end
        )

    def get_selected_text(self) -> str:
        """Return the selected text from the wrapped lines."""
        if not self.has_selection():
            return ""

        start, end = self._selection_bounds()
        lines = []

        for y in range(start[0], end[0] + 1):
            if y >= len(self._wrapped_lines):
                break
            text, _style = self._wrapped_lines[y]
            # Pad to width for column-accurate selection
            padded = text.ljust(self.size.width)

            col_start = start[1] if y == start[0] else 0
            col_end = end[1] if y == end[0] else len(padded) - 1
            col_end = min(col_end, len(padded) - 1)

            line = padded[col_start : col_end + 1].rstrip()
            lines.append(line)

        while lines and not lines[-1]:
            lines.pop()

        return "\n".join(lines)

    def _selection_bounds(self) -> tuple[tuple[int, int], tuple[int, int]]:
        """Return (start, end) in normalized order."""
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
        return start <= (y, x) <= end

    # ── Rendering ─────────────────────────────────────────────────

    def render_line(self, y: int) -> Strip:
        """Render a single line of advisory content with scroll offset."""
        width = self.size.width
        has_sel = self.has_selection()
        line_idx = y + self._scroll_offset

        if line_idx < len(self._wrapped_lines):
            text, style_str = self._wrapped_lines[line_idx]
            base_style = Style.parse(style_str) if style_str else Style()
            padded = text.ljust(width)[:width]

            if has_sel:
                # Render character by character for selection highlight
                segments: list[Segment] = []
                current_text = ""
                current_style: Style | None = None

                for x, ch in enumerate(padded):
                    style = _SEL_STYLE if self._is_selected(line_idx, x) else base_style
                    if style == current_style:
                        current_text += ch
                    else:
                        if current_text:
                            segments.append(Segment(current_text, current_style))
                        current_text = ch
                        current_style = style
                if current_text:
                    segments.append(Segment(current_text, current_style))
                return Strip(segments, width)
            else:
                return Strip([Segment(padded, base_style)], width)

        return Strip.blank(width)
