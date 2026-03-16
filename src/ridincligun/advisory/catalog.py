"""Command catalog loader.

Loads the JSON catalog from disk and provides compiled regex patterns.
Stateless — loads once, immutable after that.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from ridincligun.advisory.models import RiskLevel


@dataclass(frozen=True)
class CatalogPattern:
    """A single compiled pattern from the catalog."""

    family_id: str
    family_name: str
    regex: re.Pattern[str]
    risk: RiskLevel
    summary: str
    suggestion: str


@dataclass
class CommandCatalog:
    """The loaded command catalog with compiled patterns."""

    version: str
    patterns: list[CatalogPattern] = field(default_factory=list)


def load_catalog(path: Path | None = None) -> CommandCatalog:
    """Load the command catalog from JSON.

    If no path is given, loads the bundled default catalog.
    Patterns are compiled once at load time.
    """
    if path is None:
        # Load from the data directory relative to the project
        # Try the installed package data first, then fall back to repo layout
        try:
            data_ref = resources.files("ridincligun") / "data" / "command_catalog.json"
            raw = data_ref.read_text(encoding="utf-8")
        except (FileNotFoundError, TypeError):
            # Fall back to repo-relative path
            repo_path = Path(__file__).resolve().parents[3] / "data" / "command_catalog.json"
            raw = repo_path.read_text(encoding="utf-8")
    else:
        raw = path.read_text(encoding="utf-8")

    data = json.loads(raw)
    catalog = CommandCatalog(version=data.get("version", "unknown"))

    for family in data.get("families", []):
        family_id = family["id"]
        family_name = family["name"]
        for pattern in family.get("patterns", []):
            try:
                compiled = re.compile(pattern["regex"])
                risk = RiskLevel(pattern["risk"])
                catalog.patterns.append(
                    CatalogPattern(
                        family_id=family_id,
                        family_name=family_name,
                        regex=compiled,
                        risk=risk,
                        summary=pattern["summary"],
                        suggestion=pattern["suggestion"],
                    )
                )
            except (re.error, ValueError):
                # Skip malformed patterns silently
                pass

    return catalog
