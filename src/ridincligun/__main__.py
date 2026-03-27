# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Entry point

"""Entry point for `python -m ridincligun`."""

from ridincligun.app import RidinCLIgunApp


def main() -> None:
    app = RidinCLIgunApp()
    app.run()


if __name__ == "__main__":
    main()
