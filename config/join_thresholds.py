"""HIGH_CARDINALITY_JOIN thresholds. See high-cardinality-join-design.md §10.

Ratios are scale-free. Floors are not, and a small dataset clears none of
them, so JOIN_SCALE_PROFILE=sandbox in .env relaxes the floors for testing.
"""

import os

from dotenv import load_dotenv


load_dotenv()


MIB = 1024 ** 2
GIB = 1024 ** 3


JOIN_DOMINANCE = 0.40
SKEW_COMPUTE_RATIO = 4.0
FANOUT_RATIO_WARN = 5.0
SHUFFLE_AMPLIFICATION = 2.0
INTERVAL_COV_SCHEDULED = 0.15

# Spill is meaningful relative to the shuffle that produced it, so it is a
# ratio and not a per-profile floor. As an absolute floor it silently
# changed which failure mode was diagnosed rather than only gating
# materiality: one spilled byte was enough to make KEY_SKEW win over an
# otherwise obvious FAN_OUT.
SPILL_RATIO_WARN = 0.10
SPILL_MIN_SHUFFLE_BYTES = 1 * MIB

# Estimated matches per probe row, from key cardinality rather than from
# the execution plan. BigQuery fuses aggregation into the join stage, so
# records_written is the post-GROUP BY count and the measured fan-out
# ratio understates the join's real output. NDV is the only way to
# recover it.
MATCHES_PER_ROW_WARN = 10.0

HISTORY_DAYS = 30
RECURRENCE_HORIZON_DAYS = 30
UNKNOWN_HASH_EXPECTED_RUNS = 1.0


_PROFILES = {
    "production": {
        "min_side_rows": 1_000_000,
        "shuffle_floor_bytes": 10 * GIB,
        "min_expected_runs": 2.0,
        "slot_ms_percentile": 99,
    },
    "sandbox": {
        "min_side_rows": 1_000,
        "shuffle_floor_bytes": 1 * MIB,
        "min_expected_runs": 1.0,
        "slot_ms_percentile": None,
    },
}


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)

    if raw is None:
        return default

    return raw.strip().lower() in ("1", "true", "yes", "on")


# Tier 2 profiling reads the join key columns to recover fan-out. It is
# the only part of the check that spends money, so it stays off until
# switched on deliberately.
PROFILING_ENABLED = _bool_env("JOIN_PROFILING_ENABLED", False)
PROFILE_MAX_BYTES = 5 * GIB


SCALE_PROFILE = os.getenv("JOIN_SCALE_PROFILE", "production").strip().lower()

if SCALE_PROFILE not in _PROFILES:
    SCALE_PROFILE = "production"

_floors = _PROFILES[SCALE_PROFILE]

MIN_SIDE_ROWS = _floors["min_side_rows"]
SHUFFLE_FLOOR_BYTES = _floors["shuffle_floor_bytes"]
MIN_EXPECTED_RUNS = _floors["min_expected_runs"]
SLOT_MS_PERCENTILE = _floors["slot_ms_percentile"]


def describe() -> dict:
    return {
        "scale_profile": SCALE_PROFILE,
        "floors": dict(_floors),
        "ratios": {
            "join_dominance": JOIN_DOMINANCE,
            "skew_compute_ratio": SKEW_COMPUTE_RATIO,
            "fanout_ratio_warn": FANOUT_RATIO_WARN,
            "shuffle_amplification": SHUFFLE_AMPLIFICATION,
            "spill_ratio_warn": SPILL_RATIO_WARN,
        },
    }
