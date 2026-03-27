# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — PTY subprocess management

"""PTY process management for ridinCLIgun.

Forks a real shell in a pseudo-terminal. Provides read/write/resize/stop.
Does NOT interpret terminal escape sequences — that's the UI widget's job.
"""

from __future__ import annotations

import fcntl
import os
import pty
import signal
import struct
import subprocess
import termios
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class PtyProcess:
    """Manages a child process running in a PTY."""

    def __init__(self, shell: str | None = None, rows: int = 24, cols: int = 80) -> None:
        self._shell = shell or os.environ.get("SHELL", "/bin/zsh")
        self._rows = rows
        self._cols = cols
        self._master_fd: int | None = None
        self._child_pid: int | None = None
        self._running = False

    @property
    def master_fd(self) -> int | None:
        """File descriptor for the master side of the PTY."""
        return self._master_fd

    @property
    def running(self) -> bool:
        return self._running

    @property
    def shell_name(self) -> str:
        """Short name of the shell (e.g. 'zsh', 'bash')."""
        return os.path.basename(self._shell)

    def start(self) -> None:
        """Fork a PTY and exec the shell."""
        if self._running:
            return

        # Create PTY pair
        master_fd, slave_fd = pty.openpty()

        # Set initial terminal size
        self._set_winsize(slave_fd, self._rows, self._cols)

        # Fork the child process
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"

        # SECURITY: Strip provider API keys from the shell environment.
        # The embedded shell and its children (plugins, prompts, subprocesses)
        # do not need these credentials. See FINDING-02 in security audit.
        for key in list(env):
            if key.endswith("_API_KEY") or key.endswith("_SECRET_KEY"):
                del env[key]

        self._child_pid = subprocess.Popen(
            [self._shell, "-l"],  # login shell
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            preexec_fn=os.setsid,
            env=env,
            close_fds=True,
        ).pid

        # Close slave in parent — child owns it now
        os.close(slave_fd)

        # Set master to non-blocking
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        self._master_fd = master_fd
        self._running = True

    def write(self, data: bytes) -> None:
        """Send raw bytes to the PTY (keystrokes)."""
        if self._master_fd is not None and self._running:
            try:
                os.write(self._master_fd, data)
            except OSError:
                self._running = False

    def read(self, size: int = 65536) -> bytes:
        """Non-blocking read from PTY. Returns b'' if nothing available."""
        if self._master_fd is None or not self._running:
            return b""
        try:
            return os.read(self._master_fd, size)
        except BlockingIOError:
            return b""
        except OSError:
            self._running = False
            return b""

    def resize(self, rows: int, cols: int) -> None:
        """Update the PTY terminal size (sends TIOCSWINSZ ioctl)."""
        self._rows = rows
        self._cols = cols
        if self._master_fd is not None:
            self._set_winsize(self._master_fd, rows, cols)

    def stop(self) -> None:
        """Terminate the child process and clean up."""
        if self._child_pid is not None:
            try:
                os.kill(self._child_pid, signal.SIGHUP)
            except ProcessLookupError:
                pass
            self._child_pid = None

        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None

        self._running = False

    @staticmethod
    def _set_winsize(fd: int, rows: int, cols: int) -> None:
        """Set the terminal window size on a file descriptor."""
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
