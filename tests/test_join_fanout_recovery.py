"""Behaviour for joins whose fan-out the execution plan cannot measure.

BigQuery fuses aggregation into the join stage, so records_written is the
post-GROUP BY count and the measured fan-out ratio understates the join's
real output. Every join stage observed in the sandbox workload was fused,
so this path is the normal case rather than an edge case.
"""

import pytest

from config import join_thresholds as T
from tools.bigquery.job_stages import analyze_join_stages
from tools.bigquery.join_detection import (
    detect_high_cardinality_join,
    estimate_matches_per_row,
    profile_targets,
)
from utils.join_parser import extract_joins


GIB = 1024 ** 3

SQL = "SELECT 1 FROM `p.d.tx` a JOIN `p.d.loans` b ON a.fraud_flag = b.fraud_flag"

BIG = {"p.d.tx": 50_000_000, "p.d.loans": 50_000_000}


def fused_stage(**overrides):
    """A join stage that also aggregates, so fan-out is not measurable."""

    base = {
        "name": "S01: Join+",
        "slot_ms": 390_000,
        "compute_ms_avg": 1_000,
        "compute_ms_max": 1_100,
        "records_read": 10_000,
        "records_written": 12_000,
        "shuffle_output_bytes": 500 * 1024 * 1024,
        "shuffle_output_bytes_spilled": 0,
        "steps": [{"kind": "JOIN", "substeps": []}, {"kind": "AGGREGATE"}],
    }
    base.update(overrides)

    return base


def detect(key_stats=None, pk_columns=None, sql=SQL, job=None, stage=None):
    return detect_high_cardinality_join(
        job=job or {"job_id": "j", "total_bytes_processed": 2_000_000},
        joins=extract_joins(sql)["joins"],
        stages=analyze_join_stages([stage or fused_stage()], total_slot_ms=400_000),
        table_rows=BIG,
        pk_columns=pk_columns,
        key_stats=key_stats,
        expected_future_runs=30.0,
    )


# Without cardinality, the verdict must not claim the join is fine.


def test_unmeasurable_fanout_is_inconclusive_not_pattern_only():
    result = detect()

    assert result["confidence_state"] == "INCONCLUSIVE"
    assert result["reason"] == "fanout_unmeasurable_aggregate_fused"
    assert result["missing_evidence"] == ["join_key_cardinality"]
    assert result["detected"] is False


def test_measurable_fanout_still_reports_pattern_only():
    unfused = fused_stage(steps=[{"kind": "JOIN", "substeps": []}])

    result = detect(stage=unfused)

    assert result["confidence_state"] == "PATTERN_ONLY"
    assert result["reason"] == "no_join_pathology_in_stage_metrics"


# A declared primary key settles it without profiling.


def test_declared_primary_key_bounds_fanout_without_profiling():
    result = detect(pk_columns={("p.d.loans", "fraud_flag")})

    assert result["confidence_state"] == "NOT_CONFIRMED"
    assert result["reason"] == "declared_primary_key_bounds_fanout"


# Cardinality recovers the verdict the plan could not give.


def test_low_cardinality_key_is_recovered_as_fanout():
    stats = {
        ("p.d.tx", "fraud_flag"): {"row_count": 20_000, "ndv": 2},
        ("p.d.loans", "fraud_flag"): {"row_count": 20_000, "ndv": 2},
    }

    result = detect(key_stats=stats)

    assert result["failure_mode"] == "FAN_OUT"
    assert result["confidence_state"] == "PROBABLE"
    assert result["evidence_tier"] == 2
    assert result["estimated_matches_per_row"] == pytest.approx(10_000)


def test_estimate_is_capped_at_probable_never_confirmed():
    """An estimate from uniformity assumptions is not a measurement."""

    stats = {
        ("p.d.tx", "fraud_flag"): {"row_count": 1_000_000, "ndv": 2},
        ("p.d.loans", "fraud_flag"): {"row_count": 1_000_000, "ndv": 2},
    }

    result = detect(key_stats=stats)

    assert result["confidence_state"] != "CONFIRMED"


def test_unique_key_is_ruled_out_rather_than_left_open():
    stats = {
        ("p.d.tx", "fraud_flag"): {"row_count": 20_000, "ndv": 20_000},
        ("p.d.loans", "fraud_flag"): {"row_count": 20_000, "ndv": 20_000},
    }

    result = detect(key_stats=stats)

    assert result["confidence_state"] == "NOT_CONFIRMED"
    assert result["reason"] == "estimated_fanout_below_threshold"


def test_ruling_out_by_ndv_is_reported_as_tier_2():
    """Ruling a join out costs the same profiling as confirming it.

    The estimate only exists when both sides were profiled, so reporting
    tier 1 here would make a paid verdict look like a free one.
    """

    stats = {
        ("p.d.tx", "fraud_flag"): {"row_count": 20_000, "ndv": 20_000},
        ("p.d.loans", "fraud_flag"): {"row_count": 20_000, "ndv": 20_000},
    }

    assert detect(key_stats=stats)["evidence_tier"] == 2


def test_dimension_lookup_is_benign_however_skewed_the_fact_side():
    """One unique side caps the output, so this must not be a fan-out.

    The fact side has 1000 rows per key; a naive estimate using only the
    larger table would call this a 1000x fan-out.
    """

    stats = {
        ("p.d.tx", "fraud_flag"): {"row_count": 1_000_000, "ndv": 1_000},
        ("p.d.loans", "fraud_flag"): {"row_count": 1_000, "ndv": 1_000},
    }

    result = detect(key_stats=stats)

    assert result["confidence_state"] == "NOT_CONFIRMED"


def test_partial_stats_do_not_produce_an_estimate():
    stats = {("p.d.tx", "fraud_flag"): {"row_count": 20_000, "ndv": 2}}

    result = detect(key_stats=stats)

    assert result["confidence_state"] == "INCONCLUSIVE"


# Helpers.


def test_estimate_uses_the_smaller_duplication_factor():
    joins = extract_joins(SQL)["joins"]

    estimate = estimate_matches_per_row(
        joins,
        {
            ("p.d.tx", "fraud_flag"): {"row_count": 1_000_000, "ndv": 10},
            ("p.d.loans", "fraud_flag"): {"row_count": 100, "ndv": 50},
        },
    )

    assert estimate["matches_per_row"] == pytest.approx(2.0)


def test_profile_targets_lists_both_sides_of_every_key():
    targets = profile_targets(extract_joins(SQL)["analyzable_joins"])

    assert set(targets) == {
        ("p.d.tx", "fraud_flag"),
        ("p.d.loans", "fraud_flag"),
    }


def test_profile_targets_skips_cte_sources():
    """A CTE alias cannot be selected from, so profiling it wastes a dry run."""

    sql = (
        "WITH inflated AS (SELECT transaction_id, n FROM `p.d.tx`, "
        "UNNEST(GENERATE_ARRAY(1, 60)) AS n) "
        "SELECT 1 FROM inflated AS a JOIN inflated AS b "
        "ON a.transaction_id = b.transaction_id"
    )

    targets = profile_targets(extract_joins(sql)["analyzable_joins"])

    assert targets == []


def test_profile_targets_keeps_the_table_side_of_a_mixed_join():
    sql = (
        "WITH c AS (SELECT k FROM `p.d.loans`) "
        "SELECT 1 FROM `p.d.tx` AS t JOIN c ON t.fraud_flag = c.k"
    )

    targets = profile_targets(extract_joins(sql)["analyzable_joins"])

    assert targets == [("p.d.tx", "fraud_flag")]


# Cache hits have no plan to fetch.


def test_cache_hit_is_reported_distinctly_from_a_failed_lookup():
    result = detect_high_cardinality_join(
        job={"job_id": "j", "cache_hit": True, "total_bytes_processed": 0},
        joins=extract_joins(SQL)["joins"],
        stages=analyze_join_stages(None),
        table_rows=BIG,
        expected_future_runs=30.0,
    )

    assert result["confidence_state"] == "INCONCLUSIVE"
    assert result["reason"] == "cache_hit_no_execution_plan"
    assert result["cache_hit"] is True


def test_uncached_missing_stages_remain_probable():
    result = detect_high_cardinality_join(
        job={"job_id": "j", "cache_hit": False, "total_bytes_processed": 100},
        joins=extract_joins(SQL)["joins"],
        stages=analyze_join_stages(None),
        table_rows=BIG,
        expected_future_runs=30.0,
    )

    assert result["confidence_state"] == "PROBABLE"


def test_profiling_refuses_when_disabled(monkeypatch):
    """The only part of the check that bills must not run unasked."""

    from tools.bigquery import column_profile

    monkeypatch.setattr(T, "PROFILING_ENABLED", False)

    result = column_profile.profile_columns([("p.d.tx", "fraud_flag")])

    assert result["key_stats"] == {}
    assert result["skipped_reason"] == "profiling_disabled"
