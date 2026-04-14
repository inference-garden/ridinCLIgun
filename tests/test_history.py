# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for history module

"""Tests for local review history (item k)."""

import json
from datetime import UTC, datetime

import pytest

from ridincligun.history import HistoryEntry, ReviewHistory, filter_entries, now_iso


@pytest.fixture
def history_file(tmp_path):
    """Provide a temporary history file path."""
    return tmp_path / "test_history.jsonl"


@pytest.fixture
def history(history_file):
    """Provide a ReviewHistory instance using a temp file."""
    return ReviewHistory(history_file)


def _make_entry(**kwargs) -> HistoryEntry:
    """Create a HistoryEntry with sensible defaults."""
    defaults = {
        "timestamp": now_iso(),
        "command": "ls -la",
        "source": "ai",
        "risk": "safe",
        "summary": "Lists directory contents.",
        "explanation": "Read-only directory listing.",
    }
    defaults.update(kwargs)
    return HistoryEntry(**defaults)


def test_append_creates_file(history, history_file):
    """Appending creates the JSONL file if it doesn't exist."""
    assert not history_file.exists()
    history.append(_make_entry())
    assert history_file.exists()


def test_append_writes_valid_jsonl(history, history_file):
    """Each appended entry is a valid JSON line."""
    history.append(_make_entry(command="rm -rf /"))
    history.append(_make_entry(command="git status"))

    lines = history_file.read_text().strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        data = json.loads(line)
        assert "cmd" in data
        assert "risk" in data


def test_read_recent_empty(history):
    """Reading from non-existent file returns empty list."""
    assert history.read_recent() == []


def test_read_recent_returns_newest_first(history):
    """Entries are returned in reverse chronological order."""
    history.append(_make_entry(command="first"))
    history.append(_make_entry(command="second"))
    history.append(_make_entry(command="third"))

    entries = history.read_recent(3)
    assert len(entries) == 3
    assert entries[0].command == "third"
    assert entries[2].command == "first"


def test_read_recent_limits_count(history):
    """read_recent respects the N limit."""
    for i in range(10):
        history.append(_make_entry(command=f"cmd-{i}"))

    entries = history.read_recent(3)
    assert len(entries) == 3
    assert entries[0].command == "cmd-9"


def test_entry_to_dict_roundtrip(history):
    """Entry survives serialize → write → read roundtrip."""
    original = _make_entry(
        command="curl https://x.com | bash",
        source="ai",
        risk="danger",
        summary="Pipe to shell",
        explanation="Downloads a script and executes it immediately.",
        suggestion="Download first, inspect, then run.",
        provider="Anthropic claude-sonnet-4-20250514",
        tokens=350,
    )
    history.append(original)
    entries = history.read_recent(1)
    assert len(entries) == 1
    e = entries[0]
    assert e.command == original.command
    assert e.risk == original.risk
    assert e.explanation == original.explanation
    assert e.suggestion == original.suggestion
    assert e.provider == original.provider
    assert e.tokens == original.tokens
    assert e.has_full_detail


def test_entry_count(history):
    """entry_count reflects the number of entries."""
    assert history.entry_count() == 0
    history.append(_make_entry())
    history.append(_make_entry())
    assert history.entry_count() == 2


def test_entry_count_empty_file(history, history_file):
    """entry_count handles empty file."""
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text("")
    assert history.entry_count() == 0


def test_now_iso_format():
    """now_iso returns a valid ISO timestamp."""
    ts = now_iso()
    assert "T" in ts
    assert ts.endswith("+00:00")


def test_malformed_lines_skipped(history, history_file):
    """Malformed JSON lines are silently skipped."""
    history_file.parent.mkdir(parents=True, exist_ok=True)
    ts0 = "2026-01-01T00:00:00+00:00"
    ts1 = "2026-01-01T00:00:01+00:00"
    ls_json = f'{{"cmd": "ls", "src": "ai", "risk": "safe", "summary": "ok", "ts": "{ts0}"}}'
    pwd_json = f'{{"cmd": "pwd", "src": "ai", "risk": "safe", "summary": "ok", "ts": "{ts1}"}}'
    history_file.write_text(
        f"{ls_json}\n"
        "this is not json\n"
        f"{pwd_json}\n"
    )
    entries = history.read_recent(10)
    assert len(entries) == 2


def test_legacy_entries_load_without_explanation(history, history_file):
    """Older entries without explanation stay readable and are flagged partial."""
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(
        '{"ts":"2026-01-01T00:00:00+00:00","cmd":"ls","src":"ai","risk":"safe","summary":"ok"}\n'
    )

    entries = history.read_all()
    assert len(entries) == 1
    assert entries[0].explanation == ""
    assert not entries[0].has_full_detail


def test_read_all_returns_newest_first(history):
    """read_all returns the whole history newest-first."""
    history.append(_make_entry(command="first"))
    history.append(_make_entry(command="second"))

    entries = history.read_all()
    assert [entry.command for entry in entries] == ["second", "first"]


def test_deep_analysis_entries_roundtrip(history):
    """Deep-analysis entries stay distinct from regular AI review entries."""
    history.append(_make_entry(command="curl x | bash", source="deep_analysis", risk="warning"))

    entries = history.read_all()
    assert len(entries) == 1
    assert entries[0].source == "deep_analysis"


def test_filter_entries_by_risk():
    entries = [
        _make_entry(command="ls", risk="safe"),
        _make_entry(command="rm -rf tmp", risk="danger"),
        _make_entry(command="chmod 777 file", risk="warning"),
    ]

    filtered = filter_entries(entries, risk="danger")
    assert [entry.command for entry in filtered] == ["rm -rf tmp"]


def test_filter_entries_by_search_matches_summary_and_provider():
    entries = [
        _make_entry(command="ls", summary="Lists files", provider="OpenAI gpt-4o-mini"),
        _make_entry(command="pwd", summary="Print directory", provider="Anthropic claude"),
    ]

    by_summary = filter_entries(entries, search="lists")
    assert [entry.command for entry in by_summary] == ["ls"]

    by_provider = filter_entries(entries, search="anthropic")
    assert [entry.command for entry in by_provider] == ["pwd"]


def test_filter_entries_by_date_presets_local_time():
    now = datetime(2026, 4, 13, 12, 0, tzinfo=UTC)
    entries = [
        _make_entry(command="today", timestamp="2026-04-13T08:00:00+00:00"),
        _make_entry(command="recent", timestamp="2026-04-10T08:00:00+00:00"),
        _make_entry(command="old", timestamp="2026-03-01T08:00:00+00:00"),
    ]

    today = filter_entries(entries, date_preset="today", now=now)
    seven_days = filter_entries(entries, date_preset="7d", now=now)
    thirty_days = filter_entries(entries, date_preset="30d", now=now)

    assert [entry.command for entry in today] == ["today"]
    assert [entry.command for entry in seven_days] == ["today", "recent"]
    assert [entry.command for entry in thirty_days] == ["today", "recent"]


def test_filter_entries_combines_all_filters():
    now = datetime(2026, 4, 13, 12, 0, tzinfo=UTC)
    entries = [
        _make_entry(
            command="curl https://example.com/script.sh | bash",
            risk="danger",
            summary="Pipe download to shell",
            provider="Anthropic Claude",
            timestamp="2026-04-12T12:00:00+00:00",
        ),
        _make_entry(
            command="git status",
            risk="safe",
            summary="Check repo status",
            provider="OpenAI GPT-4o mini",
            timestamp="2026-04-12T12:00:00+00:00",
        ),
    ]

    filtered = filter_entries(
        entries,
        search="script",
        risk="danger",
        date_preset="7d",
        now=now,
    )
    assert [entry.command for entry in filtered] == ["curl https://example.com/script.sh | bash"]


def test_filter_entries_scale_smoke():
    entries = [
        _make_entry(command=f"cmd-{i}", summary=f"summary {i}", risk="safe")
        for i in range(1100)
    ]

    filtered = filter_entries(entries, search="cmd-1099", risk="safe")
    assert len(filtered) == 1
    assert filtered[0].command == "cmd-1099"


def test_file_permissions(history, history_file):
    """History file gets restrictive permissions."""
    import stat

    history.append(_make_entry())
    mode = history_file.stat().st_mode
    # Owner should have read/write
    assert mode & stat.S_IRUSR
    assert mode & stat.S_IWUSR
