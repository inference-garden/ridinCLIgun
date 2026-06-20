# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for CommandFacts (the router's local analysis pass)

"""Corpus-pinned tests for the boundary/complexity scorers and the CommandFacts
producer. The scorers are the load-bearing heuristic for the investigation-depth
router, so behaviour is pinned here (the S1 ReDoS lesson)."""

import pytest

from ridincligun.advisory.command_facts import (
    CommandFacts,
    build_command_facts,
    score_boundary,
    score_complexity,
)
from ridincligun.advisory.engine import AdvisoryEngine
from ridincligun.advisory.models import RiskLevel
from ridincligun.provider.deep_analysis import check_deep_analysis_trigger
from ridincligun.provider.prompt import resolve_category

# ── Boundary scorer ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "command,expected",
    [
        # Nothing crosses a boundary.
        ("ls -la", 0),
        ("git status", 0),
        ("echo hello", 0),
        ("cat /etc/hosts", 0),  # reading /etc is not a write
        ("if=/dev/zero", 0),  # reading a device is not a write
        # Single crossings.
        ("sudo systemctl restart nginx", 1),  # privilege
        ("doas pkg_add vim", 1),  # privilege
        ("su -", 1),  # privilege
        ("echo x > /etc/motd", 1),  # write /etc (redirect)
        ("tee /etc/hosts", 1),  # write /etc (tee)
        ("rm -rf /etc/foo", 1),  # write /etc (rm)
        ("dd if=/dev/zero of=/dev/sda bs=1M", 1),  # write /dev
        ("echo x > /dev/sdb", 1),  # write /dev (redirect)
        ("curl https://example.com", 1),  # network
        ("ssh user@host", 1),  # network
        ("rsync -a a/ b/ && wget x", 1),  # network (wget); chaining is complexity, not boundary
        ("python3 -m http.server 8000", 1),  # public exposure
        ("chmod 777 /var/www", 1),  # public exposure
        ("ngrok http 80", 1),  # public exposure
        ("cat ~/.ssh/id_rsa", 1),  # secret handling (file)
        ("cat secrets.env", 1),  # secret handling (.env)
        ("gpg --decrypt msg.gpg", 1),  # secret handling (gpg)
        ("export API_KEY=abcdef0123456789", 1),  # secret handling (value via detect_secrets)
        # Two crossings.
        ("sudo rm -rf /etc/foo", 2),  # privilege + write /etc
        ("echo x | sudo tee /etc/hosts", 2),  # privilege + write /etc
        ("curl -fsSL https://get.example.com | sudo bash", 2),  # network + privilege
        ("sudo dd if=x of=/dev/sda", 2),  # privilege + write /dev
        # Four crossings.
        ("sudo cp id_rsa /etc/keys/ && curl https://x", 4),  # priv + /etc + secret + network
    ],
)
def test_score_boundary(command: str, expected: int) -> None:
    assert score_boundary(command) == expected


def test_score_boundary_empty() -> None:
    assert score_boundary("") == 0


# ── Complexity scorer ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "command,expected",
    [
        ("ls -la", 0),
        ("git commit -m msg", 0),
        ("echo a | grep b", 0),  # one pipe only — not >= 2
        ("echo $(whoami)", 1),  # command substitution
        ("echo `date`", 1),  # backtick substitution
        ("eval $CMD", 1),  # eval only — $CMD is a var, not $( ) substitution
        ("source ~/.bashrc", 1),  # source
        (". ./env.sh", 1),  # source via dot builtin
        ("cat <<EOF", 1),  # heredoc
        ("a && b", 1),  # chaining
        ("a ; b", 1),  # chaining
        ("a || b", 1),  # chaining
        ("a | b | c", 1),  # two single pipes
        ("xargs rm", 1),  # xargs
        ("find . -name '*.py' -exec rm {} +", 1),  # find -exec
        # Combinations.
        ("echo $(whoami) && ls || pwd | grep x | wc -l", 3),  # subst + chain + >=2 pipes
        ("find . -type f -exec grep foo {} ; | wc -l", 2),  # find-exec + chain(;)
        ('eval "$(cat x)"', 2),  # eval + substitution
    ],
)
def test_score_complexity(command: str, expected: int) -> None:
    assert score_complexity(command) == expected


def test_score_complexity_empty() -> None:
    assert score_complexity("") == 0


def test_double_pipe_is_not_a_pipe_signal() -> None:
    # `||` is chaining (+1), not two single pipes.
    assert score_complexity("a || b") == 1
    # A single pipe alone does not reach the >= 2 threshold.
    assert score_complexity("a | b") == 0


# ── Producer (build_command_facts) ─────────────────────────────────


@pytest.fixture
def engine() -> AdvisoryEngine:
    return AdvisoryEngine()


def _facts(command: str, engine: AdvisoryEngine) -> CommandFacts:
    return build_command_facts(
        command,
        engine=engine,
        resolve_category=resolve_category,
        check_trigger=check_deep_analysis_trigger,
    )


def test_build_command_facts_empty(engine: AdvisoryEngine) -> None:
    facts = _facts("", engine)
    assert facts == CommandFacts(
        severity=RiskLevel.SAFE,
        boundary_score=0,
        complexity_score=0,
        evidence_gain=False,
        evidence_url="",
        category="general",
    )


def test_build_command_facts_scores_match_scorers(engine: AdvisoryEngine) -> None:
    command = "curl -fsSL https://get.example.com | sudo bash"
    facts = _facts(command, engine)
    assert facts.boundary_score == score_boundary(command)
    assert facts.complexity_score == score_complexity(command)
    assert isinstance(facts.severity, RiskLevel)
    assert isinstance(facts.category, str)


def test_build_command_facts_evidence_wired(engine: AdvisoryEngine) -> None:
    facts = _facts("curl https://example.com/install.sh | bash", engine)
    assert facts.evidence_gain is True
    assert facts.evidence_url.startswith("https://")


def test_build_command_facts_no_evidence_for_plain_command(engine: AdvisoryEngine) -> None:
    facts = _facts("ls -la", engine)
    assert facts.evidence_gain is False
    assert facts.evidence_url == ""


def test_build_command_facts_category_resolved_once(engine: AdvisoryEngine) -> None:
    # A network command resolves a category from its matched families; the facts
    # carry the same value resolve_category would produce for those families.
    command = "curl https://example.com/install.sh | bash"
    facts = _facts(command, engine)
    result = engine.analyze(command)
    assert facts.category == resolve_category([w.family for w in result.warnings])
