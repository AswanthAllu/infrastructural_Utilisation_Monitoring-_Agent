"""The review response must explain why a detector found nothing.

Without the join_review block and the per-detector counts, an empty join
result is indistinguishable from a detector that never ran.
"""

import inspect

from services import agent_service
from tools.bigquery import query_review


def test_review_jobs_returns_join_diagnostics():
    source = inspect.getsource(query_review.review_jobs)

    assert '"join_review"' in source
    assert '"scale_profile"' in source


def test_agent_service_passes_diagnostics_through():
    source = inspect.getsource(agent_service.run_support_agent)

    assert '"join_review"' in source
    assert '"detector_counts"' in source


def test_thresholds_report_the_active_scale_profile():
    from config import join_thresholds

    described = join_thresholds.describe()

    assert described["scale_profile"] in ("production", "sandbox")
    assert "min_side_rows" in described["floors"]


def test_unconstrained_join_is_not_gated_by_the_size_floor():
    """A cartesian product has nothing to hash on, whatever the sizes.

    That verdict must not depend on table size, or a small dataset hides
    the most severe failure mode there is.
    """

    from tools.bigquery.job_stages import analyze_join_stages
    from tools.bigquery.join_detection import detect_high_cardinality_join
    from utils.join_parser import extract_joins

    sql = (
        "SELECT 1 FROM `p.d.transactions` AS t "
        "CROSS JOIN `p.d.loan_applications` AS l"
    )

    result = detect_high_cardinality_join(
        job={"job_id": "j", "total_bytes_processed": 2_000_000},
        joins=extract_joins(sql)["joins"],
        stages=analyze_join_stages(None),
        table_rows={"p.d.transactions": 20_000, "p.d.loan_applications": 20_000},
        expected_future_runs=1.0,
    )

    assert result["detected"] is True
    assert result["failure_mode"] == "UNCONSTRAINED_JOIN"
