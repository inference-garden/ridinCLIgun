"""Local review history for ridinCLIgun.

Append-only JSONL log of commands, warnings, AI verdicts, and timestamps.
Never leaves the machine. Used for audit and learning.

File location: ~/.config/ridincligun/history.jsonl
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Max history file size before rotation (5 MB)
_MAX_FILE_SIZE = 5 * 1024 * 1024


@dataclass(frozen=True)
class HistoryEntry:
    """A single review history entry."""

    timestamp: str
    command: str
    source: str  # "local", "ai", "deep_analysis"
    risk: str  # "safe", "caution", "warning", "danger"
    summary: str
    suggestion: str = ""
    provider: str = ""
    tokens: int = 0

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {
            "ts": self.timestamp,
            "cmd": self.command,
            "src": self.source,
            "risk": self.risk,
            "summary": self.summary,
            "suggestion": self.suggestion,
            "provider": self.provider,
            "tokens": self.tokens,
        }


class ReviewHistory:
    """Append-only JSONL review history.

    Thread-safe via file-level appends. No locking needed for
    single-process append-only writes.
    """

    def __init__(self, history_file: Path | None = None) -> None:
        self._file = history_file or (
            Path.home() / ".config" / "ridincligun" / "history.jsonl"
        )

    @property
    def file_path(self) -> Path:
        return self._file

    def append(self, entry: HistoryEntry) -> None:
        """Append a single entry to the history file.

        Creates the file and parent directory if needed.
        Restricts permissions to owner-only (0600).
        Silently fails on I/O errors — history is non-critical.
        """
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)

            # Rotate if too large
            if self._file.exists() and self._file.stat().st_size > _MAX_FILE_SIZE:
                self._rotate()

            line = json.dumps(entry.to_dict(), ensure_ascii=False) + "\n"

            with open(self._file, "a", encoding="utf-8") as f:
                f.write(line)

            # Ensure owner-only permissions
            self._secure_permissions()
        except OSError:
            pass  # Non-critical — history is a convenience feature

    def read_recent(self, n: int = 50) -> list[HistoryEntry]:
        """Read the N most recent history entries.

        Returns entries in reverse chronological order (newest first).
        """
        if not self._file.exists():
            return []

        try:
            entries: list[HistoryEntry] = []
            with open(self._file, encoding="utf-8") as f:
                lines = f.readlines()

            # Read from the end
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(HistoryEntry(
                        timestamp=data.get("ts", ""),
                        command=data.get("cmd", ""),
                        source=data.get("src", ""),
                        risk=data.get("risk", ""),
                        summary=data.get("summary", ""),
                        suggestion=data.get("suggestion", ""),
                        provider=data.get("provider", ""),
                        tokens=data.get("tokens", 0),
                    ))
                except (json.JSONDecodeError, KeyError):
                    continue  # Skip malformed entries

                if len(entries) >= n:
                    break

            return entries
        except OSError:
            return []

    def _rotate(self) -> None:
        """Rotate the history file: keep the newer half, discard the older."""
        try:
            with open(self._file, encoding="utf-8") as f:
                lines = f.readlines()
            # Keep the newer half
            half = len(lines) // 2
            with open(self._file, "w", encoding="utf-8") as f:
                f.writelines(lines[half:])
        except OSError:
            pass

    def _secure_permissions(self) -> None:
        """Ensure history file is owner-only readable/writable."""
        try:
            current = self._file.stat().st_mode
            if current & (stat.S_IRGRP | stat.S_IROTH):
                self._file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
        except OSError:
            pass

    def entry_count(self) -> int:
        """Count entries in the history file."""
        if not self._file.exists():
            return 0
        try:
            with open(self._file, encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except OSError:
            return 0


def now_iso() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
