# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for suggestion extraction

"""Tests for AI suggestion command extraction (item g)."""

import pytest

from ridincligun.app import RidinCLIgunApp


@pytest.mark.parametrize("suggestion, expected", [
    # Backtick-quoted commands
    ("Use `rm -i file.txt` instead.", "rm -i file.txt"),
    ("Try `ls -la /tmp` for details.", "ls -la /tmp"),
    ("Run `git stash` before rebasing.", "git stash"),
    ("Consider using `chmod 644 file.txt` for safer permissions.", "chmod 644 file.txt"),
    # Command-like suggestions (starts with known verb)
    ("rm -i file.txt", "rm -i file.txt"),
    ("git push --force-with-lease", "git push --force-with-lease"),
    ("sudo chmod 644 file.txt", "sudo chmod 644 file.txt"),
    ("find . -name '*.tmp' -delete", "find . -name '*.tmp' -delete"),
    # Non-extractable (plain text advice)
    ("Consider reviewing the file first.", ""),
    ("None", ""),
    ("Check the documentation.", ""),
    ("", ""),
])
def test_extract_command(suggestion, expected):
    """Extraction handles various AI suggestion formats."""
    result = RidinCLIgunApp._extract_command_from_suggestion(suggestion)
    assert result == expected
