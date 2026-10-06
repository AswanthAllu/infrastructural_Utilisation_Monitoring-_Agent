"""Put the project root on sys.path so `pytest` works as well as `python -m pytest`.

The application uses absolute imports rooted here (`tools.`, `utils.`,
`config.`, `agents.`), which only resolve when this directory is on the
path. `python -m pytest` adds it implicitly; bare `pytest` does not.
"""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))

import pytest  # noqa: E402

from config import join_thresholds  # noqa: E402


@pytest.fixture(autouse=True)
def pinned_scale_profile(monkeypatch):
    """Pin the join thresholds so the suite does not depend on .env.

    JOIN_SCALE_PROFILE is read at import time, so whichever profile a
    developer has configured locally would otherwise change what the
    tests assert. Tests that care about a specific floor override it.
    """

    for name, value in (
        ("SCALE_PROFILE", "production"),
        ("MIN_SIDE_ROWS", 1_000_000),
        ("SHUFFLE_FLOOR_BYTES", 10 * join_thresholds.GIB),
        ("MIN_EXPECTED_RUNS", 2.0),
        ("SLOT_MS_PERCENTILE", 99),
        ("PROFILING_ENABLED", False),
    ):
        monkeypatch.setattr(join_thresholds, name, value)
