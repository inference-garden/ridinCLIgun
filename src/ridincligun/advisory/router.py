# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Investigation-depth router

"""The investigation-depth router.

A pure, deterministic decision over :class:`CommandFacts`: it chooses the **Layer-2
review tier** (Fast vs Deep) and whether to **fetch remote evidence** for Layer-3 deep
analysis. No network, no I/O, no provider knowledge — it emits an abstract tier
(``"fast"``/``"deep"``), and the app maps that tier to the chosen provider's model.

Guiding principle (locked design): **danger ≠ investigation value.** A dangerous but
fully-local command (e.g. ``sudo rm -rf /etc/foo``) earns the Deep *model* for a more
careful review, but it does NOT earn a fetch — there is nothing remote to fetch.
``evidence_gain`` (a fetchable remote script) gates the fetch; severity / boundary /
complexity are amplifiers. Model and fetch are therefore decided **separately**.

Floor invariant: the router only decides *depth*. After the user's F2 trigger a Layer-2
review ALWAYS runs (the floor is Fast) — never "no API". The app enforces that; the
router never returns "skip review".

Thresholds are locked (``investigation_depth_router.md``); do not re-litigate. They are
pinned by ``tests/test_router.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ridincligun.advisory.command_facts import CommandFacts
from ridincligun.advisory.models import RiskLevel

# Tier labels — the abstract output of the router (mapped to model ids by the app).
FAST = "fast"
DEEP = "deep"

# Ordered risk ranks for ">= warning" comparisons (one local source of truth here).
_RISK_RANK: dict[RiskLevel, int] = {
    RiskLevel.SAFE: 0,
    RiskLevel.CAUTION: 1,
    RiskLevel.WARNING: 2,
    RiskLevel.DANGER: 3,
}


def _severity_at_least_warning(severity: RiskLevel) -> bool:
    return _RISK_RANK.get(severity, 0) >= _RISK_RANK[RiskLevel.WARNING]


@dataclass(frozen=True)
class RoutingDecision:
    """The router's output: which Layer-2 model tier, and whether to fetch evidence."""

    layer2_tier: str  # FAST | DEEP
    fetch: bool  # True → run Layer-3 deep analysis (on the Deep model)


def route(facts: CommandFacts) -> RoutingDecision:
    """Decide the Layer-2 tier and the fetch flag from local facts. Pure, no I/O.

    Locked thresholds:

    - **Fetch → Layer 3** (runs on the Deep model): ``evidence_gain`` AND
      (``severity ≥ warning`` OR ``boundary ≥ 2`` OR ``complexity ≥ 1``).
    - **Layer-2 tier = Deep**: it fetched, OR ``severity ≥ warning``, OR
      ``boundary ≥ 2``, OR ``complexity ≥ 2``; otherwise **Fast**.
    """
    sev_warn = _severity_at_least_warning(facts.severity)

    fetch = facts.evidence_gain and (
        sev_warn or facts.boundary_score >= 2 or facts.complexity_score >= 1
    )

    deep = fetch or sev_warn or facts.boundary_score >= 2 or facts.complexity_score >= 2

    return RoutingDecision(layer2_tier=DEEP if deep else FAST, fetch=fetch)
