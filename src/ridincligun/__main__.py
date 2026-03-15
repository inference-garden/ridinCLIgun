"""Entry point for `python -m ridincligun`."""

from ridincligun.app import RidinCLIgunApp


def main() -> None:
    app = RidinCLIgunApp()
    app.run()


if __name__ == "__main__":
    main()
