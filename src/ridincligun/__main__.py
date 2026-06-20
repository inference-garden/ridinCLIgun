# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Entry point

"""Entry point for `python -m ridincligun`."""

import argparse
import sys

from ridincligun import __version__
from ridincligun.app import RidinCLIgunApp
from ridincligun.config import ConfigError


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ridincligun",
        description="A terminal companion that advises but never acts.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"ridincligun {__version__}",
    )
    # Bare launch parses to an empty namespace and falls through to the TUI;
    # --version / --help print to stdout and exit before the app is built.
    parser.parse_args()

    try:
        app = RidinCLIgunApp()
    except ConfigError as e:
        # A broken config.toml should fail with one clear line, not a raw traceback.
        print(f"ridincligun: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    app.run()


if __name__ == "__main__":
    main()
