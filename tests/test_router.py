# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for the investigation-depth router

"""Threshold-boundary tests for the pure router. Synthetic CommandFacts pin every
locked threshold (severity / boundary / complexity edges, evidence on/off, and the
model-vs-fetch separation), decoupled from the scorers (tested separately)."""

import pytest

from ridincligun.advisory.command_facts import CommandFacts
from ridincligun.advisory.models import RiskLevel
from ridincligun.advisory.router import DEEP, FAST, RoutingDecision, route


def facts(
    *,
    severity: RiskLevel = RiskLevel.SAFE,
    boundary: int = 0,
    complexity: int = 0,
    evidence: bool = False,
) -> CommandFacts:
    return CommandFacts(
        severity=severity,
        boundary_score=boundary,
        complexity_score=complexity,
        evidence_gain=evidence,
        evidence_url="https://example.com/x.sh" if evidence else "",
        category="general",
    )


# ── Tier + fetch decision table ────────────────────────────────────


@pytest.mark.parametrize(
    "kwargs,expected_tier,expected_fetch",
    [
        # Trivial → Fast, no fetch.
        (dict(), FAST, False),
        (dict(severity=RiskLevel.CAUTION), FAST, False),  # caution < warning
        (dict(boundary=1), FAST, False),  # below the boundary>=2 deep edge
        (dict(complexity=1), FAST, False),  # complexity 1 alone is not deep-worthy locally
        # Risky / complex LOCAL → Deep model, no fetch (no fetchable evidence).
        (dict(severity=RiskLevel.WARNING), DEEP, False),
        (dict(severity=RiskLevel.DANGER), DEEP, False),
        (dict(boundary=2), DEEP, False),
        (dict(boundary=3), DEEP, False),
        (dict(complexity=2), DEEP, False),
        # Fetchable remote-execute → Deep model + Layer-3 fetch.
        (dict(evidence=True, severity=RiskLevel.WARNING), DEEP, True),
        (dict(evidence=True, boundary=2), DEEP, True),
        (dict(evidence=True, complexity=1), DEEP, True),  # complexity>=1 gates the fetch
        # Evidence present but nothing amplifies → NO fetch, and Fast review.
        (dict(evidence=True), FAST, False),
        (dict(evidence=True, severity=RiskLevel.CAUTION), FAST, False),
        (dict(evidence=True, boundary=1), FAST, False),  # boundary 1 doesn't reach the fetch gate
    ],
)
def test_route_decision_table(kwargs: dict, expected_tier: str, expected_fetch: bool) -> None:
    decision = route(facts(**kwargs))
    assert decision == RoutingDecision(layer2_tier=expected_tier, fetch=expected_fetch)


# ── Locked invariants ──────────────────────────────────────────────


def test_model_and_fetch_are_separate() -> None:
    # A risky/complex LOCAL command (no evidence) gets the Deep model but no fetch.
    d = route(facts(boundary=2, evidence=False))
    assert d.layer2_tier == DEEP
    assert d.fetch is False


def test_fetch_requires_evidence() -> None:
    # Even maximal amplifiers never fetch without fetchable evidence.
    d = route(facts(severity=RiskLevel.DANGER, boundary=3, complexity=5, evidence=False))
    assert d.fetch is False
    assert d.layer2_tier == DEEP


def test_fetch_implies_deep() -> None:
    # Whenever a fetch happens, the Layer-2 tier is Deep.
    for kwargs in (
        dict(evidence=True, severity=RiskLevel.WARNING),
        dict(evidence=True, boundary=2),
        dict(evidence=True, complexity=1),
    ):
        d = route(facts(**kwargs))
        assert d.fetch is True
        assert d.layer2_tier == DEEP


def test_floor_tier_always_fast_or_deep() -> None:
    # The router only chooses depth; it never returns "skip" — the tier is always one
    # of the two real tiers (the Fast floor guarantees a review always happens).
    for sev in RiskLevel:
        for b in range(4):
            for c in range(4):
                for ev in (False, True):
                    tier = route(
                        facts(severity=sev, boundary=b, complexity=c, evidence=ev)
                    ).layer2_tier
                    assert tier in (FAST, DEEP)


def test_caution_does_not_trigger_deep() -> None:
    assert route(facts(severity=RiskLevel.CAUTION)).layer2_tier == FAST


def test_warning_triggers_deep_model_without_fetch() -> None:
    d = route(facts(severity=RiskLevel.WARNING, evidence=False))
    assert d.layer2_tier == DEEP
    assert d.fetch is False
