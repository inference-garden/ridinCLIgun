"""Shared test fixtures for ridinCLIgun."""

import sys
from pathlib import Path

# Ensure src is on the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
