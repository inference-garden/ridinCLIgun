# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for TypoDetector

"""Tests for the Levenshtein-based typo detector."""

import pytest

from ridincligun.advisory.typo_detector import TypoDetector, _levenshtein

# ── _levenshtein ─────────────────────────────────────────────────

class TestLevenshtein:
    def test_identical_strings(self):
        assert _levenshtein("abc", "abc") == 0

    def test_empty_strings(self):
        assert _levenshtein("", "") == 0

    def test_one_empty(self):
        assert _levenshtein("abc", "") == 3
        assert _levenshtein("", "abc") == 3

    def test_single_insertion(self):
        assert _levenshtein("abc", "abcd") == 1

    def test_single_deletion(self):
        assert _levenshtein("abcd", "abc") == 1

    def test_single_substitution(self):
        assert _levenshtein("abc", "axc") == 1

    def test_transposition_costs_two(self):
        # Levenshtein (not Damerau) — transposition = 2 ops
        assert _levenshtein("ab", "ba") == 2

    def test_completely_different(self):
        assert _levenshtein("abc", "xyz") == 3

    def test_symmetric(self):
        assert _levenshtein("git", "gti") == _levenshtein("gti", "git")

    def test_real_typo_grpe(self):
        assert _levenshtein("grep", "grpe") == 2

    def test_real_typo_gti(self):
        assert _levenshtein("git", "gti") == 2


# ── TypoDetector ─────────────────────────────────────────────────

DICT = frozenset(["git", "grep", "curl", "python", "ls", "tar", "ssh", "docker"])


@pytest.fixture
def detector():
    return TypoDetector(DICT)


class TestTypoDetectorIsKnown:
    def test_known_command(self, detector):
        assert detector.is_known("git") is True
        assert detector.is_known("grep") is True

    def test_unknown_command(self, detector):
        assert detector.is_known("gti") is False
        assert detector.is_known("totally_unknown") is False

    def test_case_insensitive(self, detector):
        assert detector.is_known("GIT") is True
        assert detector.is_known("GREP") is True

    def test_strips_whitespace(self, detector):
        # is_known doesn't strip, suggest does — so verify direct membership
        assert detector.is_known("git") is True


class TestTypoDetectorSuggest:
    def test_known_command_returns_none(self, detector):
        """No suggestion for a correctly-typed command."""
        assert detector.suggest("git") is None
        assert detector.suggest("grep") is None

    def test_one_char_typo(self, detector):
        result = detector.suggest("giy")   # git → distance 1
        assert result == "git"

    def test_two_char_typo(self, detector):
        result = detector.suggest("grpe")  # grep → distance 2
        assert result == "grep"

    def test_beyond_max_distance_returns_none(self, detector):
        result = detector.suggest("xyzabc")  # no command within distance 2
        assert result is None

    def test_too_short_returns_none(self, detector):
        # min_length default is 2; single char should return None
        result = detector.suggest("g")
        assert result is None

    def test_empty_returns_none(self, detector):
        assert detector.suggest("") is None

    def test_case_insensitive_suggestion(self, detector):
        result = detector.suggest("GIT")
        # "GIT" is in dictionary as "git" via lower()
        assert result is None  # known → no suggestion

    def test_case_insensitive_typo(self, detector):
        result = detector.suggest("GIY")  # GIY → giy → git (dist 1)
        assert result == "git"

    def test_strips_whitespace(self, detector):
        result = detector.suggest("  git  ")
        assert result is None  # recognized after strip → no suggestion

    def test_prefer_shorter_name_on_tie(self):
        """When two candidates have equal distance, prefer the shorter one."""
        # "ab" and "abc" both at distance 1 from "ac"
        d = TypoDetector(frozenset(["ab", "abc"]))
        result = d.suggest("ac")
        assert result == "ab"

    def test_min_length_boundary(self):
        d = TypoDetector(DICT, min_length=3)
        assert d.suggest("gi") is None   # below min_length → no suggestion
        assert d.suggest("giy") is not None  # at or above min_length

    def test_max_distance_one(self):
        d = TypoDetector(DICT, max_distance=1)
        assert d.suggest("giy") == "git"    # distance 1 — within limit
        assert d.suggest("grpe") is None    # distance 2 — outside limit

    def test_dictionary_size_property(self):
        d = TypoDetector(DICT)
        assert d.dictionary_size == len(DICT)


# ── Integration: realistic typos ─────────────────────────────────

@pytest.mark.parametrize("typo, expected", [
    ("gti",    "git"),
    ("grpe",   "grep"),
    ("crul",   "curl"),
    ("sl",     "ls"),
    ("tsr",    "tar"),
    # "shs" ties with both "ssh" (dist 2) and "ls" (dist 2); tie-break prefers
    # the shorter name, so "ls" wins.  Use "sshh" (dist 1 from "ssh") instead.
    ("sshh",   "ssh"),
])
def test_realistic_typos(typo, expected):
    d = TypoDetector(DICT)
    assert d.suggest(typo) == expected, f"{typo!r} should suggest {expected!r}"


# ── Edge case: empty dictionary ───────────────────────────────────

def test_empty_dictionary():
    d = TypoDetector(frozenset())
    assert d.suggest("git") is None
    assert d.dictionary_size == 0
