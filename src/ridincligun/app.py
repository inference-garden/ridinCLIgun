"""Main Textual application for ridinCLIgun.

Composes the two-pane layout, owns AppState, and coordinates messages.
Handles the Ctrl+G leader key, divider resize, config, and AI review.
"""

from __future__ import annotations

import asyncio

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches

from ridincligun.advisory.engine import AdvisoryEngine
from ridincligun.advisory.models import RiskLevel
from ridincligun.config import Config, load_config, save_split_ratio
from ridincligun.provider.anthropic import AnthropicAdapter
from ridincligun.provider.base import AIReviewResponse
from ridincligun.provider.manager import ProviderManager
from ridincligun.shell.input_parser import extract_current_command
from ridincligun.shortcuts.bindings import LeaderAction, LeaderState
from ridincligun.state import AppState, Phase
from ridincligun.ui.advisory_pane import AdvisoryPane
from ridincligun.ui.divider import PaneDivider
from ridincligun.ui.shell_pane import ShellPane
from ridincligun.ui.status_bar import StatusBar

# Min/max split ratio bounds (shell fr : advisory fr)
_MIN_SHELL_FR = 1
_MAX_SHELL_FR = 7
_MIN_ADVISORY_FR = 1
_MAX_ADVISORY_FR = 5


class RidinCLIgunApp(App):
    """The ridinCLIgun terminal companion application."""

    TITLE = "ridinCLIgun"

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-container {
        layout: horizontal;
        height: 1fr;
    }

    #shell-pane {
        width: 3fr;
        min-width: 20;
    }

    #advisory-pane {
        width: 2fr;
        min-width: 15;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+g", "leader", "Leader key"),
        ("f6", "grow_divider", "Divider left (more advisory)"),
        ("f7", "shrink_divider", "Divider right (more shell)"),
    ]

    def __init__(self, config: Config | None = None) -> None:
        super().__init__()
        self.config = config or load_config()
        self.state = AppState(
            ai_enabled=self.config.ai_enabled_default,
            split_ratio=self.config.split_ratio,
        )
        self._leader = LeaderState()
        self._help_showing = False
        self._engine = AdvisoryEngine()
        # AI provider — key passed explicitly from config, not from os.environ (FINDING-02)
        adapter = AnthropicAdapter(
            api_key=self.config.api_key,
            model=self.config.provider.model,
        )
        self._provider = ProviderManager(
            adapter, timeout=self.config.provider.timeout_seconds
        )
        self._review_task: asyncio.Task | None = None
        self._ai_review_showing = False  # True while an AI review is displayed

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-container"):
            yield ShellPane(shell=self.config.shell or None, id="shell-pane")
            yield PaneDivider(id="pane-divider")
            yield AdvisoryPane(id="advisory-pane")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        """Initialize the app after mounting."""
        try:
            shell = self.query_one("#shell-pane", ShellPane)
            shell.focus()
            self._apply_split_ratio()
            self._sync_status_bar()
        except NoMatches:
            pass

    # ── Key handling ──────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        """Handle leader key follow-up."""
        if not self._leader.active:
            return

        # We're in leader mode — resolve the follow-up key
        action = self._leader.resolve(event.key)
        self._sync_leader_indicator(active=False)

        if action is not None:
            event.stop()
            self._dispatch_leader_action(action)
        else:
            # Invalid follow-up or Escape — return to normal silently
            pass

    # ── Shell event handlers ────────────────────────────────────

    def on_shell_pane_any_key_pressed(self, _message: ShellPane.AnyKeyPressed) -> None:
        """Dismiss help when the user types anything in the shell."""
        if self._help_showing:
            self._help_showing = False
            self._show_advisory_welcome()

    def on_shell_pane_input_changed(self, message: ShellPane.InputChanged) -> None:
        """Analyze the current command and show/clear warnings accordingly.

        AI review persists while the user edits the command, but clears when:
        - Command becomes empty (executed via Enter, or cleared via Ctrl+C/U)
        - A new review is requested (Ctrl+G, R)
        """
        command = message.command

        if not command:
            # Command empty → clear everything (including AI review)
            self._ai_review_showing = False
            self._show_advisory_welcome()
            return

        # AI review showing + command still has content → keep review visible
        if self._ai_review_showing:
            return

        result = self._engine.analyze(command)
        if result.is_safe:
            self._show_advisory_welcome()
            return

        self._show_warnings(result)

    # ── Leader key ────────────────────────────────────────────────

    def action_leader(self) -> None:
        """Activate Ctrl+G leader mode. No timeout — exits on next key."""
        self._leader.activate()
        self._sync_leader_indicator(active=True)

    def _sync_leader_indicator(self, *, active: bool) -> None:
        """Show/hide the leader key waiting indicator in the status bar."""
        try:
            status = self.query_one("#status-bar", StatusBar)
            status.update_state(leader_active=active)
        except NoMatches:
            pass

    def _dispatch_leader_action(self, action: LeaderAction) -> None:
        """Execute a leader key action."""
        match action:
            case LeaderAction.TOGGLE_AI:
                self.state.ai_enabled = not self.state.ai_enabled
                label = "on" if self.state.ai_enabled else "off"
                self._show_advisory_notice(f"AI review: {label}")
                self._sync_status_bar()

            case LeaderAction.TOGGLE_SECRET:
                self.state.secret_mode = not self.state.secret_mode
                label = "on" if self.state.secret_mode else "off"
                # Cancel any in-flight AI review when entering secret mode
                if self.state.secret_mode and self._review_task and not self._review_task.done():
                    self._review_task.cancel()
                    self._review_task = None
                self._show_advisory_notice(f"Secret mode: {label}")
                self._sync_status_bar()

            case LeaderAction.HELP:
                self._show_help()

            case LeaderAction.QUIT:
                self.action_quit()

            case LeaderAction.REVIEW:
                self._trigger_ai_review()

            case LeaderAction.RESTART_SHELL:
                self._restart_shell()

            case LeaderAction.DEBUG:
                self._show_debug()

            case LeaderAction.COPY:
                self._do_copy()

            case LeaderAction.PASTE:
                self._do_paste()

    # ── AI Review ────────────────────────────────────────────────

    def _trigger_ai_review(self) -> None:
        """Trigger an AI review of the current command."""
        # Starting a new review clears any previous review lock
        self._ai_review_showing = False

        if not self.state.ai_enabled:
            self._show_advisory_notice("AI is off. Toggle with Ctrl+G, A.")
            return

        if self.state.secret_mode:
            self._show_advisory_notice(
                "Secret mode is on — command not sent.\n"
                "Toggle with Ctrl+G, S."
            )
            return

        if not self._provider.is_configured:
            self._show_advisory_notice(
                "No API key configured.\n"
                "Add ANTHROPIC_API_KEY to:\n"
                "~/.config/ridincligun/.env"
            )
            return

        # Get current command from shell
        try:
            shell = self.query_one("#shell-pane", ShellPane)
            command = extract_current_command(shell._screen)
        except NoMatches:
            return

        if not command.strip():
            self._show_advisory_notice("No command to review.")
            return

        # Cancel any in-flight review
        if self._review_task and not self._review_task.done():
            self._review_task.cancel()

        # Show loading state
        self.state.phase = Phase.REVIEW_LOADING
        self._show_advisory_notice(
            f"🔍 Reviewing: {command}\n\n"
            f"Asking {self._provider.provider_name}..."
        )

        # Launch async review
        self._review_task = asyncio.create_task(self._do_ai_review(command))

    async def _do_ai_review(self, command: str) -> None:
        """Perform the AI review asynchronously."""
        result = await self._provider.review(command)

        # Defense in depth: suppress result if secret mode was enabled
        # after the request was sent (race condition guard)
        if self.state.secret_mode:
            self.state.phase = Phase.TYPING
            return

        self.state.phase = Phase.REVIEW_READY

        if result.success and result.response:
            self._show_ai_review(command, result.response)
        else:
            self._show_advisory_notice(f"⚠️ Review failed\n\n{result.error_message}")

    def _show_ai_review(self, command: str, response: AIReviewResponse) -> None:
        """Display an AI review result in the advisory pane. Persists until next review."""
        self._ai_review_showing = True
        risk_styles = {
            "danger": ("bold red", "red", "⛔"),
            "warning": ("bold yellow", "yellow", "⚠️"),
            "caution": ("bold cyan", "dim cyan", "💡"),
            "safe": ("bold green", "green", "✅"),
        }
        title_style, body_style, icon = risk_styles.get(
            response.risk_assessment, ("bold", "dim", "ℹ️")
        )

        lines: list[tuple[str, str]] = [
            ("", ""),
            (f"  {icon} AI Review", title_style),
            ("", ""),
            (f"  {response.summary}", body_style),
            ("", ""),
        ]

        if response.explanation:
            lines.append((f"  {response.explanation}", "dim"))
            lines.append(("", ""))

        if response.suggestion:
            lines.append((f"  💡 {response.suggestion}", "dim green"))
            lines.append(("", ""))

        lines.append((f"  — {self._provider.provider_name}", "dim"))
        total_tokens = response.input_tokens + response.output_tokens
        if total_tokens > 0:
            tok_in = response.input_tokens
            tok_out = response.output_tokens
            lines.append((
                f"  📊 {tok_in} in + {tok_out} out = {total_tokens} tok",
                "dim",
            ))

        try:
            advisory = self.query_one("#advisory-pane", AdvisoryPane)
            advisory.set_content(lines)
        except NoMatches:
            pass

    # ── Shell restart ─────────────────────────────────────────────

    def _restart_shell(self) -> None:
        """Restart the shell process."""
        try:
            shell = self.query_one("#shell-pane", ShellPane)
            shell.restart_shell()
            self._show_advisory_notice("Shell restarted.")
            self._sync_status_bar()
        except NoMatches:
            pass

    # ── Copy / Paste ─────────────────────────────────────────────

    def _do_copy(self) -> None:
        """Copy selected text from either pane to macOS clipboard."""
        try:
            import subprocess

            shell = self.query_one("#shell-pane", ShellPane)
            advisory = self.query_one("#advisory-pane", AdvisoryPane)

            # Check both panes for selection — advisory first, then shell
            if advisory.has_selection():
                text = advisory.get_selected_text()
                source = "advisory selection"
                advisory.clear_selection()
            elif shell.has_selection():
                text = shell.get_selected_text()
                source = "selection"
                shell.clear_selection()
            else:
                # No selection — inform user instead of copying entire screen
                self._show_advisory_notice("Nothing selected to copy.")
                return
            if text:
                subprocess.run(
                    ["pbcopy"],
                    input=text.encode("utf-8"),
                    check=True,
                    timeout=2,
                )
                self._show_advisory_notice(f"Copied {source} to clipboard.")
            else:
                self._show_advisory_notice("Nothing to copy.")
        except NoMatches:
            pass
        except Exception as e:
            self._show_advisory_notice(f"Copy failed: {e}")

    def _do_paste(self) -> None:
        """Paste from the macOS clipboard into the shell."""
        try:
            import subprocess

            result = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                timeout=2,
            )
            text = result.stdout.decode("utf-8", errors="replace")
            if text:
                shell = self.query_one("#shell-pane", ShellPane)
                # Use bracketed paste mode to safely handle multi-line content
                shell._pty.write(b"\x1b[200~" + text.encode("utf-8") + b"\x1b[201~")
                self._show_advisory_notice(f"Pasted {len(text)} chars.")
            else:
                self._show_advisory_notice("Clipboard is empty.")
        except NoMatches:
            pass
        except Exception as e:
            self._show_advisory_notice(f"Paste failed: {e}")

    # ── Debug display ────────────────────────────────────────────

    def _show_debug(self) -> None:
        """Show debug info in the advisory pane."""
        lines: list[tuple[str, str]] = [
            ("", ""),
            ("  Debug Info", "bold cyan underline"),
            ("", ""),
            (f"  Phase: {self.state.phase.name}", ""),
            (f"  AI: {'on' if self.state.ai_enabled else 'off'}", ""),
            (f"  Secret: {'on' if self.state.secret_mode else 'off'}", ""),
            (f"  Split: {self.state.split_ratio}", ""),
            (f"  Provider: {self._provider.provider_name}", ""),
            (f"  Configured: {self._provider.is_configured}", ""),
            ("", ""),
        ]

        try:
            shell = self.query_one("#shell-pane", ShellPane)
            cmd = extract_current_command(shell._screen)
            lines.append((f"  Current cmd: {cmd or '(empty)'}", "dim"))
        except NoMatches:
            pass

        try:
            advisory = self.query_one("#advisory-pane", AdvisoryPane)
            advisory.set_content(lines)
        except NoMatches:
            pass

    # ── Focus switching ───────────────────────────────────────────

    def action_focus_shell(self) -> None:
        """Focus the shell pane."""
        try:
            self.query_one("#shell-pane", ShellPane).focus()
        except NoMatches:
            pass

    def action_focus_advisory(self) -> None:
        """Focus the advisory pane."""
        try:
            self.query_one("#advisory-pane", AdvisoryPane).focus()
        except NoMatches:
            pass

    # ── Divider resize ────────────────────────────────────────────

    def action_shrink_divider(self) -> None:
        """Shrink the advisory pane (give more space to shell)."""
        shell_fr, advisory_fr = self.state.split_ratio
        if advisory_fr > _MIN_ADVISORY_FR and shell_fr < _MAX_SHELL_FR:
            self.state.split_ratio = (shell_fr + 1, advisory_fr - 1)
            self._apply_split_ratio()

    def action_grow_divider(self) -> None:
        """Grow the advisory pane (give more space to advisory)."""
        shell_fr, advisory_fr = self.state.split_ratio
        if advisory_fr < _MAX_ADVISORY_FR and shell_fr > _MIN_SHELL_FR:
            self.state.split_ratio = (shell_fr - 1, advisory_fr + 1)
            self._apply_split_ratio()

    def on_pane_divider_divider_dragged(self, message: PaneDivider.DividerDragged) -> None:
        """Handle mouse drag on the divider — smooth pixel-based resizing."""
        try:
            container = self.query_one("#main-container")
            shell_pane = self.query_one("#shell-pane", ShellPane)
            advisory_pane = self.query_one("#advisory-pane", AdvisoryPane)

            total_width = container.size.width - 1  # -1 for divider
            shell_width = shell_pane.size.width + message.delta_x
            advisory_width = total_width - shell_width

            # Clamp to minimum widths
            min_shell = 20
            min_advisory = 15
            shell_width = max(min_shell, min(shell_width, total_width - min_advisory))
            advisory_width = total_width - shell_width

            shell_pane.styles.width = shell_width
            advisory_pane.styles.width = advisory_width

            # Update state ratio to approximate the new split
            total = shell_width + advisory_width
            if total > 0:
                ratio_shell = max(1, round(shell_width / total * 8))
                ratio_advisory = max(1, 8 - ratio_shell)
                self.state.split_ratio = (ratio_shell, ratio_advisory)
        except NoMatches:
            pass

    def _apply_split_ratio(self) -> None:
        """Apply the current split ratio to the CSS layout."""
        shell_fr, advisory_fr = self.state.split_ratio
        try:
            shell_pane = self.query_one("#shell-pane", ShellPane)
            advisory_pane = self.query_one("#advisory-pane", AdvisoryPane)
            shell_pane.styles.width = f"{shell_fr}fr"
            advisory_pane.styles.width = f"{advisory_fr}fr"
        except NoMatches:
            pass

    # ── Status bar sync ───────────────────────────────────────────

    def _sync_status_bar(self) -> None:
        """Push current state to the status bar."""
        try:
            status = self.query_one("#status-bar", StatusBar)
            shell_name = "zsh"
            try:
                shell_name = self.query_one("#shell-pane", ShellPane).shell_name
            except NoMatches:
                pass
            status.update_state(
                ai_enabled=self.state.ai_enabled,
                secret_mode=self.state.secret_mode,
                shell_name=shell_name,
            )
        except NoMatches:
            pass

    # ── Advisory pane helpers ─────────────────────────────────────

    def _show_advisory_notice(self, message: str) -> None:
        """Show a brief notice in the advisory pane. First line bold, rest dim."""
        self._help_showing = False
        self._ai_review_showing = False
        styled_lines: list[tuple[str, str]] = [("", "")]
        first = True
        for line in message.split("\n"):
            if not line.strip():
                styled_lines.append(("", ""))
            elif first:
                styled_lines.append((f"  {line}", "bold"))
                first = False
            else:
                styled_lines.append((f"  {line}", "dim"))
        try:
            advisory = self.query_one("#advisory-pane", AdvisoryPane)
            advisory.set_content(styled_lines)
        except NoMatches:
            pass

    def _show_help(self) -> None:
        """Show the shortcut help in the advisory pane."""
        self._help_showing = True
        self._ai_review_showing = False
        try:
            advisory = self.query_one("#advisory-pane", AdvisoryPane)
            advisory.set_content([
                ("", ""),
                ("  Shortcuts", "bold cyan underline"),
                ("", ""),
                ("  Ctrl+Q         quit", ""),
                ("  F6             divider left", ""),
                ("  F7             divider right", ""),
                ("", ""),
                ("  Ctrl+G leader key:", "bold"),
                ("  Ctrl+G, R      AI review command", ""),
                ("  Ctrl+G, A      toggle AI on/off", ""),
                ("  Ctrl+G, S      toggle Secret mode", ""),
                ("  Ctrl+G, H      this help", ""),
                ("  Ctrl+G, X      restart shell", ""),
                ("  Ctrl+G, D      debug info", ""),
                ("  Ctrl+G, Q      quit (fallback)", ""),
                ("", ""),
                ("  Press any key to dismiss.", "dim"),
            ])
        except NoMatches:
            pass

    def _show_warnings(self, result) -> None:
        """Render local catalog warnings in the advisory pane."""
        from ridincligun.advisory.models import ReviewResult

        if not isinstance(result, ReviewResult) or not result.warnings:
            return

        risk_styles = {
            RiskLevel.DANGER: ("bold red", "red", "⛔"),
            RiskLevel.WARNING: ("bold yellow", "yellow", "⚠️"),
            RiskLevel.CAUTION: ("bold cyan", "dim cyan", "💡"),
        }

        lines: list[tuple[str, str]] = [("", "")]

        for warning in result.warnings:
            title_style, body_style, icon = risk_styles.get(
                warning.risk, ("bold", "dim", "ℹ️")
            )
            level_name = warning.risk.value.upper()
            lines.append((f"  {icon} {level_name}", title_style))
            lines.append(("", ""))
            lines.append((f"  {warning.summary}", body_style))
            lines.append(("", ""))
            if warning.suggestion:
                lines.append((f"  💡 {warning.suggestion}", "dim green"))
                lines.append(("", ""))

        try:
            advisory = self.query_one("#advisory-pane", AdvisoryPane)
            advisory.set_content(lines)
        except NoMatches:
            pass

    def _show_advisory_welcome(self) -> None:
        """Restore the advisory pane to its welcome state."""
        try:
            self.query_one("#advisory-pane", AdvisoryPane).clear()
        except NoMatches:
            pass

    # ── Quit ──────────────────────────────────────────────────────

    def action_quit(self) -> None:
        """Quit the application. Persists split ratio to config.toml."""
        # Save split ratio if it changed from the config default
        if self.state.split_ratio != self.config.split_ratio:
            save_split_ratio(self.config, self.state.split_ratio)
        try:
            shell = self.query_one("#shell-pane", ShellPane)
            shell.pty_process.stop()
        except NoMatches:
            pass
        self.exit()
