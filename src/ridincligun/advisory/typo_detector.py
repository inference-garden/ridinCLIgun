# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Typo detector for mistyped command names

"""Real-time typo detection for shell commands.

Detects when the first token of a typed command is not a known command
and suggests the closest match using Levenshtein edit distance.

Dictionary sources (merged at construction):
  1. tldr catalog command names  (~2 100 common commands)
  2. command_catalog family IDs  (~17 dangerous-pattern families)
  3. PATH-scanned binaries       (all executables on the current machine)

The dictionary is a ``frozenset[str]`` — O(1) membership test.
The suggestion search is O(dict_size) Levenshtein, ~1 ms for 2 000 words.
"""

from __future__ import annotations

# ── Levenshtein distance ──────────────────────────────────────────

def _levenshtein(a: str, b: str) -> int:
    """Compute the Levenshtein edit distance between two strings."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la

    # Use two rows of the DP matrix to keep memory O(min(la,lb))
    if la < lb:
        a, b, la, lb = b, a, lb, la

    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        curr = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[lb]


# ── Typo detector ─────────────────────────────────────────────────

class TypoDetector:
    """Suggests the closest known command when the typed name is unknown.

    Args:
        dictionary: Full set of known command names.  Build it from
                    ``TldrStore.known_commands()`` + catalog family IDs
                    + PATH-scanned binaries.
        max_distance: Maximum Levenshtein distance to consider a match.
                      Default 2 catches single-swap / adjacent-key typos.
        min_length: Minimum token length before suggesting.  Avoids
                    spurious suggestions while the user is still typing
                    the first characters.
    """

    def __init__(
        self,
        dictionary: frozenset[str],
        *,
        max_distance: int = 2,
        min_length: int = 2,
    ) -> None:
        self._dictionary = dictionary
        self._max_distance = max_distance
        self._min_length = min_length

    def is_known(self, command_name: str) -> bool:
        """Return True if *command_name* is in the dictionary."""
        return command_name.lower() in self._dictionary

    def suggest(self, command_name: str) -> str | None:
        """Return the closest known command, or ``None``.

        Only fires when:
        - ``command_name`` is NOT in the dictionary
        - length ≥ ``min_length``
        - exactly one candidate within ``max_distance`` (returns it),
          OR multiple candidates — returns the one with lowest distance,
          breaking ties by preferring shorter names (more common tools).
        """
        name = command_name.lower().strip()
        if not name or len(name) < self._min_length:
            return None
        if name in self._dictionary:
            return None

        best: str | None = None
        best_dist = self._max_distance + 1

        for known in self._dictionary:
            # Quick length guard: distance ≥ |len(a) - len(b)|
            if abs(len(known) - len(name)) > self._max_distance:
                continue
            d = _levenshtein(name, known)
            if d < best_dist or (d == best_dist and len(known) < len(best or "")):
                best_dist = d
                best = known

        return best if best_dist <= self._max_distance else None

    @property
    def dictionary_size(self) -> int:
        return len(self._dictionary)
