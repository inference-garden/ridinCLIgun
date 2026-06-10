# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — tldr corpus integrity verification

"""Verifies the bundled tldr catalogs against data/tldr_manifest.json.

The manifest is written by data/build_tldr_catalog.py (which itself verifies
the upstream release zip against a pinned sha256). This test closes the loop
at package time: any edit to the bundled corpus that is not accompanied by a
regenerated manifest in the same reviewed change fails CI.

If this test fails after an intentional corpus update, regenerate with:
    python data/build_tldr_catalog.py            (full rebuild + manifest)
    python data/build_tldr_catalog.py --manifest-only   (manifest from disk)
"""

import hashlib
import json
import re
from pathlib import Path

import pytest

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_MANIFEST = _DATA_DIR / "tldr_manifest.json"

_CATALOGS = ["tldr_catalog.json", "tldr_catalog_de.json", "tldr_catalog_fr.json"]


@pytest.fixture(scope="module")
def manifest() -> dict:
    assert _MANIFEST.exists(), "tldr_manifest.json missing — run build_tldr_catalog.py"
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


def test_manifest_covers_all_bundled_catalogs(manifest):
    assert set(manifest["files"].keys()) == set(_CATALOGS)


def test_manifest_pins_https_release_and_zip_hash(manifest):
    assert manifest["source"].startswith("https://github.com/tldr-pages/tldr/releases/")
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["source_sha256"])


@pytest.mark.parametrize("filename", _CATALOGS)
def test_bundled_catalog_matches_manifest(manifest, filename):
    """Tamper/drift check: bundled file must hash to the manifest value."""
    path = _DATA_DIR / filename
    assert path.exists(), f"{filename} missing from data/"
    data = path.read_bytes()
    entry = manifest["files"][filename]
    assert len(data) == entry["bytes"], f"{filename}: size drifted from manifest"
    assert hashlib.sha256(data).hexdigest() == entry["sha256"], (
        f"{filename} does not match tldr_manifest.json — if this corpus change "
        "is intentional, regenerate the manifest (see module docstring)"
    )
