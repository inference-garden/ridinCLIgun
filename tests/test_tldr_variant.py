# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for variant-aware offline help (S4-5)

"""Corpus-pinned tests for the offline-help refinement.

Three layers, all offline/synchronous/deterministic:
  L1  subcommand resolution — narrow the tldr page to the typed variant.
  L2  example ranking        — float the examples matching typed flags/args.
  L3  flag-level detail       — explain the typed flags the page documents.

The behavioral tests run against the *real* bundled catalog (like
``test_advisory_engine.py``) so they pin the actual user-visible behavior; the
helper tests pin the deterministic rules without a catalog dependency.
"""

from __future__ import annotations

import json

import pytest

from ridincligun.advisory.engine import (
    AdvisoryEngine,
    _example_signals,
    _extract_signals,
    _is_keyword,
    _rank_examples,
    _resolve_variant,
)
from ridincligun.advisory.tldr_store import TldrExample, TldrPage, TldrStore


@pytest.fixture
def engine():
    return AdvisoryEngine()


# ── Layer 1 — subcommand resolution (real catalog) ────────────────


def test_l1_subcommand_page_is_resolved(engine):
    """Typing a subcommand switches to that subcommand's page."""
    result = engine.analyze("git commit")
    assert result.tldr_page is not None
    assert result.tldr_page.command == "git-commit"
    assert result.matched_command == "git-commit"


def test_l1_subcommand_resolved_with_flags_and_args(engine):
    result = engine.analyze('git commit -m "wip"')
    assert result.tldr_page.command == "git-commit"
    assert result.matched_command == "git-commit"


def test_l1_base_command_has_no_matched_variant(engine):
    """A bare base command behaves exactly as before (no refinement shown)."""
    result = engine.analyze("git")
    assert result.tldr_page.command == "git"
    assert result.matched_command is None


def test_l1_env_prefix_stripped_before_resolution(engine):
    result = engine.analyze("FOO=bar git commit")
    assert result.tldr_page.command == "git-commit"
    assert result.matched_command == "git-commit"


def test_l1_unknown_subcommand_falls_back_to_base(engine):
    """No dedicated sub-page → graceful fallback to the base command page."""
    result = engine.analyze("git wibblewobble")
    assert result.tldr_page.command == "git"
    assert result.matched_command is None


def test_l1_native_dash_command_is_not_de_dashed(engine):
    """`apt-get` is its own command, not an `apt` refinement."""
    result = engine.analyze("apt-get install cowsay")
    assert result.tldr_page.command == "apt-get"
    assert result.matched_command is None  # consumed exactly the base token


def test_l1_deep_subcommand_resolves(engine):
    result = engine.analyze("docker buildx du")
    assert result.tldr_page.command == "docker-buildx-du"
    assert result.matched_command == "docker-buildx-du"


# ── Layer 2 — example ranking (real catalog) ──────────────────────


def test_l2_matching_flag_floats_to_top(engine):
    result = engine.analyze('git commit -m "wip"')
    assert result.ranked_examples
    top_ex, top_is_match = result.ranked_examples[0]
    assert top_is_match is True
    assert "-m" in top_ex.command or "--message" in top_ex.command


def test_l2_amend_flag_floats_to_top(engine):
    result = engine.analyze("git commit --amend")
    top_ex, top_is_match = result.ranked_examples[0]
    assert top_is_match is True
    assert "--amend" in top_ex.command


def test_l2_no_flags_keeps_catalog_order_and_no_matches(engine):
    """No typed flags/args → original order, nothing highlighted (today's behavior)."""
    page = engine._tldr.lookup("git-commit")
    result = engine.analyze("git commit")
    ranked_cmds = [ex.command for ex, _ in result.ranked_examples]
    assert ranked_cmds == [ex.command for ex in page.examples]
    assert all(not is_match for _, is_match in result.ranked_examples)


# ── Layer 3 — flag-level detail (real catalog) ────────────────────


def test_l3_flag_note_for_typed_flag(engine):
    result = engine.analyze('git commit -m "wip"')
    assert result.flag_notes
    display, desc = result.flag_notes[0]
    assert "-m" in display or "--message" in display
    assert desc  # a human description, sourced from the page's own example


def test_l3_no_flags_no_notes(engine):
    result = engine.analyze("git commit")
    assert not result.flag_notes


def test_l3_unknown_flag_yields_no_note(engine):
    result = engine.analyze("git commit --definitely-not-a-real-flag")
    assert result.flag_notes == []


def test_l3_notes_are_capped(engine):
    result = engine.analyze("git commit -m -a -S -F --amend")
    assert result.flag_notes is not None
    assert len(result.flag_notes) <= 3


# ── i18n — rank on EN template, display locale description ─────────


def test_i18n_ranks_on_template_shows_locale_description(engine):
    """Ranking uses the language-independent template; display uses the DE text."""
    de = engine.analyze('git commit -m "wip"', locale="de")
    en = engine.analyze('git commit -m "wip"', locale="en")
    assert de.matched_command == "git-commit"
    de_top, de_match = de.ranked_examples[0]
    en_top, _ = en.ranked_examples[0]
    assert de_match is True
    # The flag is language-independent so the same example ranks to the top in
    # both locales; the displayed description is the localized (DE) text.
    # (Locale catalogs translate example *values* too — "message" → "nachricht"
    # — but flags are never translated, so ranking is locale-robust.)
    assert "--message" in de_top.command and "--message" in en_top.command
    assert de_top.description != en_top.description


# ── Deterministic helper rules (no catalog dependency) ────────────


def test_example_signals_parses_alt_flag_notation():
    flags, words = _example_signals('git commit -m|--message "message"')
    assert flags == {"-m", "--message"}
    assert words == {"git", "commit"}  # quoted "message" is an arg, not a word


def test_extract_signals_typed_tokens():
    flags, words = _extract_signals(["-m", "hello", "--amend"])
    assert flags == {"-m", "--amend"}
    assert "hello" in words


def test_extract_signals_strips_flag_value():
    flags, _ = _extract_signals(["--message=hi"])
    assert flags == {"--message"}


@pytest.mark.parametrize(
    "token,expected",
    [
        ("commit", True),
        ("status", True),
        ("-m", False),
        ("path/to/file", False),
        ("message_text", False),
        ("FILE", False),
        ('"message"', False),
    ],
)
def test_is_keyword(token, expected):
    assert _is_keyword(token) is expected


def test_rank_examples_stable_on_ties():
    """Equal scores keep the catalog order (stable sort)."""
    page = TldrPage(
        command="x",
        description="",
        examples=[
            TldrExample(description="a", command="x foo"),
            TldrExample(description="b", command="x bar"),
            TldrExample(description="c", command="x baz"),
        ],
    )
    ranked = _rank_examples(page, set(), set())
    assert [ex.description for ex, _ in ranked] == ["a", "b", "c"]
    assert all(not m for _, m in ranked)


def test_resolve_variant_longest_match_wins():
    catalog = {"git": object(), "git-commit": object()}
    page, key, consumed = _resolve_variant(["git", "commit", "-m"], lambda k: catalog.get(k))
    assert key == "git-commit"
    assert consumed == 2
    assert page is catalog["git-commit"]


def test_resolve_variant_falls_back_to_base():
    catalog = {"git": object()}
    page, key, consumed = _resolve_variant(["git", "whatever"], lambda k: catalog.get(k))
    assert key == "git"
    assert consumed == 1
    assert page is catalog["git"]


def test_resolve_variant_unknown_command_returns_none():
    page, key, consumed = _resolve_variant(["zzznope"], lambda k: None)
    assert page is None
    assert key == "zzznope"


# ── Fallback when a sub-page is absent (isolated mini-catalog) ─────


def test_isolated_fallback_to_base(tmp_path):
    catalog = {"git": {"desc": "VCS.", "examples": []}}
    p = tmp_path / "tldr_catalog.json"
    p.write_text(json.dumps(catalog), encoding="utf-8")
    eng = AdvisoryEngine(tldr_store=TldrStore(catalog_path=p))
    result = eng.analyze("git commit -m x")
    assert result.tldr_page.command == "git"
    assert result.matched_command is None
