#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# ridinCLIgun — dev-only build script for tldr catalog JSON files
#
# Downloads the official tldr-pages release zip (MIT licensed), filters to
# common + Linux + macOS pages, parses them, and writes plain JSON catalog
# files to the data/ directory.
#
# Run from the repo root:
#   python data/build_tldr_catalog.py
#
# The generated JSON files are committed to the repo so end users never need
# to run this script.  Re-run when you want to update the bundled tldr data
# to a newer release.
#
# Output files (plain JSON, human-readable):
#   data/tldr_catalog.json        — English baseline (~6600 commands)
#   data/tldr_catalog_de.json     — German overlay   (~800 commands)
#   data/tldr_catalog_fr.json     — French overlay   (~800 commands)
#
# Network: downloads from github.com/tldr-pages/tldr (MIT license).
# No data is sent — this is a one-way download of community documentation.

from __future__ import annotations

import io
import json
import urllib.request
import zipfile
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────
# Pinned to a known stable release for reproducibility.
# Update this URL when upgrading.
TLDR_ZIP_URL = "https://github.com/tldr-pages/tldr/releases/download/v2.3/tldr.zip"
PLATFORMS = {"common", "linux", "osx"}  # page platforms to include
MIN_EXAMPLES = 1                         # skip pages with fewer examples

OUT_PATH = Path(__file__).parent / "tldr_catalog.json"

# Additional locale catalogs built alongside the English baseline.
# Keys are tldr directory prefixes, values are output file paths.
LOCALE_CATALOGS: dict[str, Path] = {
    "pages.de": Path(__file__).parent / "tldr_catalog_de.json",
    "pages.fr": Path(__file__).parent / "tldr_catalog_fr.json",
}


# ── Parser ────────────────────────────────────────────────────────

def _strip_placeholders(text: str) -> str:
    """Remove tldr-pages {{ }} placeholder markers and optional [ ] wrappers.

    tldr-pages uses:
        {{value}}          → simple placeholder   → value
        {{[-a|--all]}}     → optional flag         → -a|--all
        {{[.gz|.bz2]}}     → optional extension    → .gz|.bz2
        {{path/to/file}}   → path placeholder      → path/to/file

    The outer [ ] inside {{ }} signals "optional" — we strip those brackets
    so the advisory pane shows clean flag syntax.
    Note: brackets that appear *inside* a longer token (e.g.
    ``source.tar[.gz|.bz2]``) are kept because the whole content doesn't
    start with ``[``.
    """
    result = []
    i = 0
    while i < len(text):
        if text[i:i+2] == "{{":
            end = text.find("}}", i + 2)
            if end != -1:
                inner = text[i+2:end]
                # Strip wrapping [ ] when the entire placeholder content is
                # enclosed: e.g. "[-a|--all]" → "-a|--all"
                if inner.startswith("[") and inner.endswith("]"):
                    inner = inner[1:-1]
                result.append(inner)
                i = end + 2
                continue
        result.append(text[i])
        i += 1
    return "".join(result)


def _parse_page(content: str) -> dict | None:
    """Parse a tldr markdown page into {desc, examples:[{desc,cmd}]}."""
    desc_parts: list[str] = []
    examples: list[dict] = []
    current_desc: str | None = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("# "):
            continue
        if line.startswith("> More information"):
            continue
        if line.startswith(">"):
            text = line[1:].strip()
            if text:
                desc_parts.append(text)
        elif line.startswith("- "):
            current_desc = line[2:].rstrip(":").strip()
        elif line.startswith("`") and line.endswith("`") and len(line) > 2:
            cmd = _strip_placeholders(line[1:-1].strip())
            if current_desc is not None and cmd:
                examples.append({"desc": current_desc, "cmd": cmd})
                current_desc = None

    if not desc_parts or len(examples) < MIN_EXAMPLES:
        return None

    return {
        "desc": desc_parts[0],                  # first sentence only
        "examples": examples,
    }


# ── Main ──────────────────────────────────────────────────────────

def build() -> None:
    print(f"Downloading tldr-pages from:\n  {TLDR_ZIP_URL}", flush=True)
    print("(MIT license — community command documentation)", flush=True)

    with urllib.request.urlopen(TLDR_ZIP_URL, timeout=60) as resp:  # noqa: S310
        zip_bytes = resp.read()

    print(f"Downloaded {len(zip_bytes) / 1024:.0f} KB", flush=True)

    # catalog_by_dir: top-level dir → {command: {desc, examples}}
    catalog_by_dir: dict[str, dict[str, dict]] = {}
    # seen_by_dir: tracks which platform provided each command (linux > osx)
    seen_by_dir: dict[str, dict[str, str]] = {}

    wanted_dirs = {"pages"} | set(LOCALE_CATALOGS.keys())

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        entries = [n for n in zf.namelist() if n.endswith(".md")]
        print(f"Total pages in zip: {len(entries)}", flush=True)

        for name in entries:
            # English:    pages/<platform>/<command>.md
            # Translated: pages.XX/<platform>/<command>.md
            parts = name.split("/")
            if len(parts) < 3:
                continue
            top_dir = parts[0]
            if top_dir not in wanted_dirs:
                continue
            platform = parts[-2]
            if platform not in PLATFORMS:
                continue
            command = parts[-1][:-3]  # strip .md

            # Prefer linux over osx for the same command, within each dir
            seen = seen_by_dir.setdefault(top_dir, {})
            if command in seen and seen[command] == "linux" and platform == "osx":
                continue

            content = zf.read(name).decode("utf-8", errors="replace")
            parsed = _parse_page(content)
            if parsed is not None:
                catalog_by_dir.setdefault(top_dir, {})[command] = parsed
                seen[command] = platform

    def _write_catalog(catalog: dict[str, dict], out_path: Path, label: str) -> None:
        catalog = dict(sorted(catalog.items()))
        # Indented for human readability; use separators to keep it compact
        raw_json = json.dumps(catalog, ensure_ascii=False, indent=1,
                              separators=(",", ": "))
        out_path.write_text(raw_json, encoding="utf-8")
        size_kb = out_path.stat().st_size / 1024
        print(f"Written: {out_path}  ({size_kb:.0f} KB, {len(catalog)} {label} commands)", flush=True)

    en_catalog = catalog_by_dir.get("pages", {})
    print(f"Parsed {len(en_catalog)} English commands ({'+'.join(sorted(PLATFORMS))})", flush=True)
    _write_catalog(en_catalog, OUT_PATH, "EN")

    for top_dir, out_path in LOCALE_CATALOGS.items():
        locale_catalog = catalog_by_dir.get(top_dir, {})
        locale_code = top_dir.replace("pages.", "").upper()
        print(f"Parsed {len(locale_catalog)} {locale_code} commands", flush=True)
        _write_catalog(locale_catalog, out_path, locale_code)


if __name__ == "__main__":
    build()
    print("Done.", flush=True)
