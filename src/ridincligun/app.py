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
from ridincligun.advisory.secret_detector import detect_secrets
from ridincligun.config import Config, load_config, save_split_ratio
from ridincligun.history import HistoryEntry, ReviewHistory, now_iso
from ridincligun.provider import create_provider
from ridincligun.provider.base import AIReviewResponse
from ridincligun.provider.deep_analysis import (
    check_deep_analysis_trigger,
    fetch_script,
    build_deep_analysis_prompt,
    DEEP_ANALYSIS_SYSTEM,
)
from ridincligun.provider.prompt import get_redaction_diff
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
        # AI provider — created via factory from config (supports anthropic, openai)
        self._provider = create_provider(self.config)
        self._review_task: asyncio.Task | None = None
        self._ai_review_showing = False  # True while an AI review is displayed
        self._last_ai_failed = False  # True if the most recent AI call failed
        self._pending_review_command: str | None = None  # awaiting preview confirmation
        self._last_suggestion: str = ""  # last AI suggestion command for insert (item g)
        self._history = ReviewHistory()  # append-only local review log (item k)
        self._model_select_showing = False  # True while model selector is visible

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
        """Handle leader key follow-up and modal key handlers."""
        # Model selector intercepts number keys
        if self._model_select_showing and not self._leader.active:
            if self._handle_model_select_key(event.key):
                event.stop()
                return

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
        """Dismiss help, model selector, or pending preview when the user types in the shell."""
        if self._pending_review_command is not None:
            self._pending_review_command = None
            self._show_advisory_notice("Review cancelled.")
        if self._model_select_showing:
            self._model_select_showing = False
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
            self.state.secrets_detected = False
            self._show_advisory_welcome()
            return

        # ── Secret detection (runs on every keystroke) ─────────────
        secret_result = detect_secrets(command)
        self.state.secrets_detected = secret_result.has_secrets

        if secret_result.has_secrets:
            self._ai_review_showing = False
            self._show_secret_warning(secret_result)
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
        # Cancel pending redaction preview on any action other than REVIEW
        if action != LeaderAction.REVIEW and self._pending_review_command is not None:
            self._pending_review_command = None

        match action:
            case LeaderAction.TOGGLE_AI:
                self.state.ai_enabled = not self.state.ai_enabled
                if self.state.ai_enabled and not self._provider.is_configured:
                    self._update_ai_status("offline")
                    self._show_advisory_notice(
                        "AI review: on\n\n"
                        "⚠ No API key configured.\n"
                        "Add it to ~/.config/ridincligun/.env\n"
                        "and restart."
                    )
                elif self.state.ai_enabled:
                    self._show_advisory_notice(
                        "AI review: on\n\n"
                        "Checking connection..."
                    )
                    # Validate provider in background — updates status on result
                    asyncio.create_task(self._validate_provider())
                else:
                    self._update_ai_status("")
                    self._show_advisory_notice("AI review: off")
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

            case LeaderAction.INSERT_SUGGESTION:
                self._insert_suggestion()

            case LeaderAction.CMD_HELP:
                self._show_cmd_help()

            case LeaderAction.MODEL_SELECT:
                self._show_model_selector()

            case LeaderAction.COPY:
                self._do_copy()

            case LeaderAction.PASTE:
                self._do_paste()

    # ── Secret warning ─────────────────────────────────────────────

    def _show_secret_warning(self, result) -> None:
        """Display a secret detection warning in the advisory pane."""
        from ridincligun.advisory.secret_detector import SecretDetectionResult

        if not isinstance(result, SecretDetectionResult) or not result.matches:
            return

        lines: list[tuple[str, str]] = [
            ("", ""),
            ("  🔒 Secrets Detected", "bold red"),
            ("", ""),
            ("  AI review auto-blocked.", "bold yellow"),
            ("", ""),
        ]

        for match in result.matches:
            lines.append((f"  ⚠ {match.description}", "red"))

        lines.append(("", ""))
        lines.append(("  Secrets should not be sent to AI.", "dim"))
        lines.append(("  Remove secrets before requesting", "dim"))
        lines.append(("  AI review.", "dim"))
        lines.append(("", ""))

        try:
            advisory = self.query_one("#advisory-pane", AdvisoryPane)
            advisory.set_content(lines)
        except NoMatches:
            pass

    # ── Redaction preview ───────────────────────────────────────────

    def _show_redaction_preview(self, diff) -> None:
        """Show what will be sent to AI vs. the original command."""
        from ridincligun.provider.prompt import RedactionDiff

        if not isinstance(diff, RedactionDiff):
            return

        lines: list[tuple[str, str]] = [
            ("", ""),
            ("  🔍 Redaction Preview", "bold cyan"),
            ("", ""),
            ("  Ctrl+G, R to confirm and send.", "bold green"),
            ("  Any other key to cancel.", "dim"),
            ("", ""),
            ("  Original:", "bold"),
            (f"  {diff.original}", "dim"),
            ("", ""),
            ("  Sent to AI:", "bold"),
            (f"  {diff.redacted}", "yellow"),
            ("", ""),
        ]

        if diff.placeholders:
            lines.append(("  Masked:", "bold"))
            for placeholder, reason in diff.placeholders:
                lines.append((f"  {placeholder} — {reason}", "dim yellow"))
            lines.append(("", ""))

        lines.append(("  Switch off in [privacy] config.", "dim"))

        try:
            advisory = self.query_one("#advisory-pane", AdvisoryPane)
            advisory.set_content(lines)
        except NoMatches:
            pass

    # ── AI Review ────────────────────────────────────────────────

    def _trigger_ai_review(self) -> None:
        """Trigger an AI review of the current command.

        If redaction preview is enabled and the command gets redacted,
        shows a preview first. Press Ctrl+G, R again to confirm.
        """
        # Second press confirms a pending preview
        if self._pending_review_command is not None:
            command = self._pending_review_command
            self._pending_review_command = None
            self._send_ai_review(command)
            return

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

        if self.state.secrets_detected:
            self._show_advisory_notice(
                "🔒 Secrets detected in command.\n\n"
                "AI review blocked to protect credentials.\n"
                "Remove secrets from the command first."
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

        # Show redaction preview if enabled and command gets redacted
        if self.config.show_redaction_preview:
            diff = get_redaction_diff(command)
            if diff.has_changes:
                self._pending_review_command = command
                self._show_redaction_preview(diff)
                return

        # No preview needed — send directly
        self._send_ai_review(command)

    def _send_ai_review(self, command: str) -> None:
        """Actually send the command for AI review."""
        # Cancel any in-flight review
        if self._review_task and not self._review_task.done():
            self._review_task.cancel()

        # Show loading state and clear any previous error status
        self.state.phase = Phase.REVIEW_LOADING
        self._update_ai_status("")
        self._show_advisory_notice(
            f"🔍 Reviewing: {command}\n\n"
            f"Asking {self._provider.provider_name}..."
        )

        # Launch async review
        self._review_task = asyncio.create_task(self._do_ai_review(command))

    async def _do_ai_review(self, command: str) -> None:
        """Perform the AI review asynchronously (Layer 2).

        After showing the review, checks if the command triggers deep
        analysis (Layer 3) and starts it automatically.
        """
        result = await self._provider.review(command)

        # Defense in depth: suppress result if secret mode was enabled
        # after the request was sent (race condition guard)
        if self.state.secret_mode:
            self.state.phase = Phase.TYPING
            return

        self.state.phase = Phase.REVIEW_READY

        if result.success and result.response:
            self._last_ai_failed = False
            self._update_ai_status("")
            self._show_ai_review(command, result.response)

            # Check for Layer 3: deep analysis of remote scripts
            trigger = check_deep_analysis_trigger(command)
            if trigger.should_analyze:
                asyncio.create_task(self._do_deep_analysis(command, trigger))
        else:
            self._last_ai_failed = True
            self._update_ai_status("offline")
            self._show_connection_error(result.error_message)

    async def _do_deep_analysis(self, command: str, trigger) -> None:
        """Layer 3: fetch and analyze a remote script.

        Appends results to the existing AI review in the advisory pane.
        """
        # Show "fetching" indicator appended to current review
        self._append_advisory_lines([
            ("", ""),
            ("  ⏳ Fetching script content...", "bold cyan"),
            (f"  {trigger.url}", "dim"),
        ])

        # Fetch the script
        result = await fetch_script(trigger.url)

        if self.state.secret_mode:
            return  # Suppressed

        if not result.success:
            self._append_advisory_lines([
                ("", ""),
                ("  ⚠ Could not fetch script", "bold yellow"),
                (f"  {result.error}", "dim"),
            ])
            return

        # Show script size, then send to AI
        size_info = f"{result.size_bytes:,} bytes"
        if result.truncated:
            size_info += " (truncated to 64KB)"

        self._append_advisory_lines([
            ("", ""),
            (f"  📄 Script fetched: {size_info}", "cyan"),
            ("  Analyzing content...", "bold cyan"),
        ])

        # Build deep analysis prompt and send to provider
        prompt = build_deep_analysis_prompt(
            trigger.url, result.content, result.truncated
        )
        analysis = await self._provider.review(
            prompt,
            context="deep_script_analysis",
        )

        if self.state.secret_mode:
            return

        if analysis.success and analysis.response:
            self._append_advisory_lines([
                ("", ""),
                ("  🔬 Script Analysis", "bold magenta"),
                ("", ""),
                (f"  {analysis.response.summary}", "yellow"),
                ("", ""),
            ])
            if analysis.response.explanation:
                self._append_advisory_lines([
                    (f"  {analysis.response.explanation}", "dim"),
                    ("", ""),
                ])
            if analysis.response.suggestion:
                self._append_advisory_lines([
                    (f"  💡 {analysis.response.suggestion}", "dim green"),
                    ("", ""),
                ])
        else:
            self._append_advisory_lines([
                ("", ""),
                ("  ⚠ Script analysis failed", "bold yellow"),
                (f"  {analysis.error_message}", "dim"),
            ])

    async def _validate_provider(self) -> None:
        """Quick background check if the AI provider is reachable.

        Sends a minimal review request. Updates status bar and advisory
        pane based on the result.
        """
        result = await self._provider.review("echo test")
        if result.success:
            self._last_ai_failed = False
            self._update_ai_status("")
            self._show_advisory_notice(
                "AI review: on\n\n"
                "✓ Connected to "
                f"{self._provider.provider_name}."
            )
        else:
            self._last_ai_failed = True
            self._update_ai_status("offline")
            self._show_connection_error(result.error_message)

    def _show_ai_review(self, command: str, response: AIReviewResponse) -> None:
        """Display an AI review result in the advisory pane. Persists until next review."""
        self._ai_review_showing = True

        # Store suggestion for insert shortcut (Ctrl+G, I)
        self._last_suggestion = response.suggestion if response.suggestion else ""

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
            lines.append((f"  💡 {response.suggestion}", "bold green"))
            lines.append(("  Ctrl+G, I to insert suggestion.", "dim cyan"))
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

        # Log to history (item k)
        self._history.append(HistoryEntry(
            timestamp=now_iso(),
            command=command,
            source="ai",
            risk=response.risk_assessment,
            summary=response.summary,
            suggestion=response.suggestion,
            provider=self._provider.provider_name,
            tokens=response.input_tokens + response.output_tokens,
        ))

    # ── Suggestion insert (item g) ──────────────────────────────────

    def _insert_suggestion(self) -> None:
        """Insert the last AI suggestion into the shell prompt.

        Clears the current command line first (Ctrl+U), then types the
        suggestion. The user remains sole authority — they must press
        Enter to execute.
        """
        if not self._last_suggestion:
            self._show_advisory_notice("No AI suggestion available.\nRequest a review first (Ctrl+G, R).")
            return

        # Extract just the command part from the suggestion text.
        # The AI may say "Use `rm -i file.txt` instead" — extract the backtick part.
        suggestion = self._extract_command_from_suggestion(self._last_suggestion)

        if not suggestion:
            self._show_advisory_notice(
                "Could not extract a command from\n"
                "the AI suggestion."
            )
            return

        try:
            shell = self.query_one("#shell-pane", ShellPane)
            # Clear current input line (Ctrl+U) then type the suggestion
            shell._pty.write(b"\x15")  # Ctrl+U — kill line
            shell._pty.write(suggestion.encode("utf-8"))
            self._show_advisory_notice(
                f"Inserted: {suggestion}\n\n"
                "Review before pressing Enter."
            )
        except NoMatches:
            pass

    @staticmethod
    def _extract_command_from_suggestion(suggestion: str) -> str:
        """Try to extract a runnable command from an AI suggestion string.

        Looks for backtick-quoted commands first, then tries to find
        a command sentence that starts with a known verb.
        """
        import re

        # Try backtick-quoted command: `some command here`
        backtick = re.search(r"`([^`]+)`", suggestion)
        if backtick:
            return backtick.group(1).strip()

        _CMD_VERBS = {
            "ls", "rm", "cp", "mv", "mkdir", "chmod", "chown", "find", "grep",
            "sed", "awk", "cat", "head", "tail", "sort", "tar", "zip", "unzip",
            "git", "docker", "kubectl", "npm", "pip", "python", "curl", "wget",
            "ssh", "scp", "rsync", "dd", "mount", "umount", "kill", "pkill",
            "sudo", "brew", "apt", "yum", "dnf", "pacman",
        }

        # Try to find a command fragment inside prose like
        # "Use rm -ri /tmp/test instead" or "Try: ls -la /home"
        # Split on prose intro words; avoid splitting on ". " inside commands
        fragments = re.split(r"(?:^|\s)(?:Use|Try|Run|Consider|Instead)[:\s]+",
                             suggestion, flags=re.IGNORECASE)
        for frag in fragments:
            frag = frag.strip().rstrip(".")
            words = frag.split()
            if not words:
                continue
            if words[0].lower() in _CMD_VERBS:
                # Take words that look like command parts (stop at prose).
                # A word is "prose" if it's a common English stop word AND
                # doesn't look like a flag or path (no leading - / . ~).
                _PROSE_WORDS = {
                    "instead", "first", "before", "after", "rather", "which",
                    "that", "this", "the", "for", "to", "or",
                    "and", "if", "when", "so", "but", "as",
                }
                cmd_parts = []
                for w in words:
                    # Stop at parenthetical explanations like "(owner has...)"
                    if w.startswith("("):
                        break
                    if (w.lower() in _PROSE_WORDS
                            and len(cmd_parts) > 1
                            and not w.startswith(("-", "/", ".", "~"))):
                        break
                    cmd_parts.append(w)
                return " ".join(cmd_parts)

        return ""

    # ── Command help (item c) ──────────────────────────────────────

    def _show_cmd_help(self) -> None:
        """Run `cmd --help` silently and display output in advisory pane."""
        try:
            shell = self.query_one("#shell-pane", ShellPane)
            command = extract_current_command(shell._screen)
        except NoMatches:
            return

        if not command.strip():
            self._show_advisory_notice("No command to look up.\nType a command first.")
            return

        # Extract the base command (first word, strip sudo)
        parts = command.strip().split()
        if parts[0] == "sudo" and len(parts) > 1:
            base_cmd = parts[1]
        else:
            base_cmd = parts[0]

        self._show_advisory_notice(
            f"Looking up: {base_cmd} --help\n\n"
            "Please wait..."
        )
        asyncio.create_task(self._fetch_cmd_help(base_cmd))

    async def _fetch_cmd_help(self, cmd: str) -> None:
        """Run `cmd --help` in a subprocess and display the output."""
        import shlex
        import subprocess

        try:
            # Security: validate command name — no shell metacharacters
            if not cmd.replace("-", "").replace("_", "").replace(".", "").isalnum():
                self._show_advisory_notice(
                    f"Invalid command name: {cmd}\n\n"
                    "Cannot look up help."
                )
                return

            # Run in a thread to not block the event loop
            result = await asyncio.to_thread(
                subprocess.run,
                [cmd, "--help"],
                capture_output=True,
                timeout=5,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"},
            )

            output = result.stdout.decode("utf-8", errors="replace")
            if not output:
                output = result.stderr.decode("utf-8", errors="replace")

            if not output.strip():
                self._show_advisory_notice(
                    f"No help output for: {cmd}\n\n"
                    "The command may not support --help."
                )
                return

            # Format for advisory pane
            lines: list[tuple[str, str]] = [
                ("", ""),
                (f"  📖 {cmd} --help", "bold cyan"),
                ("", ""),
            ]

            # Limit to ~80 lines to keep the pane manageable
            help_lines = output.splitlines()[:80]
            for help_line in help_lines:
                lines.append((f"  {help_line}", "dim"))

            if len(output.splitlines()) > 80:
                lines.append(("", ""))
                lines.append(("  ... (truncated)", "dim yellow"))

            lines.append(("", ""))
            lines.append(("  Press any key in shell to dismiss.", "dim cyan"))

            try:
                advisory = self.query_one("#advisory-pane", AdvisoryPane)
                advisory.set_content(lines)
            except NoMatches:
                pass

        except FileNotFoundError:
            self._show_advisory_notice(
                f"Command not found: {cmd}\n\n"
                "Make sure it's installed and in PATH."
            )
        except subprocess.TimeoutExpired:
            self._show_advisory_notice(
                f"{cmd} --help timed out (5s).\n\n"
                "The command may be interactive."
            )
        except Exception as e:
            self._show_advisory_notice(f"Help lookup failed: {e}")

    # ── Model selector (item j) ────────────────────────────────────

    _MODEL_OPTIONS: list[tuple[str, str, str]] = [
        # (display_name, provider_kind, model_id)
        # Mistral: https://docs.mistral.ai/getting-started/models
        ("Mistral Small", "mistral", "mistral-small-latest"),
        ("Mistral Large", "mistral", "mistral-large-latest"),
        # Anthropic: https://platform.claude.com/docs/en/docs/about-claude/models
        ("Anthropic Claude Sonnet 4", "anthropic", "claude-sonnet-4-20250514"),
        ("Anthropic Claude Haiku 4.5", "anthropic", "claude-haiku-4-5-20251001"),
        # OpenAI: https://platform.openai.com/docs/models
        ("OpenAI GPT-4o", "openai", "gpt-4o"),
        ("OpenAI GPT-4o mini", "openai", "gpt-4o-mini"),
    ]

    def _show_model_selector(self) -> None:
        """Show model/provider selection in the advisory pane."""
        self._model_select_showing = True
        current = self._provider.provider_name

        lines: list[tuple[str, str]] = [
            ("", ""),
            ("  🔧 Model Selection", "bold cyan"),
            ("", ""),
            (f"  Current: {current}", "bold"),
            ("", ""),
        ]

        for idx, (name, kind, model_id) in enumerate(self._MODEL_OPTIONS, 1):
            marker = " ◉" if model_id in current else " ○"
            lines.append((f"  {idx}{marker} {name}", ""))

        lines.append(("", ""))
        lines.append((f"  Type 1-{len(self._MODEL_OPTIONS)} to select.", "bold green"))
        lines.append(("  Any other key to cancel.", "dim"))
        lines.append(("", ""))
        lines.append(("  Changes apply immediately.", "dim"))
        lines.append(("  Persisted to config.toml.", "dim"))

        try:
            advisory = self.query_one("#advisory-pane", AdvisoryPane)
            advisory.set_content(lines)
        except NoMatches:
            pass

    def _handle_model_select_key(self, key: str) -> bool:
        """Handle a key press during model selection. Returns True if consumed."""
        if not self._model_select_showing:
            return False

        self._model_select_showing = False

        if key in ("1", "2", "3", "4"):
            idx = int(key) - 1
            if idx < len(self._MODEL_OPTIONS):
                name, kind, model_id = self._MODEL_OPTIONS[idx]
                self._switch_model(kind, model_id, name)
                return True

        self._show_advisory_notice("Model selection cancelled.")
        return True

    def _switch_model(self, kind: str, model_id: str, display_name: str) -> None:
        """Switch the AI provider/model and persist to config."""
        import os

        from ridincligun.config import ProviderSettings

        # Resolve the appropriate API key
        _KEY_MAP = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "mistral": "MISTRAL_API_KEY",
        }
        key_name = _KEY_MAP.get(kind, "ANTHROPIC_API_KEY")

        # Try .env first, then os.environ
        from dotenv import dotenv_values

        env_vars = {}
        if self.config.env_file.exists():
            env_vars = dotenv_values(self.config.env_file)

        api_key = env_vars.get(key_name, "") or os.environ.get(key_name, "") or ""

        # Update config
        self.config.provider = ProviderSettings(
            kind=kind,
            model=model_id,
            timeout_seconds=self.config.provider.timeout_seconds,
            max_tokens=self.config.provider.max_tokens,
        )
        self.config.api_key = api_key

        # Recreate provider
        self._provider = create_provider(self.config)

        # Persist to config.toml
        self._persist_provider_config(kind, model_id)

        if not api_key:
            self._update_ai_status("offline")
            self._show_advisory_notice(
                f"Switched to {display_name}\n\n"
                f"⚠ No API key for {kind}.\n"
                f"Add {key_name} to\n"
                "~/.config/ridincligun/.env\n"
                "and restart."
            )
        else:
            self._show_advisory_notice(
                f"Switched to {display_name}\n\n"
                "Checking connection..."
            )
            asyncio.create_task(self._validate_provider())

        self._sync_status_bar()

    def _persist_provider_config(self, kind: str, model: str) -> None:
        """Write provider kind and model to config.toml."""
        import re as _re

        config_file = self.config.config_file
        if not config_file.exists():
            return

        try:
            text = config_file.read_text()

            # Update kind
            if _re.search(r'^kind\s*=', text, _re.MULTILINE):
                text = _re.sub(
                    r'^kind\s*=\s*"[^"]*"',
                    f'kind = "{kind}"',
                    text, count=1, flags=_re.MULTILINE,
                )
            # Update model
            if _re.search(r'^model\s*=', text, _re.MULTILINE):
                text = _re.sub(
                    r'^model\s*=\s*"[^"]*"',
                    f'model = "{model}"',
                    text, count=1, flags=_re.MULTILINE,
                )

            config_file.write_text(text)
        except OSError:
            pass  # Non-critical

    # ── Review history display (item k) ───────────────────────────

    def _show_review_history(self) -> None:
        """Show recent review history in the advisory pane."""
        entries = self._history.read_recent(20)

        if not entries:
            self._show_advisory_notice("No review history yet.\nHistory is recorded after AI reviews.")
            return

        risk_icons = {
            "danger": "⛔",
            "warning": "⚠️",
            "caution": "💡",
            "safe": "✅",
        }

        lines: list[tuple[str, str]] = [
            ("", ""),
            ("  📜 Review History", "bold cyan"),
            (f"  ({len(entries)} most recent)", "dim"),
            ("", ""),
        ]

        for entry in entries:
            icon = risk_icons.get(entry.risk, "ℹ️")
            # Truncate long commands
            cmd = entry.command[:40] + "..." if len(entry.command) > 40 else entry.command
            lines.append((f"  {icon} {cmd}", ""))
            lines.append((f"    {entry.summary[:60]}", "dim"))
            ts = entry.timestamp[:19].replace("T", " ")  # trim to readable
            lines.append((f"    {ts} via {entry.source}", "dim cyan"))
            lines.append(("", ""))

        total = self._history.entry_count()
        lines.append((f"  Total entries: {total}", "dim"))
        lines.append((f"  File: {self._history.file_path}", "dim"))

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

    # ── AI status helpers ───────────────────────────────────────────

    def _update_ai_status(self, status: str) -> None:
        """Update the AI connection status in the status bar."""
        try:
            bar = self.query_one("#status-bar", StatusBar)
            bar.update_state(ai_status=status)
        except NoMatches:
            pass

    def _show_connection_error(self, error_message: str) -> None:
        """Show a clear connection error in the advisory pane."""
        provider = self._provider.provider_name
        lines: list[tuple[str, str]] = [
            ("", ""),
            ("  ⚠ Connection Failed", "bold red"),
            ("", ""),
            (f"  Could not reach {provider}.", "yellow"),
            ("", ""),
            (f"  {error_message}", "dim"),
            ("", ""),
            ("  Check:", "bold"),
            ("  - Network connection", "dim"),
            ("  - API key in ~/.config/ridincligun/.env", "dim"),
            ("  - Provider status page", "dim"),
            ("", ""),
            ("  After updating the API key,", "dim yellow"),
            ("  restart the app to apply.", "dim yellow"),
            ("", ""),
            ("  Local advisories still active.", "dim green"),
        ]
        try:
            advisory = self.query_one("#advisory-pane", AdvisoryPane)
            advisory.set_content(lines)
        except NoMatches:
            pass

    # ── Advisory pane helpers ─────────────────────────────────────

    def _append_advisory_lines(self, lines: list[tuple[str, str]]) -> None:
        """Append styled lines to the current advisory content."""
        try:
            advisory = self.query_one("#advisory-pane", AdvisoryPane)
            advisory.append_content(lines)
        except NoMatches:
            pass

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
                ("  Ctrl+G, I      insert AI suggestion", ""),
                ("  Ctrl+G, ?      show cmd --help", ""),
                ("  Ctrl+G, A      toggle AI on/off", ""),
                ("  Ctrl+G, M      model selection", ""),
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
