# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — History browser screen

"""Modal history browser for past AI reviews and deep-analysis results."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from rich.cells import cell_len
from rich.console import Console, ConsoleRenderable, Group
from rich.padding import Padding
from rich.segment import Segment
from rich.style import Style
from rich.syntax import Syntax
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Label, Static

from ridincligun.history import HistoryEntry, ReviewHistory, filter_entries
from ridincligun.i18n import t


class _FocusArea(Enum):
    SEARCH = "search"
    RISK = "risk"
    DATE = "date"
    LIST = "list"
    DETAIL = "detail"


_PANE_BG = "#0f1728"
_FRAME_BG = "#101829"

# ── Risk icon styles ─────────────────────────────────────────────
# Single-codepoint Unicode with unambiguous 1-cell width in every
# terminal.  Emoji (⛔ ⚠️ 💡 ✅) are NOT safe: terminals disagree
# on their cell width, causing row-by-row misalignment in the list.

_RISK_ICONS: dict[str, tuple[str, Style]] = {
    "danger":  ("✖", Style(color="#ff5555", bold=True)),
    "warning": ("▲", Style(color="#f1fa8c", bold=True)),
    "caution": ("◆", Style(color="#8be9fd")),
    "safe":    ("✓", Style(color="#50fa7b", bold=True)),
}
_DEFAULT_ICON: tuple[str, Style] = ("●", Style(color="#7f8da6"))


class _HistoryDivider(Widget):
    """Stable vertical divider between history panes."""

    DEFAULT_CSS = """
    _HistoryDivider {
        width: 3;
        height: 1fr;
        background: #101829;
    }
    """

    def render_line(self, y: int) -> Strip:
        if y >= self.size.height:
            return Strip.blank(self.size.width, Style())
        line = [
            Segment(" ", Style(bgcolor=_FRAME_BG)),
            Segment("│", Style(color="#42536f", bgcolor=_FRAME_BG)),
            Segment(" ", Style(bgcolor=_FRAME_BG)),
        ]
        return Strip(line, self.size.width)


class _HistoryListView(Widget):
    """Line-based history list rendering with stable full-width rows.

    Stores pre-built ``Strip`` objects (multi-segment) so that each
    icon can carry its own colour while every line has an exact,
    predictable cell width.  Content is always capped to the pane
    viewport — no horizontal overflow.
    """

    DEFAULT_CSS = """
    _HistoryListView {
        width: 1fr;
        height: auto;
        background: #0f1728;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._strips: list[Strip] = []
        self._background = Style(bgcolor=_PANE_BG)

    def set_strips(self, strips: list[Strip], *, min_width: int) -> None:
        self._strips = strips or [Strip.blank(min_width, self._background)]
        self.styles.width = max(24, min_width)
        self.styles.height = max(1, len(self._strips))
        self.refresh(layout=True)

    def render_line(self, y: int) -> Strip:
        width = max(1, self.size.width)
        if y >= len(self._strips):
            return Strip.blank(width, self._background)
        return self._strips[y].adjust_cell_length(width, self._background)


class _HistoryRenderableView(Widget):
    """Line-based renderable view to avoid row-dependent segment bleed."""

    DEFAULT_CSS = """
    _HistoryRenderableView {
        width: 1fr;
        height: auto;
        background: #0f1728;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._lines: list[Strip] = []
        self._background = Style(bgcolor=_PANE_BG)

    def set_renderable(self, renderable: ConsoleRenderable, *, width: int) -> None:
        self._lines = HistoryBrowserScreen._renderable_to_strips(
            renderable,
            width=width,
            background=_PANE_BG,
        )
        self.styles.width = width
        self.styles.height = max(1, len(self._lines))
        self.refresh(layout=True)

    def render_line(self, y: int) -> Strip:
        width = max(1, self.size.width)
        if y >= len(self._lines):
            return Strip.blank(width, self._background)
        return self._lines[y].adjust_cell_length(width, self._background)


def _truncate_to_width(text: str, width: int) -> str:
    """Truncate *text* so its cell width fits *width*, adding '…' suffix."""
    if width < 2:
        return text[:width]
    out: list[str] = []
    used = 0
    for ch in text:
        w = cell_len(ch)
        if used + w > width - 1:  # reserve 1 cell for '…'
            break
        out.append(ch)
        used += w
    return "".join(out) + "…"


class HistoryBrowserScreen(ModalScreen[None]):
    """Read-only modal browser for review history."""

    BINDINGS = [
        ("escape", "dismiss_browser", "Close history"),
    ]

    # ── CSS ──────────────────────────────────────────────────────────
    #
    # Layout is: Horizontal → [ScrollPane | Divider | ScrollPane]
    # No Container wrappers — fewer compositor boundaries = clean divider.
    # Both panes use overflow-x: hidden so content never bleeds sideways.

    CSS = """
    HistoryBrowserScreen {
        align: center middle;
    }

    #history-browser {
        width: 94%;
        height: 94%;
        background: #101829;
        border: tall #3d4b63;
        padding: 0 1;
    }

    .history-title {
        text-align: center;
        text-style: bold;
        color: #8be9fd;
        margin-bottom: 0;
    }

    .history-bar {
        height: auto;
        margin-bottom: 0;
    }

    #history-main {
        height: 1fr;
        margin-top: 1;
    }

    #history-divider {
        width: 3;
        height: 1fr;
        background: #101829;
    }

    .history-pane {
        height: 1fr;
        padding: 0 1;
        overflow-y: auto;
        overflow-x: hidden;
        background: #0f1728;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
        scrollbar-background: #0f1728;
        scrollbar-background-hover: #0f1728;
        scrollbar-background-active: #0f1728;
        scrollbar-color: #26354d;
        scrollbar-color-hover: #314765;
        scrollbar-color-active: #406088;
        scrollbar-corner-color: #0f1728;
    }

    .history-pane-focused {
        background: #16233b;
    }

    #history-list-pane {
        width: 3fr;
        min-width: 36;
    }

    #history-detail-pane {
        width: 2fr;
        min-width: 52;
    }

    #history-list-content, #history-detail-content {
        width: 1fr;
        height: auto;
        background: #0f1728;
    }

    #history-footer {
        margin-top: 0;
        color: #7f8da6;
    }
    """

    _RISK_OPTIONS = ("all", "danger", "warning", "caution", "safe")
    _DATE_OPTIONS = ("all", "today", "7d", "30d")

    def __init__(self, history: ReviewHistory) -> None:
        super().__init__()
        self._history = history
        self._all_entries: list[HistoryEntry] = history.read_all()
        self._filtered_entries: list[HistoryEntry] = []
        self._search = ""
        self._risk = "all"
        self._date = "all"
        self._focus_area = _FocusArea.LIST
        self._selected_index = 0

    # ── Compose: flat layout, no Container wrappers ──────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="history-browser"):
            yield Label(t("history.title"), classes="history-title")
            yield Static(id="history-search", classes="history-bar")
            yield Static(id="history-filters", classes="history-bar")
            with Horizontal(id="history-main"):
                with VerticalScroll(id="history-list-pane", classes="history-pane"):
                    yield _HistoryListView(id="history-list-content")
                yield _HistoryDivider(id="history-divider")
                with VerticalScroll(id="history-detail-pane", classes="history-pane"):
                    yield _HistoryRenderableView(id="history-detail-content")
            yield Static(id="history-footer")

    def on_mount(self) -> None:
        self._apply_filters()
        self._refresh()

    def on_resize(self, _event: events.Resize) -> None:
        self._refresh()

    # ── Key handling ─────────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        if event.key in ("tab", "shift+tab"):
            self._cycle_focus(reverse=event.key == "shift+tab")
            event.stop()
            return

        if event.key == "c" and self._focus_area != _FocusArea.SEARCH:
            self._copy_suggestion()
            event.stop()
            return

        if self._focus_area == _FocusArea.SEARCH and self._handle_search_key(event):
            event.stop()
            return

        if self._focus_area == _FocusArea.RISK and self._handle_filter_key(event, "risk"):
            event.stop()
            return

        if self._focus_area == _FocusArea.DATE and self._handle_filter_key(event, "date"):
            event.stop()
            return

        if self._focus_area == _FocusArea.LIST and self._handle_list_key(event):
            event.stop()
            return

        if self._focus_area == _FocusArea.DETAIL and self._handle_detail_key(event):
            event.stop()
            return

    def _handle_search_key(self, event: events.Key) -> bool:
        """Handle editing the pseudo search field."""
        if event.key == "backspace":
            self._search = self._search[:-1]
            self._apply_filters()
            self._refresh()
            return True
        if event.key == "space":
            self._search += " "
            self._apply_filters()
            self._refresh()
            return True

        character = event.character or ""
        if character and character.isprintable():
            self._search += character
            self._apply_filters()
            self._refresh()
            return True
        return False

    def _handle_filter_key(self, event: events.Key, which: str) -> bool:
        """Handle cycling a filter control."""
        if event.key in ("left", "h"):
            self._cycle_filter(which, reverse=True)
            return True
        if event.key in ("right", "l", "space", "enter"):
            self._cycle_filter(which, reverse=False)
            return True
        return False

    def _handle_list_key(self, event: events.Key) -> bool:
        if event.key in ("up", "k"):
            self._move_selection(-1)
            return True
        if event.key in ("down", "j"):
            self._move_selection(1)
            return True
        if event.key == "pageup":
            self._move_selection(-self._list_step())
            return True
        if event.key == "pagedown":
            self._move_selection(self._list_step())
            return True
        if event.key == "home":
            self._jump_to_selection(0)
            return True
        if event.key == "end":
            self._jump_to_selection(len(self._filtered_entries) - 1)
            return True
        return False

    def _handle_detail_key(self, event: events.Key) -> bool:
        detail_pane = self.query_one("#history-detail-pane", VerticalScroll)
        if event.key in ("up", "k"):
            detail_pane.scroll_up(animate=False)
            return True
        if event.key in ("down", "j"):
            detail_pane.scroll_down(animate=False)
            return True
        if event.key == "pageup":
            detail_pane.scroll_page_up(animate=False)
            return True
        if event.key == "pagedown":
            detail_pane.scroll_page_down(animate=False)
            return True
        if event.key == "home":
            detail_pane.scroll_home(animate=False)
            return True
        if event.key == "end":
            detail_pane.scroll_end(animate=False)
            return True
        return False

    # ── Focus / filter / selection ───────────────────────────────────

    def _cycle_focus(self, *, reverse: bool) -> None:
        areas = list(_FocusArea)
        current = areas.index(self._focus_area)
        delta = -1 if reverse else 1
        self._focus_area = areas[(current + delta) % len(areas)]
        self._refresh()

    def _cycle_filter(self, which: str, *, reverse: bool) -> None:
        options = self._RISK_OPTIONS if which == "risk" else self._DATE_OPTIONS
        current = self._risk if which == "risk" else self._date
        idx = options.index(current)
        delta = -1 if reverse else 1
        next_value = options[(idx + delta) % len(options)]
        if which == "risk":
            self._risk = next_value
        else:
            self._date = next_value
        self._apply_filters()
        self._refresh()

    def _move_selection(self, delta: int) -> None:
        if not self._filtered_entries:
            return
        self._selected_index = max(
            0,
            min(len(self._filtered_entries) - 1, self._selected_index + delta),
        )
        self._refresh_list()
        self._refresh_detail(reset_scroll=True)

    def _jump_to_selection(self, index: int) -> None:
        if not self._filtered_entries:
            return
        self._selected_index = max(0, min(len(self._filtered_entries) - 1, index))
        self._refresh_list()
        self._refresh_detail(reset_scroll=True)

    def _apply_filters(self) -> None:
        self._filtered_entries = filter_entries(
            self._all_entries,
            search=self._search,
            risk=self._risk,
            date_preset=self._date,
        )
        if not self._filtered_entries:
            self._selected_index = 0
            return
        self._selected_index = min(self._selected_index, len(self._filtered_entries) - 1)

    # ── Refresh helpers ──────────────────────────────────────────────

    def _refresh(self) -> None:
        self._refresh_search()
        self._refresh_filters()
        self._refresh_pane_focus()
        self._refresh_list()
        self._refresh_detail(reset_scroll=False)
        self._refresh_footer()

    def _refresh_search(self) -> None:
        search_widget = self.query_one("#history-search", Static)
        label = t("history.search_label")
        prefix = "▸" if self._focus_area == _FocusArea.SEARCH else " "
        value = self._search or t("history.search_placeholder")
        if not self._search:
            value = f"({value})"
        search_widget.update(f"{prefix} {label}: {value}")

    def _refresh_filters(self) -> None:
        filters_widget = self.query_one("#history-filters", Static)
        risk_prefix = "▸" if self._focus_area == _FocusArea.RISK else " "
        date_prefix = "▸" if self._focus_area == _FocusArea.DATE else " "
        risk_value = self._label_for_risk(self._risk)
        date_value = self._label_for_date(self._date)
        filters_widget.update(
            f"{risk_prefix} {t('history.risk_label')}: {risk_value}    "
            f"{date_prefix} {t('history.date_label')}: {date_value}"
        )

    def _refresh_pane_focus(self) -> None:
        list_pane = self.query_one("#history-list-pane", VerticalScroll)
        detail_pane = self.query_one("#history-detail-pane", VerticalScroll)
        list_pane.remove_class("history-pane-focused")
        detail_pane.remove_class("history-pane-focused")
        if self._focus_area == _FocusArea.LIST:
            list_pane.add_class("history-pane-focused")
        elif self._focus_area == _FocusArea.DETAIL:
            detail_pane.add_class("history-pane-focused")

    def _refresh_list(self) -> None:
        list_pane = self.query_one("#history-list-pane", VerticalScroll)
        list_widget = self.query_one("#history-list-content", _HistoryListView)
        pane_width = max(24, list_pane.size.width - 2)
        bg = Style(bgcolor=_PANE_BG)

        title_style = (
            Style.parse("bold #8be9fd") + bg
            if self._focus_area == _FocusArea.LIST
            else Style.parse("bold #7f8da6") + bg
        )
        text_style = Style(color="white") + bg

        focus_marker = "▸ " if self._focus_area == _FocusArea.LIST else "  "
        title_text = f"{focus_marker}{t('history.list_title')}"
        strips: list[Strip] = [
            Strip([Segment(title_text, title_style)], cell_len(title_text)),
            Strip([Segment("", text_style)], 0),
        ]

        if not self._filtered_entries:
            for text in (t("history.empty_title"), "", t("history.empty_hint")):
                strips.append(Strip([Segment(text, text_style)], cell_len(text)))
            list_widget.set_strips(strips, min_width=pane_width)
            return

        for idx, entry in enumerate(self._filtered_entries):
            selected = idx == self._selected_index
            line_style = (Style.parse("bold #8be9fd") + bg) if selected else text_style
            prefix = "▸" if selected else " "
            icon_char, icon_style = _RISK_ICONS.get(entry.risk, _DEFAULT_ICON)
            timestamp = self._format_timestamp(entry.timestamp)
            source = self._source_badge(entry.source)
            tail = f" [{source} {timestamp}] {entry.command}"

            # Multi-segment strip: prefix | icon (own colour) | rest
            segments = [
                Segment(f"{prefix} ", line_style),
                Segment(icon_char, icon_style + bg),
                Segment(tail, line_style),
            ]
            strip_len = cell_len(f"{prefix} ") + cell_len(icon_char) + cell_len(tail)
            strips.append(Strip(segments, strip_len))

        list_widget.set_strips(strips, min_width=pane_width)
        list_pane.scroll_to(y=max(0, self._selected_index + 2), animate=False)

    def _refresh_detail(self, *, reset_scroll: bool) -> None:
        detail_pane = self.query_one("#history-detail-pane", VerticalScroll)
        detail_widget = self.query_one("#history-detail-content", _HistoryRenderableView)
        detail_widget.set_renderable(
            self._build_detail_renderable(),
            width=max(24, detail_pane.size.width - 2),
        )
        if reset_scroll:
            detail_pane.scroll_home(animate=False)

    def _build_detail_renderable(self) -> Group:
        entry = self._selected_entry()
        if entry is None:
            return Group(
                self._pane_title_text(
                    t("history.detail_title"),
                    focused=self._focus_area == _FocusArea.DETAIL,
                ),
                Text(""),
                Text(t("history.empty_title")),
                Text(""),
                Text(t("history.empty_hint")),
            )

        renderables = [
            self._pane_title_text(
                t("history.detail_title"),
                focused=self._focus_area == _FocusArea.DETAIL,
            ),
            Text(""),
            Text(t("history.detail_command"), style="bold"),
            self._code_panel(entry.command),
            Text(""),
            Text(t("history.detail_summary"), style="bold"),
            Text(entry.summary or "—"),
            Text(""),
        ]

        if entry.explanation:
            renderables.extend(
                [
                    Text(t("history.detail_explanation"), style="bold"),
                    Text(entry.explanation),
                    Text(""),
                ]
            )
        elif not entry.has_full_detail:
            renderables.extend(
                [
                    Text(t("history.detail_explanation"), style="bold"),
                    Text(t("history.legacy_note"), style="italic #7f8da6"),
                    Text(""),
                ]
            )

        if entry.suggestion:
            renderables.extend(
                [
                    Text(t("history.detail_suggestion"), style="bold"),
                    self._code_panel(entry.suggestion),
                    Text(""),
                ]
            )

        meta = Text()
        meta.append(f"{t('history.detail_risk')}: {self._label_for_risk(entry.risk)}\n")
        meta.append(f"{t('history.detail_source')}: {self._source_label(entry.source)}\n")
        meta.append(
            f"{t('history.detail_timestamp')}: "
            f"{self._format_timestamp(entry.timestamp, full=True)}\n"
        )
        if entry.provider:
            meta.append(f"{t('history.detail_provider')}: {entry.provider}\n")
        if entry.tokens:
            meta.append(f"{t('history.detail_tokens')}: {entry.tokens}")

        renderables.extend(
            [
                Text(t("history.detail_meta"), style="bold"),
                meta,
            ]
        )
        return Group(*renderables)

    # ── Plaintext accessors (used by tests + copy) ───────────────────

    def _detail_plaintext(self) -> str:
        entry = self._selected_entry()
        if entry is None:
            return f"{t('history.empty_title')}\n{t('history.empty_hint')}"

        parts = [
            t("history.detail_title"),
            t("history.detail_command"),
            entry.command,
            t("history.detail_summary"),
            entry.summary or "—",
        ]
        if entry.explanation:
            parts.extend([t("history.detail_explanation"), entry.explanation])
        elif not entry.has_full_detail:
            parts.extend([t("history.detail_explanation"), t("history.legacy_note")])
        if entry.suggestion:
            parts.extend([t("history.detail_suggestion"), entry.suggestion])
        return "\n".join(parts)

    def _list_plaintext(self) -> str:
        lines = [t("history.list_title")]
        if not self._filtered_entries:
            lines.extend(["", t("history.empty_title"), "", t("history.empty_hint")])
            return "\n".join(lines)

        for idx, entry in enumerate(self._filtered_entries):
            prefix = "▸" if idx == self._selected_index else " "
            icon = self._icon_for_risk(entry.risk)
            timestamp = self._format_timestamp(entry.timestamp)
            source = self._source_badge(entry.source)
            lines.append(f"{prefix} {icon} [{source} {timestamp}] {entry.command}")
        return "\n".join(lines)

    # ── Static helpers ───────────────────────────────────────────────

    @staticmethod
    def _pane_title_text(title: str, *, focused: bool) -> Text:
        marker = "▸ " if focused else "  "
        style = "bold #8be9fd" if focused else "bold #7f8da6"
        return Text(f"{marker}{title}", style=style)

    @staticmethod
    def _renderable_to_strips(
        renderable: ConsoleRenderable,
        *,
        width: int,
        background: str,
    ) -> list[Strip]:
        console = Console(width=width, force_terminal=True, color_system="truecolor")
        options = console.options.update(width=width, height=None)
        lines = console.render_lines(renderable, options=options, pad=True)
        background_style = Style(bgcolor=background)
        strips: list[Strip] = []
        for line in lines:
            segments = [
                Segment(
                    segment.text,
                    ((segment.style or Style()) + background_style),
                    segment.control,
                )
                for segment in line
            ]
            strips.append(Strip(segments, width).adjust_cell_length(width, background_style))
        return strips or [Strip.blank(width, background_style)]

    @staticmethod
    def _code_panel(code: str) -> Padding:
        syntax = Syntax(
            code or "",
            "bash",
            line_numbers=False,
            word_wrap=True,
            background_color="#0b1220",
        )
        return Padding(syntax, (0, 1), style="on #0b1220")

    def _refresh_footer(self) -> None:
        footer_widget = self.query_one("#history-footer", Static)
        shown = len(self._filtered_entries)
        total = len(self._all_entries)
        footer_widget.update(
            f"{t('history.result_count', shown=shown, total=total)}\n"
            f"{t('history.hint')}"
        )

    def _selected_entry(self) -> HistoryEntry | None:
        if not self._filtered_entries:
            return None
        return self._filtered_entries[self._selected_index]

    def _list_step(self) -> int:
        list_pane = self.query_one("#history-list-pane", VerticalScroll)
        return max(5, list_pane.size.height - 4)

    def _copy_suggestion(self) -> None:
        entry = self._selected_entry()
        suggestion = (entry.suggestion if entry else "").strip()
        if not suggestion:
            self._toast(t("history.copy_missing"))
            return
        try:
            import pyperclip

            pyperclip.copy(suggestion)
            self._toast(t("toast.copied", source=t("history.copy_source")))
        except Exception as exc:
            self._toast(t("toast.copy_failed", error=exc), severity="error")

    def _toast(self, message: str, *, severity: str = "info") -> None:
        toast = getattr(self.app, "_toast", None)
        if callable(toast):
            toast(message, severity=severity)

    @staticmethod
    def _icon_for_risk(risk: str) -> str:
        """Plain-text icon for plaintext export / tests.

        The live UI uses the coloured ``_RISK_ICONS`` dict instead.
        """
        return _RISK_ICONS.get(risk, _DEFAULT_ICON)[0]

    @staticmethod
    def _format_timestamp(timestamp: str, *, full: bool = False) -> str:
        if not timestamp:
            return "—"
        try:
            parsed = datetime.fromisoformat(timestamp)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone()
            return parsed.strftime("%Y-%m-%d %H:%M:%S" if full else "%Y-%m-%d")
        except ValueError:
            return timestamp

    @staticmethod
    def _source_badge(source: str) -> str:
        return {
            "ai": "AI",
            "deep_analysis": "DEEP",
        }.get(source, source.upper() if source else "—")

    @staticmethod
    def _source_label(source: str) -> str:
        return {
            "ai": t("history.source_ai"),
            "deep_analysis": t("history.source_deep_analysis"),
        }.get(source, t("history.source_unknown"))

    @staticmethod
    def _label_for_risk(risk: str) -> str:
        key = {
            "all": "history.risk_all",
            "safe": "history.risk_safe",
            "caution": "history.risk_caution",
            "warning": "history.risk_warning",
            "danger": "history.risk_danger",
        }.get(risk, "history.risk_all")
        return t(key)

    @staticmethod
    def _label_for_date(date_value: str) -> str:
        key = {
            "all": "history.date_all",
            "today": "history.date_today",
            "7d": "history.date_7d",
            "30d": "history.date_30d",
        }.get(date_value, "history.date_all")
        return t(key)

    def action_dismiss_browser(self) -> None:
        """Close the history browser."""
        self.dismiss(None)
