# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Application coordinator

"""Main Textual application for ridinCLIgun.

Composes the two-pane layout, owns AppState, and coordinates messages.
Handles the Ctrl+G leader key, divider resize, config, and AI review.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches

from ridincligun.advisory.engine import AdvisoryEngine
from ridincligun.advisory.models import RiskLevel
from ridincligun.advisory.secret_detector import detect_secrets
from ridincligun.config import Config, load_config, save_split_ratio
from ridincligun.history import HistoryEntry, ReviewHistory, now_iso
from ridincligun.i18n import detect_system_locale, get_locale, set_locale, t
from ridincligun.provider import create_provider
from ridincligun.provider.base import AIReviewResponse
from ridincligun.provider.deep_analysis import (
    build_deep_analysis_prompt,
    check_deep_analysis_trigger,
    fetch_script,
    fit_script_to_context,
)
from ridincligun.provider.prompt import (
    build_locale_context,
    build_system_prompt,
    get_redaction_diff,
    resolve_category,
)
from ridincligun.shell.input_parser import extract_current_command
from ridincligun.shortcuts.bindings import LeaderAction, LeaderState
from ridincligun.state import AppState, Phase
from ridincligun.ui.advisory_pane import AdvisoryPane
from ridincligun.ui.divider import PaneDivider
from ridincligun.ui.history_screen import HistoryBrowserScreen
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
        ("escape", "dismiss_help", "Dismiss help"),
        ("f6", "grow_divider", "Divider left (more advisory)"),
        ("f7", "shrink_divider", "Divider right (more shell)"),
    ]

    def __init__(self, config: Config | None = None) -> None:
        super().__init__()
        self.config = config or load_config()
        # Initialize i18n — use config language, auto-detect, or fallback to "en"
        locale = self.config.language or detect_system_locale()
        set_locale(locale)
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
        self._pending_paste_text: str | None = None  # awaiting paste confirmation (secrets)
        self._secrets_review_confirmed = False  # True after first Ctrl+G,R with secrets
        self._last_suggestion: str = ""  # last AI suggestion command for insert (item g)
        self._history = ReviewHistory()  # append-only local review log (item k)
        self._model_select_showing = False  # True while model selector is visible
        # Incremented on secret-mode toggle + new review; stale results discarded
        self._review_generation = 0

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
            if self.config.first_run:
                self._show_onboarding()
        except NoMatches:
            pass
        # Scan PATH for installed binaries and extend the typo dictionary.
        # Runs asynchronously so startup is not blocked.
        asyncio.create_task(self._init_typo_dictionary())

    async def _init_typo_dictionary(self) -> None:
        """Scan PATH directories and register binaries with the engine."""
        path_commands: set[str] = set()
        for dir_str in os.environ.get("PATH", "").split(os.pathsep):
            try:
                for entry in Path(dir_str).iterdir():
                    if entry.is_file() and os.access(entry, os.X_OK):
                        path_commands.add(entry.name.lower())
            except (PermissionError, FileNotFoundError, NotADirectoryError):
                pass
        self._engine.set_extra_commands(frozenset(path_commands))

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
        """Dismiss model selector or pending preview when the user types in the shell.

        Help content (shortcuts and cmd --help) persists while typing —
        only replaced by a new advisory event (warning, review, or Escape).
        """
        if self._pending_review_command is not None:
            self._pending_review_command = None
            self._toast(t("toast.review_cancelled"))
        if self._model_select_showing:
            self._model_select_showing = False

    def on_shell_pane_input_changed(self, message: ShellPane.InputChanged) -> None:
        """Analyze the current command and show/clear warnings accordingly.

        AI review and help persist while the user edits the command.
        AI review clears when:
        - Command becomes empty (executed via Enter, or cleared via Ctrl+C/U)
        - A new review is requested (Ctrl+G, R)
        Help clears only on Escape or explicit new leader action.
        """
        command = message.command

        # ── Secret detection always runs (state update) ────────────
        secret_result = detect_secrets(command) if command else None
        self.state.secrets_detected = (
            secret_result.has_secrets if secret_result else False
        )

        # Help showing → keep help visible, don't update advisory pane
        if self._help_showing:
            return

        if not command:
            # Command empty → clear everything (including AI review)
            self._ai_review_showing = False
            self._show_advisory_welcome()
            return

        if secret_result and secret_result.has_secrets:
            self._ai_review_showing = False
            self._show_secret_warning(secret_result)
            return

        # AI review showing + command still has content → keep review visible
        if self._ai_review_showing:
            return

        result = self._engine.analyze(command, locale=get_locale())
        self._show_local_advisory(result)

    # ── Leader key ────────────────────────────────────────────────

    def action_dismiss_help(self) -> None:
        """Dismiss help content from the advisory pane (Escape key)."""
        if self._help_showing:
            self._help_showing = False
            self._show_advisory_welcome()

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
                    self._toast(t("toast.ai_on_no_key"), severity="warning")
                elif self.state.ai_enabled:
                    self._toast(t("toast.ai_on"))
                    # Validate provider in background — updates status on result
                    asyncio.create_task(self._validate_provider())
                else:
                    self._update_ai_status("")
                    self._toast(t("toast.ai_off"))
                self._sync_status_bar()

            case LeaderAction.TOGGLE_SECRET:
                self.state.secret_mode = not self.state.secret_mode
                # Invalidate any in-flight AI review when entering secret mode
                if self.state.secret_mode:
                    self._review_generation += 1
                    if self._review_task and not self._review_task.done():
                        self._review_task.cancel()
                        self._review_task = None
                    self._toast(t("toast.secret_on"))
                else:
                    self._toast(t("toast.secret_off"))
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

            case LeaderAction.HISTORY:
                self._show_review_history()

            case LeaderAction.SETTINGS:
                self._open_settings()

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
            (f"  {t('secrets.title')}", "bold red"),
            ("", ""),
            (f"  {t('secrets.auto_blocked')}", "bold yellow"),
            ("", ""),
        ]

        for match in result.matches:
            lines.append((f"  ⚠ {match.description}", "red"))

        lines.append(("", ""))
        lines.append((f"  {t('secrets.warning_line1')}", "dim"))
        lines.append((f"  {t('secrets.warning_line2')}", "dim"))
        lines.append((f"  {t('secrets.warning_line3')}", "dim"))
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
            (f"  {t('redaction.title')}", "bold cyan"),
            ("", ""),
            (f"  {t('redaction.confirm')}", "bold green"),
            (f"  {t('redaction.cancel')}", "dim"),
            ("", ""),
            (f"  {t('redaction.original')}", "bold"),
            (f"  {diff.original}", "dim"),
            ("", ""),
            (f"  {t('redaction.sent_to_ai')}", "bold"),
            (f"  {diff.redacted}", "yellow"),
            ("", ""),
        ]

        if diff.placeholders:
            lines.append((f"  {t('redaction.masked')}", "bold"))
            for placeholder, reason in diff.placeholders:
                lines.append((f"  {placeholder} — {reason}", "dim yellow"))
            lines.append(("", ""))

        lines.append((f"  {t('redaction.config_hint')}", "dim"))

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
            self._show_advisory_notice(t("notice.ai_off"))
            return

        if self.state.secret_mode:
            self._show_advisory_notice(t("notice.secret_mode_on"))
            return

        if self.state.secrets_detected and not self._secrets_review_confirmed:
            self._secrets_review_confirmed = True
            self._show_advisory_notice(
                f"{t('secrets.detected_in_command')}\n\n"
                f"{t('secrets.send_anyway')}\n"
                f"{t('secrets.confirm_send')}"
            )
            return
        # Reset confirmation flag after use
        self._secrets_review_confirmed = False

        if not self._provider.is_configured:
            self._show_advisory_notice(t("notice.no_api_key"))
            return

        # Get current command from shell
        try:
            shell = self.query_one("#shell-pane", ShellPane)
            command = extract_current_command(shell._screen)
        except NoMatches:
            return

        if not command.strip():
            self._show_advisory_notice(t("notice.no_command"))
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

        # Increment generation so stale responses are discarded
        self._review_generation += 1

        # Resolve prompt category from local engine's matched families
        result = self._engine.analyze(command, locale=get_locale())
        family_ids = [w.family for w in result.warnings]
        category = resolve_category(family_ids)
        system_prompt = build_system_prompt(category, self.config.review_mode, get_locale())

        # Show loading state and clear any previous error status
        self.state.phase = Phase.REVIEW_LOADING
        self._update_ai_status("")
        self._show_advisory_notice(
            f"{t('review.loading', command=command)}\n\n"
            f"{t('review.asking', provider=self._provider.provider_name)}"
        )

        # Launch async review with current generation
        gen = self._review_generation
        self._review_task = asyncio.create_task(
            self._do_ai_review(command, gen, system_prompt)
        )

    async def _do_ai_review(
        self, command: str, generation: int = 0, system_prompt: str = "",
    ) -> None:
        """Perform the AI review asynchronously (Layer 2).

        After showing the review, checks if the command triggers deep
        analysis (Layer 3) and starts it automatically.

        Args:
            generation: Review generation counter at launch time.
                        If it no longer matches self._review_generation
                        when the response arrives, the result is stale
                        (secret mode was toggled or a new review started)
                        and must be discarded without rendering.
            system_prompt: Composed system prompt (base + category + mode).
        """
        result = await self._provider.review(
            command,
            context=build_locale_context(get_locale()),
            system_prompt=system_prompt,
        )

        # Defense in depth: suppress result if generation changed
        # (secret mode toggled or new review started during flight)
        if generation != self._review_generation or self.state.secret_mode:
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
            (f"  {t('deep.fetching')}", "bold cyan"),
            (f"  {trigger.url}", "dim"),
        ])

        # Fetch the script
        result = await fetch_script(trigger.url)

        # Remove "fetching" status line
        self._remove_advisory_lines(t("deep.fetching"))

        if self.state.secret_mode:
            return  # Suppressed

        if not result.success:
            self._append_advisory_lines([
                ("", ""),
                (f"  {t('deep.fetch_failed')}", "bold yellow"),
                (f"  {result.error}", "dim"),
                ("", ""),
                (f"  {t('deep.fetch_caution1')}", "dim"),
                (f"  {t('deep.fetch_caution2')}", "dim yellow"),
            ])
            return

        # Fit script to model's context window
        model_name = self._provider.model_id if self._provider else ""
        content, was_truncated = fit_script_to_context(
            result.content, model_name,
        )

        # Show script size, then send to AI
        size_info = f"{result.size_bytes:,} bytes"
        lines: list[tuple[str, str]] = [
            ("", ""),
            (f"  {t('deep.script_fetched', size=size_info)}", "cyan"),
        ]
        if was_truncated:
            lines.extend([
                (f"  {t('deep.too_large')}", "bold yellow"),
                (f"  {t('deep.partial')}", "dim yellow"),
            ])
        lines.append((f"  {t('deep.analyzing')}", "bold cyan"))

        self._append_advisory_lines(lines)

        # Build deep analysis prompt and send to provider
        prompt = build_deep_analysis_prompt(
            trigger.url, content, was_truncated, locale=get_locale(),
        )
        analysis = await self._provider.review(
            prompt,
            context="deep_script_analysis",
        )

        # Remove "analyzing" status line
        self._remove_advisory_lines(t("deep.analyzing"))

        if self.state.secret_mode:
            return

        if analysis.success and analysis.response:
            self._append_advisory_lines([
                ("", ""),
                (f"  {t('deep.analysis_title')}", "bold magenta"),
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
            if was_truncated:
                self._append_advisory_lines([
                    (f"  {t('deep.partial_title')}", "bold yellow"),
                    (f"  {t('deep.partial_line1')}", "dim yellow"),
                    (f"  {t('deep.partial_line2')}", "dim yellow"),
                    (f"  {t('deep.partial_line3')}", "dim yellow"),
                    (f"  {t('deep.partial_line4')}", "dim yellow"),
                    ("", ""),
                ])

            self._history.append(HistoryEntry(
                timestamp=now_iso(),
                command=command,
                source="deep_analysis",
                risk=analysis.response.risk_assessment,
                summary=analysis.response.summary,
                explanation=analysis.response.explanation,
                suggestion=analysis.response.suggestion,
                provider=self._provider.provider_name,
                tokens=analysis.response.input_tokens + analysis.response.output_tokens,
            ))
        else:
            self._append_advisory_lines([
                ("", ""),
                (f"  {t('deep.analysis_failed')}", "bold yellow"),
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
            self._toast(t("toast.connected", provider=self._provider.provider_name))
            # Clear the "Switched to X / Checking connection…" notice and restore
            # the normal advisory view for whatever command is currently in the input.
            try:
                from ridincligun.ui.command_input import CommandInput
                cmd = self.query_one(CommandInput).value.strip()
                result_local = self._engine.analyze(cmd, locale=get_locale())
                self._show_local_advisory(result_local)
            except Exception:
                self._show_advisory_welcome()
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
            (f"  {icon} {t('review.title')}", title_style),
            ("", ""),
            (f"  {response.summary}", body_style),
            ("", ""),
        ]

        if response.explanation:
            lines.append((f"  {response.explanation}", "dim"))
            lines.append(("", ""))

        if response.suggestion:
            lines.append((f"  💡 {response.suggestion}", "bold green"))
            lines.append((f"  {t('review.insert_hint')}", "dim cyan"))
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
            explanation=response.explanation,
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
            self._show_advisory_notice(t("notice.no_suggestion"))
            return

        # Extract just the command part from the suggestion text.
        # The AI may say "Use `rm -i file.txt` instead" — extract the backtick part.
        suggestion = self._extract_command_from_suggestion(self._last_suggestion)

        if not suggestion:
            self._show_advisory_notice(t("notice.extract_failed"))
            return

        try:
            shell = self.query_one("#shell-pane", ShellPane)
            # Clear current input line (Ctrl+U) then type the suggestion
            shell._pty.write(b"\x15")  # Ctrl+U — kill line
            shell._pty.write(suggestion.encode("utf-8"))
            self._show_advisory_notice(t("notice.inserted", suggestion=suggestion))
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

        _CMD_VERBS = {  # noqa: N806
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
                _PROSE_WORDS = {  # noqa: N806
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
            self._show_advisory_notice(t("cmd_help.no_command"))
            return

        # Extract the base command (first word, strip sudo)
        parts = command.strip().split()
        if parts[0] == "sudo" and len(parts) > 1:
            base_cmd = parts[1]
        else:
            base_cmd = parts[0]

        self._show_advisory_notice(
            f"{t('cmd_help.looking_up', cmd=base_cmd)}\n\n"
            f"{t('cmd_help.trying')}"
        )
        asyncio.create_task(self._fetch_cmd_help(base_cmd))

    async def _fetch_cmd_help(self, cmd: str) -> None:
        """Fetch help for a command using a fallback chain.

        Tries in order: --help, -h, man (first 40 lines).
        Sets _help_showing so content persists while the user edits.
        """
        import subprocess

        try:
            # Security: validate command name — no shell metacharacters
            if not cmd.replace("-", "").replace("_", "").replace(".", "").isalnum():
                self._show_advisory_notice(t("cmd_help.invalid_name", cmd=cmd))
                return

            _PATH_ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"}  # noqa: N806

            output = ""
            source = ""

            # Try --help, then -h. Accept output only when:
            # - rc == 0 (command recognized the flag), or
            # - stdout has content (some tools print help to stdout with rc != 0)
            # Skip stderr-only output on failure — that's an error, not help.
            for flag, label in [("--help", "--help"), ("-h", "-h")]:
                try:
                    result = await asyncio.to_thread(
                        subprocess.run,
                        [cmd, flag],
                        capture_output=True,
                        timeout=5,
                        env=_PATH_ENV,
                    )
                    stdout = result.stdout.decode("utf-8", errors="replace")
                    stderr = result.stderr.decode("utf-8", errors="replace")

                    if result.returncode == 0 and (stdout.strip() or stderr.strip()):
                        output = stdout if stdout.strip() else stderr
                        source = label
                        break
                    elif stdout.strip():
                        # Some tools exit non-zero but still print help to stdout
                        output = stdout
                        source = label
                        break
                    # stderr-only with non-zero rc → flag not recognized, try next
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    continue

            # Fallback to man page (first 40 lines)
            if not output:
                try:
                    result = await asyncio.to_thread(
                        subprocess.run,
                        ["man", cmd],
                        capture_output=True,
                        timeout=5,
                        env={**_PATH_ENV, "MANPAGER": "cat", "COLUMNS": "80"},
                    )
                    out = result.stdout.decode("utf-8", errors="replace")
                    if out.strip():
                        # Take first 40 lines of man output
                        man_lines = out.splitlines()[:40]
                        output = "\n".join(man_lines)
                        source = "man"
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass

            if not output.strip():
                self._show_advisory_notice(t("cmd_help.not_found", cmd=cmd))
                return

            # Format for advisory pane
            lines: list[tuple[str, str]] = [
                ("", ""),
                (f"  📖 {cmd} {source}", "bold cyan"),
                ("", ""),
            ]

            # Limit to ~80 lines to keep the pane manageable
            help_lines = output.splitlines()[:80]
            for help_line in help_lines:
                lines.append((f"  {help_line}", "dim"))

            if len(output.splitlines()) > 80:
                lines.append(("", ""))
                lines.append((f"  {t('cmd_help.truncated')}", "dim yellow"))

            lines.append(("", ""))
            lines.append((f"  {t('cmd_help.dismiss')}", "dim cyan"))

            self._help_showing = True
            self._ai_review_showing = False
            try:
                advisory = self.query_one("#advisory-pane", AdvisoryPane)
                advisory.set_content(lines)
            except NoMatches:
                pass

        except FileNotFoundError:
            self._show_advisory_notice(t("cmd_help.cmd_not_found", cmd=cmd))
        except subprocess.TimeoutExpired:
            self._show_advisory_notice(t("cmd_help.timeout"))
        except Exception as e:
            self._show_advisory_notice(t("cmd_help.help_failed", error=e))

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
            (f"  {t('model.title')}", "bold cyan"),
            ("", ""),
            (f"  {t('model.current', current=current)}", "bold"),
            ("", ""),
        ]

        for idx, (name, kind, model_id) in enumerate(self._MODEL_OPTIONS, 1):
            marker = " ◉" if model_id in current else " ○"
            lines.append((f"  {idx}{marker} {name}", ""))

        lines.append(("", ""))
        lines.append((f"  {t('model.select_hint', count=len(self._MODEL_OPTIONS))}", "bold green"))
        lines.append((f"  {t('model.cancel_hint')}", "dim"))
        lines.append(("", ""))
        lines.append((f"  {t('model.apply_note')}", "dim"))
        lines.append((f"  {t('model.persist_note')}", "dim"))

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

        if key.isdigit() and 1 <= int(key) <= len(self._MODEL_OPTIONS):
            idx = int(key) - 1
            name, kind, model_id = self._MODEL_OPTIONS[idx]
            self._switch_model(kind, model_id, name)
            return True

        self._toast(t("toast.model_cancelled"))
        self._show_advisory_welcome()
        return True

    def _switch_model(self, kind: str, model_id: str, display_name: str) -> None:
        """Switch the AI provider/model and persist to config."""
        import os

        from ridincligun.config import ProviderSettings

        # Resolve the appropriate API key
        _KEY_MAP = {  # noqa: N806
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
                f"{t('model.switched', name=display_name)}\n\n"
                f"{t('model.no_key', kind=kind)}\n"
                f"{t('model.add_key', key_name=key_name)}\n"
                f"{t('model.env_path')}\n"
                f"{t('model.restart')}"
            )
        else:
            self._show_advisory_notice(
                f"{t('model.switched', name=display_name)}\n\n"
                f"{t('model.checking')}"
            )
            asyncio.create_task(self._validate_provider())

        self._sync_status_bar()

    def _persist_provider_config(self, kind: str, model: str) -> None:
        """Write provider kind and model to config.toml."""
        from ridincligun.config import save_provider_config
        save_provider_config(self.config, kind, model)

    # ── Review history display (item k) ───────────────────────────

    def _show_review_history(self) -> None:
        """Open the modal review history browser."""
        self.push_screen(HistoryBrowserScreen(self._history))

    # ── Shell restart ─────────────────────────────────────────────

    def _restart_shell(self) -> None:
        """Restart the shell process."""
        try:
            shell = self.query_one("#shell-pane", ShellPane)
            shell.restart_shell()
            self._toast(t("toast.shell_restarted"))
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
                self._toast(t("toast.nothing_to_copy"))
                return
            if text:
                subprocess.run(
                    ["pbcopy"],
                    input=text.encode("utf-8"),
                    check=True,
                    timeout=2,
                )
                self._toast(t("toast.copied", source=source))
            else:
                self._toast(t("toast.nothing_to_copy_empty"))
        except NoMatches:
            pass
        except Exception as e:
            self._toast(t("toast.copy_failed", error=e), severity="error")

    def _do_paste(self) -> None:
        """Paste from the macOS clipboard into the shell.

        Checks clipboard content for secrets before inserting.
        If secrets found, shows a warning — user must press Ctrl+G, V
        again to confirm paste.
        """
        # If pending confirmed paste, execute it
        if self._pending_paste_text is not None:
            text = self._pending_paste_text
            self._pending_paste_text = None
            try:
                shell = self.query_one("#shell-pane", ShellPane)
                shell._pty.write(b"\x1b[200~" + text.encode("utf-8") + b"\x1b[201~")
                self._toast(t("toast.pasted", count=len(text)))
            except NoMatches:
                pass
            return

        try:
            import subprocess

            result = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                timeout=2,
            )
            text = result.stdout.decode("utf-8", errors="replace")
            if not text:
                self._toast(t("toast.clipboard_empty"))
                return

            # Check for secrets in clipboard content (if enabled)
            secret_result = detect_secrets(text) if self.config.clipboard_safety else None
            if secret_result and secret_result.has_secrets:
                self._pending_paste_text = text
                kinds = ", ".join(dict.fromkeys(m.kind for m in secret_result.matches))
                self._show_advisory_notice(
                    f"{t('secrets.detected_in_clipboard')}\n\n"
                    f"{t('secrets.clipboard_found', kinds=kinds)}\n\n"
                    f"{t('secrets.clipboard_confirm')}\n"
                    f"{t('secrets.clipboard_cancel')}"
                )
                return

            # No secrets — paste directly
            shell = self.query_one("#shell-pane", ShellPane)
            shell._pty.write(b"\x1b[200~" + text.encode("utf-8") + b"\x1b[201~")
            self._toast(t("toast.pasted", count=len(text)))
        except NoMatches:
            pass
        except Exception as e:
            self._toast(t("toast.paste_failed", error=e), severity="error")

    # ── Settings ──────────────────────────────────────────────────

    def _open_settings(self) -> None:
        """Open the settings modal screen."""
        from ridincligun.ui.settings_screen import SettingsScreen

        def _on_settings_close(result: str | None) -> None:
            """Refresh UI after settings closes (language may have changed).

            If result == "model_select" the user pressed Enter on the
            provider/model row — open the model selector immediately.
            """
            self._sync_status_bar()
            if result == "model_select":
                self._show_model_selector()
            else:
                self._show_advisory_welcome()

        self.push_screen(SettingsScreen(self.config), callback=_on_settings_close)

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
            (f"  {t('connection.title')}", "bold red"),
            ("", ""),
            (f"  {t('connection.unreachable', provider=provider)}", "yellow"),
            ("", ""),
            (f"  {error_message}", "dim"),
            ("", ""),
            (f"  {t('connection.check_title')}", "bold"),
            (f"  {t('connection.check_network')}", "dim"),
            (f"  {t('connection.check_key')}", "dim"),
            (f"  {t('connection.check_status')}", "dim"),
            ("", ""),
            (f"  {t('connection.restart_hint1')}", "dim yellow"),
            (f"  {t('connection.restart_hint2')}", "dim yellow"),
            ("", ""),
            (f"  {t('connection.local_active')}", "dim green"),
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

    def _remove_advisory_lines(self, marker: str) -> None:
        """Remove advisory lines containing the given marker text."""
        try:
            advisory = self.query_one("#advisory-pane", AdvisoryPane)
            advisory.remove_lines_containing(marker)
        except NoMatches:
            pass

    def _toast(self, message: str, *, severity: str = "information") -> None:
        """Show a brief, non-blocking toast notification.

        Use this for transient feedback (copy confirm, mode toggles, etc.)
        that must NOT replace advisory pane content.
        """
        self.notify(message, severity=severity, timeout=3)  # type: ignore[arg-type]

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
                (f"  {t('help.title')}", "bold cyan underline"),
                ("", ""),
                (f"  Ctrl+Q         {t('help.quit')}", ""),
                (f"  F6             {t('help.divider_left')}", ""),
                (f"  F7             {t('help.divider_right')}", ""),
                ("", ""),
                (f"  {t('help.leader_title')}", "bold"),
                (f"  Ctrl+G, R      {t('help.review')}", ""),
                (f"  Ctrl+G, I      {t('help.insert')}", ""),
                (f"  Ctrl+G, K      {t('help.history')}", ""),
                (f"  Ctrl+G, ?      {t('help.cmd_help')}", ""),
                (f"  Ctrl+G, A      {t('help.toggle_ai')}", ""),
                (f"  Ctrl+G, M      {t('help.model_select')}", ""),
                (f"  Ctrl+G, G      {t('help.settings')}", ""),
                (f"  Ctrl+G, S      {t('help.toggle_secret')}", ""),
                (f"  Ctrl+G, H      {t('help.this_help')}", ""),
                (f"  Ctrl+G, X      {t('help.restart_shell')}", ""),
                (f"  Ctrl+G, D      {t('help.debug')}", ""),
                (f"  Ctrl+G, Q      {t('help.quit_fallback')}", ""),
                ("", ""),
                (f"  {t('help.dismiss')}", "dim"),
            ])
        except NoMatches:
            pass

    def _show_local_advisory(self, result) -> None:
        """Render the full local advisory: warnings + tldr examples + typo hint."""
        from ridincligun.advisory.models import ReviewResult

        if not isinstance(result, ReviewResult):
            self._show_advisory_welcome()
            return

        lines: list[tuple[str, str]] = [("", "")]

        # ── Risk warnings ─────────────────────────────────────────
        # Use 1-cell Unicode symbols (not emoji) for reliable alignment.
        risk_styles = {
            RiskLevel.DANGER:  ("bold red",    "red",      "✖"),
            RiskLevel.WARNING: ("bold yellow",  "yellow",   "▲"),
            RiskLevel.CAUTION: ("bold cyan",    "dim cyan", "◆"),
        }
        for warning in result.warnings:
            title_style, body_style, icon = risk_styles.get(
                warning.risk, ("bold", "dim", "●")
            )
            lines.append((f"  {icon} {warning.risk.value.upper()}", title_style))
            lines.append(("", ""))
            lines.append((f"  {warning.summary}", body_style))
            lines.append(("", ""))
            if warning.suggestion:
                lines.append((f"  ▸ {warning.suggestion}", "dim green"))
                lines.append(("", ""))

        # ── tldr usage examples ───────────────────────────────────
        if result.tldr_page and result.tldr_page.examples:
            page = result.tldr_page
            if result.warnings:
                lines.append(("  ─────────────────────", "dim"))
                lines.append(("", ""))
            lines.append((f"  {page.command}", "bold cyan"))
            lines.append((f"  {page.description}", "dim"))
            lines.append(("", ""))
            for ex in page.examples:
                lines.append((f"  {ex.description}", "dim"))
                lines.append((f"  {ex.command}", "cyan"))
                lines.append(("", ""))

        # ── Typo suggestion ───────────────────────────────────────
        elif result.typo_suggestion:
            lines.append((
                f"  {t('typo.did_you_mean', suggestion=result.typo_suggestion)}",
                "bold yellow",
            ))
            lines.append(("", ""))

        # ── Fallback: nothing to show ─────────────────────────────
        elif not result.warnings:
            self._show_advisory_welcome()
            return

        try:
            advisory = self.query_one("#advisory-pane", AdvisoryPane)
            advisory.set_content(lines)
        except NoMatches:
            pass

    def _show_warnings(self, result) -> None:
        """Backwards-compatible shim — delegates to _show_local_advisory."""
        self._show_local_advisory(result)

    def _show_onboarding(self) -> None:
        """Show first-run onboarding content in the advisory pane."""
        lines: list[tuple[str, str]] = [
            ("", ""),
            (f"  {t('onboarding.title')}", "bold cyan"),
            ("", ""),
            (f"  {t('onboarding.tagline')}", "dim"),
            (f"  {t('onboarding.motto')}", "dim"),
            ("", ""),
            (f"  {t('onboarding.shortcuts_title')}", "bold"),
            (f"  {t('onboarding.shortcut_review')}", ""),
            (f"  {t('onboarding.shortcut_help')}", ""),
            (f"  {t('onboarding.shortcut_settings')}", ""),
            (f"  {t('onboarding.shortcut_all')}", ""),
            ("", ""),
            (f"  {t('onboarding.setup_title')}", "bold"),
            (f"  {t('onboarding.setup_hint')}", "dim"),
            (f"  {t('onboarding.setup_detail')}", "dim"),
            ("", ""),
            (f"  {t('onboarding.start_hint')}", "dim green"),
        ]
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
