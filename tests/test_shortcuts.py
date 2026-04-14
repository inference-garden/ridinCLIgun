# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for keyboard shortcuts

"""Tests for the leader key state machine."""

from ridincligun.shortcuts.bindings import LeaderAction, LeaderState


def test_leader_starts_inactive():
    leader = LeaderState()
    assert not leader.active


def test_leader_activate():
    leader = LeaderState()
    leader.activate()
    assert leader.active


def test_leader_resolve_valid():
    leader = LeaderState()
    leader.activate()
    action = leader.resolve("r")
    assert action == LeaderAction.REVIEW
    assert not leader.active  # deactivates after resolve


def test_leader_resolve_all_keys():
    """All documented leader keys resolve to actions."""
    expected = {
        "r": LeaderAction.REVIEW,
        "a": LeaderAction.TOGGLE_AI,
        "s": LeaderAction.TOGGLE_SECRET,
        "h": LeaderAction.HELP,
        "q": LeaderAction.QUIT,
        "x": LeaderAction.RESTART_SHELL,
        "d": LeaderAction.DEBUG,
        "c": LeaderAction.COPY,
        "v": LeaderAction.PASTE,
        "i": LeaderAction.INSERT_SUGGESTION,
        "k": LeaderAction.HISTORY,
        "?": LeaderAction.CMD_HELP,
        "m": LeaderAction.MODEL_SELECT,
    }
    for key, expected_action in expected.items():
        leader = LeaderState()
        leader.activate()
        action = leader.resolve(key)
        assert action == expected_action, f"Key {key!r} should map to {expected_action}"


def test_leader_resolve_invalid():
    leader = LeaderState()
    leader.activate()
    action = leader.resolve("z")
    assert action is None
    assert not leader.active


def test_leader_resolve_escape():
    leader = LeaderState()
    leader.activate()
    action = leader.resolve("escape")
    assert action is None
    assert not leader.active


def test_leader_resolve_when_inactive():
    """resolve() still returns the action even if not active (caller checks active)."""
    leader = LeaderState()
    # Note: the App checks leader.active before calling resolve,
    # so resolve itself doesn't gate on active state — it just maps keys.
    action = leader.resolve("r")
    assert action == LeaderAction.REVIEW  # maps the key regardless
    assert not leader.active  # but deactivates
