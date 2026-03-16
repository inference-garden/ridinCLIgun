"""Local advisory engine.

Matches commands against the catalog. Synchronous, no network, no side effects.
Returns a ReviewResult with all matched warnings.
"""

from __future__ import annotations

from ridincligun.advisory.catalog import CommandCatalog, load_catalog
from ridincligun.advisory.models import ReviewResult, Warning


class AdvisoryEngine:
    """Stateless local command analyzer. Matches input against the catalog."""

    def __init__(self, catalog: CommandCatalog | None = None) -> None:
        self._catalog = catalog or load_catalog()

    def analyze(self, command: str) -> ReviewResult:
        """Analyze a command string and return all matched warnings.

        Returns a ReviewResult with warnings sorted by severity (highest first).
        Empty/whitespace commands return a safe result with no warnings.
        """
        command = command.strip()
        if not command:
            return ReviewResult(command=command)

        warnings: list[Warning] = []
        seen_families: set[str] = set()

        for pattern in self._catalog.patterns:
            if pattern.regex.search(command):
                # Only keep the highest-severity match per family
                if pattern.family_id in seen_families:
                    continue
                seen_families.add(pattern.family_id)

                warnings.append(
                    Warning(
                        risk=pattern.risk,
                        summary=pattern.summary,
                        suggestion=pattern.suggestion,
                        family=pattern.family_id,
                        pattern_source=pattern.regex.pattern,
                    )
                )

        # Sort: danger first, then warning, then caution
        risk_order = {"danger": 0, "warning": 1, "caution": 2, "safe": 3}
        warnings.sort(key=lambda w: risk_order.get(w.risk.value, 99))

        return ReviewResult(command=command, warnings=warnings)
