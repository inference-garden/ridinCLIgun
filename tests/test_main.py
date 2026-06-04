# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun - CLI entry point tests

"""Tests for the `ridincligun` CLI entry point (ridincligun.__main__).

These pin the non-TUI `--version` behaviour the Homebrew formula's `test do`
block relies on: it must print the version to stdout, exit 0, and never build
the TUI (which would require a TTY and hang under `brew test`).
"""

import sys

import pytest

import ridincligun.__main__ as entry
from ridincligun import __version__
from ridincligun.__main__ import main


def test_version_flag_prints_to_stdout_and_exits_zero(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ridincligun", "--version"])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 0
    captured = capsys.readouterr()
    # brew's shell_output captures stdout — the version MUST land there.
    assert __version__ in captured.out
    assert "ridincligun" in captured.out


def test_version_flag_does_not_build_the_tui(monkeypatch):
    """--version must short-circuit before constructing RidinCLIgunApp."""
    monkeypatch.setattr(sys, "argv", ["ridincligun", "--version"])

    def _fail(*_args, **_kwargs):
        raise AssertionError("RidinCLIgunApp must not be built for --version")

    monkeypatch.setattr(entry, "RidinCLIgunApp", _fail)

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 0
