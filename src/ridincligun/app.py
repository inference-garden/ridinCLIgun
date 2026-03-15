"""Main Textual application for ridinCLIgun.

Composes the two-pane layout, owns AppState, and coordinates messages.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches

from ridincligun.state import AppState
from ridincligun.ui.advisory_pane import AdvisoryPane
from ridincligun.ui.shell_pane import ShellPane
from ridincligun.ui.status_bar import StatusBar


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
    ]

    def __init__(self) -> None:
        super().__init__()
        self.state = AppState()

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-container"):
            yield ShellPane(id="shell-pane")
            yield AdvisoryPane(id="advisory-pane")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        """Initialize the app after mounting."""
        # Focus the shell pane by default
        try:
            shell = self.query_one("#shell-pane", ShellPane)
            shell.focus()
            # Update status bar with shell name
            status = self.query_one("#status-bar", StatusBar)
            status.update_state(
                ai_enabled=self.state.ai_enabled,
                secret_mode=self.state.secret_mode,
                shell_name=shell.shell_name,
            )
        except NoMatches:
            pass

    def action_quit(self) -> None:
        """Quit the application."""
        # Clean up PTY before exiting
        try:
            shell = self.query_one("#shell-pane", ShellPane)
            shell.pty_process.stop()
        except NoMatches:
            pass
        self.exit()
