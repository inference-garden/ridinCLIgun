"""Shared test fixtures for ridinCLIgun."""

import sys
from pathlib import Path

import pytest

# Ensure src is on the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(autouse=True)
def _force_english_locale():
    """Ensure all tests run with English locale regardless of system config."""
    from ridincligun.i18n import get_locale, reload_locale, set_locale

    original = get_locale()
    set_locale("en")
    reload_locale()
    yield
    set_locale(original)
    reload_locale()
