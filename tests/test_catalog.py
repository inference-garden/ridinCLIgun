"""Tests for the command catalog loader."""

import json
from pathlib import Path

import pytest

from ridincligun.advisory.catalog import load_catalog


@pytest.fixture
def catalog():
    return load_catalog()


def test_catalog_loads(catalog):
    """Catalog loads without errors and has patterns."""
    assert len(catalog.patterns) > 0


def test_catalog_has_expected_families(catalog):
    """Catalog has patterns from core command families."""
    family_ids = {p.family_id for p in catalog.patterns}
    expected = {"rm", "curl_pipe", "dd", "chmod", "git_destructive"}
    assert expected.issubset(family_ids), f"Missing families: {expected - family_ids}"


def test_catalog_json_valid():
    """The catalog JSON file is valid and well-structured."""
    catalog_path = Path(__file__).parent.parent / "data" / "command_catalog.json"
    assert catalog_path.exists(), f"Catalog not found at {catalog_path}"

    with open(catalog_path) as f:
        data = json.load(f)

    assert "families" in data
    for family in data["families"]:
        assert "name" in family
        assert "patterns" in family
        assert len(family["patterns"]) > 0
        for pattern in family["patterns"]:
            assert "regex" in pattern
            assert "risk" in pattern
            assert pattern["risk"] in ("safe", "caution", "warning", "danger")
            assert "summary" in pattern


def test_catalog_patterns_are_valid_regex(catalog):
    """All patterns in the loaded catalog compiled successfully."""
    for pattern in catalog.patterns:
        assert pattern.regex is not None
        assert pattern.summary
