from typing import Any, Dict

from .candidate_detector import (
    evaluate_missing_partition_filter_candidate,
)
from .jobs_metadata import get_recent_query_jobs
from .join_review import review_jobs_for_joins
from .slot_contention_detector import (
    evaluate_slot_contention_candidate,
)


def review_jobs(
    region: str = "US",
    lookback_hours: int = 24,
    jobs_limit: int = 5,
    project: str | None = None,
) -> Dict[str, Any]:
    """
    Review recent completed BigQuery query jobs for supported
    performance issues.

    Detectors currently included:
    - Missing Partition Filter
    - Slot Contention
    - High Cardinality Join

    A job can qualify for more than one detector. Each is reported on its
    own list rather than one suppressing the others: a wide scan feeding a
    skewed join is a common compound case.
    """

    jobs_response = get_recent_query_jobs(
        region=region,
        lookback_hours=lookback_hours,
        limit=jobs_limit,
        project=project,
    )

    if not jobs_response.get("success"):
        return {
            "success": False,
            "region": region,
            "lookback_hours": lookback_hours,
            "jobs_checked": 0,
            "missing_partition_filter_candidate_count": 0,
            "slot_contention_candidate_count": 0,
            "high_cardinality_join_candidate_count": 0,
            "missing_partition_filter_candidates": [],
            "slot_contention_candidates": [],
            "high_cardinality_join_candidates": [],
            "message": jobs_response.get("message"),
        }

    completed_jobs = [
        job
        for job in jobs_response.get("jobs", [])
        if job.get("state") == "DONE"
    ]

    missing_partition_filter_candidates = []
    slot_contention_candidates = []

    for job in completed_jobs:

        # ---------------------------------------------------------
        # Detector 1: Missing Partition Filter
        # ---------------------------------------------------------
        partition_analysis = (
            evaluate_missing_partition_filter_candidate(job)
            or {}
        )

        if partition_analysis.get("candidate") is True:
            missing_partition_filter_candidates.append(
                {
                    "job": job,
                    "analysis": partition_analysis,
                }
            )

        # ---------------------------------------------------------
        # Detector 2: Slot Contention
        # ---------------------------------------------------------
        slot_analysis = (
            evaluate_slot_contention_candidate(
                job=job,
                all_jobs=completed_jobs,
            )
            or {}
        )

        if slot_analysis.get("candidate") is True:
            slot_contention_candidates.append(
                {
                    "job": job,
                    "analysis": slot_analysis,
                }
            )

    # ---------------------------------------------------------
    # Detector 3: High Cardinality Join
    #
    # Evaluated over the whole job set rather than per job, so that the
    # execution-plan, recurrence and table-metadata lookups are one
    # round trip each instead of one per job.
    # ---------------------------------------------------------
    join_review = review_jobs_for_joins(
        completed_jobs,
        region=region,
        lookback_hours=max(lookback_hours, 1),
        project=project,
    )

    high_cardinality_join_candidates = join_review.get("candidates", [])

    return {
        "success": True,
        "region": region,
        "lookback_hours": lookback_hours,
        "jobs_checked": len(completed_jobs),

        "missing_partition_filter_candidate_count": len(
            missing_partition_filter_candidates
        ),
        "missing_partition_filter_candidates": (
            missing_partition_filter_candidates
        ),

        "slot_contention_candidate_count": len(
            slot_contention_candidates
        ),
        "slot_contention_candidates": (
            slot_contention_candidates
        ),

        "high_cardinality_join_candidate_count": len(
            high_cardinality_join_candidates
        ),
        "high_cardinality_join_candidates": (
            high_cardinality_join_candidates
        ),

        "join_review": {
            "jobs_with_joins": join_review.get("jobs_with_joins", 0),
            "routed_count": join_review.get("routed_count", 0),
            "scale_profile": join_review.get("scale_profile"),
            "evaluated": join_review.get("evaluated", []),
            "stages_error": join_review.get("stages_error"),
            "profiling": join_review.get("profiling"),
        },
    }
