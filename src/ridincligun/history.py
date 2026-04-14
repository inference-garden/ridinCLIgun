# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Command review history (JSONL)

"""Local review history for ridinCLIgun.

Append-only JSONL log of commands, warnings, AI verdicts, and timestamps.
Never leaves the machine. Used for audit and learning.

File location: ~/.config/ridincligun/history.jsonl
"""

from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    explanation: str = ""
    suggestion: str = ""
    provider: str = ""
    tokens: int = 0
    has_full_detail: bool = True

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {
            "ts": self.timestamp,
            "cmd": self.command,
            "src": self.source,
            "risk": self.risk,
            "summary": self.summary,
            "explanation": self.explanation,
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
        return self._read_entries(limit=n)

    def read_all(self) -> list[HistoryEntry]:
        """Read all history entries in reverse chronological order."""
        return self._read_entries(limit=None)

    def _read_entries(self, limit: int | None) -> list[HistoryEntry]:
        """Read history entries newest-first, optionally capped at ``limit``."""
        if not self._file.exists():
            return []

        try:
            entries: list[HistoryEntry] = []
            with open(self._file, encoding="utf-8") as f:
                lines = f.readlines()

            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    has_full_detail = "explanation" in data
                    entries.append(HistoryEntry(
                        timestamp=data.get("ts", ""),
                        command=data.get("cmd", ""),
                        source=data.get("src", ""),
                        risk=data.get("risk", ""),
                        summary=data.get("summary", ""),
                        explanation=data.get("explanation", ""),
                        suggestion=data.get("suggestion", ""),
                        provider=data.get("provider", ""),
                        tokens=data.get("tokens", 0),
                        has_full_detail=has_full_detail,
                    ))
                except (json.JSONDecodeError, KeyError):
                    continue  # Skip malformed entries

                if limit is not None and len(entries) >= limit:
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
    return datetime.now(UTC).isoformat(timespec="seconds")


def filter_entries(
    entries: list[HistoryEntry],
    *,
    search: str = "",
    risk: str = "all",
    date_preset: str = "all",
    now: datetime | None = None,
) -> list[HistoryEntry]:
    """Filter history entries in memory for the browser UI.

    Search is case-insensitive substring matching against command,
    summary, and provider. Date presets are evaluated in local time.
    """
    normalized_search = search.strip().casefold()
    normalized_risk = risk.strip().lower()
    normalized_date = date_preset.strip().lower()
    local_now = (now or datetime.now().astimezone()).astimezone()

    filtered: list[HistoryEntry] = []
    for entry in entries:
        if normalized_risk not in ("", "all") and entry.risk.lower() != normalized_risk:
            continue
        if normalized_search:
            haystack = " ".join(
                part for part in (entry.command, entry.summary, entry.provider) if part
            ).casefold()
            if normalized_search not in haystack:
                continue
        if not _matches_date_preset(entry.timestamp, normalized_date, local_now):
            continue
        filtered.append(entry)
    return filtered


def _matches_date_preset(timestamp: str, preset: str, now: datetime) -> bool:
    """Return whether a timestamp matches the selected date preset."""
    if preset in ("", "all"):
        return True

    entry_dt = _parse_timestamp(timestamp)
    if entry_dt is None:
        return False

    local_dt = entry_dt.astimezone()
    if preset == "today":
        return local_dt.date() == now.date()
    if preset == "7d":
        return local_dt >= now - timedelta(days=7)
    if preset == "30d":
        return local_dt >= now - timedelta(days=30)
    return True


def _parse_timestamp(timestamp: str) -> datetime | None:
    """Best-effort parse for persisted ISO timestamps."""
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
