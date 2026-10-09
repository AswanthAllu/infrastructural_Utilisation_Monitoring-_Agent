from datetime import datetime
from typing import Any, Dict, List, Optional


# ------------------------------------------------------------------
# MVP detection thresholds
# ------------------------------------------------------------------

# Minimum total_slot_ms for a job to be considered a meaningful
# workload contributor.
DEFAULT_MIN_SLOT_MS = 10_000

# Minimum overlap duration between two jobs, in milliseconds.
DEFAULT_MIN_OVERLAP_MS = 1_000

# Minimum number of overlapping significant jobs required to
# consider the current job a slot-contention candidate.
DEFAULT_MIN_OVERLAPPING_JOBS = 1


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------

def _parse_datetime(value: Any) -> Optional[datetime]:
    """
    Convert a BigQuery timestamp value into a datetime.

    BigQuery client responses normally return datetime objects,
    but this also handles ISO-format strings safely.
    """

    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
        except ValueError:
            return None

    return None


def _calculate_duration_ms(
    start_time: Optional[datetime],
    end_time: Optional[datetime],
) -> Optional[float]:
    """Return job duration in milliseconds."""

    if start_time is None or end_time is None:
        return None

    duration_ms = (
        end_time - start_time
    ).total_seconds() * 1000

    if duration_ms <= 0:
        return None

    return duration_ms


def _calculate_overlap_ms(
    start_a: Optional[datetime],
    end_a: Optional[datetime],
    start_b: Optional[datetime],
    end_b: Optional[datetime],
) -> float:
    """
    Calculate the execution-time overlap between two jobs.

    overlap_start = max(start_a, start_b)
    overlap_end   = min(end_a, end_b)

    If overlap_start >= overlap_end, there is no overlap.
    """

    if not all(
        [
            start_a,
            end_a,
            start_b,
            end_b,
        ]
    ):
        return 0.0

    overlap_start = max(start_a, start_b)
    overlap_end = min(end_a, end_b)

    if overlap_start >= overlap_end:
        return 0.0

    return (
        overlap_end - overlap_start
    ).total_seconds() * 1000


def _calculate_average_slot_demand(
    total_slot_ms: Any,
    duration_ms: Optional[float],
) -> Optional[float]:
    """
    Estimate average slot demand.

    average slots ~= total_slot_ms / duration_ms
    """

    if total_slot_ms is None:
        return None

    if duration_ms is None or duration_ms <= 0:
        return None

    try:
        return float(total_slot_ms) / duration_ms
    except (TypeError, ValueError):
        return None


def _get_job_identity(job: Dict[str, Any]) -> str:
    """Return a readable job identifier."""

    return (
        job.get("job_id")
        or "unknown_job"
    )


# ------------------------------------------------------------------
# Main detector
# ------------------------------------------------------------------

def evaluate_slot_contention_candidate(
    job: Dict[str, Any],
    all_jobs: List[Dict[str, Any]],
    min_slot_ms: int = DEFAULT_MIN_SLOT_MS,
    min_overlap_ms: int = DEFAULT_MIN_OVERLAP_MS,
    min_overlapping_jobs: int = DEFAULT_MIN_OVERLAPPING_JOBS,
) -> Dict[str, Any]:
    """
    Evaluate whether a BigQuery job is a potential Slot Contention
    candidate.

    This MVP does NOT prove that BigQuery slot capacity was exhausted.

    It identifies jobs that:
    - have valid execution timestamps,
    - have meaningful slot consumption,
    - overlap with other meaningful query workloads,
    - and therefore may have competed for compute capacity.
    """

    job_id = _get_job_identity(job)

    # --------------------------------------------------------------
    # Parse current job timestamps
    # --------------------------------------------------------------

    start_time = _parse_datetime(
        job.get("start_time")
    )

    end_time = _parse_datetime(
        job.get("end_time")
    )

    if start_time is None or end_time is None:
        return {
            "candidate": False,
            "incident_type": "SLOT_CONTENTION",
            "status": "NOT_EVALUATED",
            "reason": "missing_or_invalid_execution_timestamps",
            "job_id": job_id,
        }

    duration_ms = _calculate_duration_ms(
        start_time,
        end_time,
    )

    if duration_ms is None:
        return {
            "candidate": False,
            "incident_type": "SLOT_CONTENTION",
            "status": "NOT_EVALUATED",
            "reason": "invalid_job_duration",
            "job_id": job_id,
        }

    # --------------------------------------------------------------
    # Check current job slot usage
    # --------------------------------------------------------------

    total_slot_ms = job.get("total_slot_ms")

    try:
        total_slot_ms_value = float(total_slot_ms)
    except (TypeError, ValueError):
        total_slot_ms_value = 0.0

    if total_slot_ms_value < min_slot_ms:
        return {
            "candidate": False,
            "incident_type": "SLOT_CONTENTION",
            "status": "NOT_APPLICABLE",
            "reason": "slot_usage_below_threshold",
            "job_id": job_id,
            "total_slot_ms": total_slot_ms_value,
            "threshold_min_slot_ms": min_slot_ms,
        }

    average_slot_demand = _calculate_average_slot_demand(
        total_slot_ms_value,
        duration_ms,
    )

    # --------------------------------------------------------------
    # Find overlapping significant jobs
    # --------------------------------------------------------------

    overlapping_jobs = []

    for other_job in all_jobs:

        other_job_id = _get_job_identity(other_job)

        # Don't compare the job with itself.
        if other_job_id == job_id:
            continue

        other_start = _parse_datetime(
            other_job.get("start_time")
        )

        other_end = _parse_datetime(
            other_job.get("end_time")
        )

        if other_start is None or other_end is None:
            continue

        other_duration_ms = _calculate_duration_ms(
            other_start,
            other_end,
        )

        if other_duration_ms is None:
            continue

        other_total_slot_ms = other_job.get(
            "total_slot_ms"
        )

        try:
            other_slot_ms_value = float(
                other_total_slot_ms
            )
        except (TypeError, ValueError):
            continue

        # Ignore very small workloads.
        if other_slot_ms_value < min_slot_ms:
            continue

        overlap_ms = _calculate_overlap_ms(
            start_time,
            end_time,
            other_start,
            other_end,
        )

        if overlap_ms < min_overlap_ms:
            continue

        other_average_slot_demand = (
            _calculate_average_slot_demand(
                other_slot_ms_value,
                other_duration_ms,
            )
        )

        overlapping_jobs.append(
            {
                "job_id": other_job_id,
                "start_time": other_start,
                "end_time": other_end,
                "duration_ms": other_duration_ms,
                "total_slot_ms": other_slot_ms_value,
                "average_slot_demand": (
                    other_average_slot_demand
                ),
                "overlap_ms": overlap_ms,
            }
        )

    # --------------------------------------------------------------
    # No significant overlap
    # --------------------------------------------------------------

    if len(overlapping_jobs) < min_overlapping_jobs:
        return {
            "candidate": False,
            "incident_type": "SLOT_CONTENTION",
            "status": "NOT_DETECTED",
            "reason": "no_significant_overlapping_workload",
            "job_id": job_id,
            "total_slot_ms": total_slot_ms_value,
            "duration_ms": duration_ms,
            "average_slot_demand": average_slot_demand,
            "overlapping_job_count": len(
                overlapping_jobs
            ),
        }

    # --------------------------------------------------------------
    # Potential Slot Contention Candidate
    # --------------------------------------------------------------

    total_overlapping_slot_ms = sum(
        overlapping_job["total_slot_ms"]
        for overlapping_job in overlapping_jobs
    )

    combined_slot_demand = (
        total_slot_ms_value
        + total_overlapping_slot_ms
    )

    return {
        "candidate": True,
        "incident_type": "SLOT_CONTENTION",
        "status": "CANDIDATE",
        "reason": "significant_overlapping_slot_workload",
        "job_id": job_id,

        "evidence": {
            "start_time": start_time,
            "end_time": end_time,
            "duration_ms": duration_ms,
            "total_slot_ms": total_slot_ms_value,
            "average_slot_demand": average_slot_demand,

            "overlapping_job_count": len(
                overlapping_jobs
            ),

            "overlapping_jobs": overlapping_jobs,

            "total_overlapping_slot_ms": (
                total_overlapping_slot_ms
            ),

            "combined_slot_demand": (
                combined_slot_demand
            ),

            "thresholds": {
                "min_slot_ms": min_slot_ms,
                "min_overlap_ms": min_overlap_ms,
                "min_overlapping_jobs": (
                    min_overlapping_jobs
                ),
            },
        },
    }