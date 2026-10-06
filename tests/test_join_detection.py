import pytest

from config import join_thresholds as T
from tools.bigquery.job_stages import analyze_join_stages
from tools.bigquery.join_detection import detect_high_cardinality_join
from utils.join_parser import extract_joins


GIB = 1024 ** 3

BIG = {"p.d.left": 50_000_000, "p.d.right": 20_000_000}

EQUI_SQL = "SELECT 1 FROM `p.d.left` l JOIN `p.d.right` r ON l.k = r.k"


def stage(**overrides):
    base = {
        "name": "S02: Join+",
        "slot_ms": 9_000_000,
        "compute_ms_avg": 1_000,
        "compute_ms_max": 1_200,
        "records_read": 10_000_000,
        "records_written": 10_500_000,
        "shuffle_output_bytes": 1 * GIB,
        "shuffle_output_bytes_spilled": 0,
        "parallel_inputs": 400,
        "steps": [{"kind": "JOIN", "substeps": ["INNER HASH JOIN ON k"]}],
    }
    base.update(overrides)

    return base


def scan_stage():
    return {
        "name": "S00: Input",
        "slot_ms": 1_000_000,
        "steps": [{"kind": "READ", "substeps": ["FROM p.d.left"]}],
    }


def analyze(*stages, total_slot_ms=10_000_000):
    return analyze_join_stages(list(stages), total_slot_ms=total_slot_ms)


def detect(sql=EQUI_SQL, job=None, stages=None, **kwargs):
    parsed = extract_joins(sql)

    kwargs.setdefault("table_rows", BIG)
    kwargs.setdefault("expected_future_runs", 30.0)

    return detect_high_cardinality_join(
        job=job or {"job_id": "j1", "total_bytes_processed": 100 * GIB},
        joins=parsed["joins"],
        stages=stages if stages is not None else analyze(stage()),
        **kwargs,
    )


# Suppression and short-circuits.


def test_unnest_only_query_is_not_applicable():
    result = detect(
        sql="SELECT 1 FROM `p.d.left` l CROSS JOIN UNNEST(l.items) AS i"
    )

    assert result["confidence_state"] == "NOT_APPLICABLE"
    assert result["detected"] is False


def test_cross_join_is_confirmed_unconstrained():
    result = detect(sql="SELECT 1 FROM `p.d.left` l CROSS JOIN `p.d.right` r")

    assert result["confidence_state"] == "CONFIRMED"
    assert result["failure_mode"] == "UNCONSTRAINED_JOIN"
    assert result["severity"] == "HIGH"
    assert result["routed"] is True


def test_range_join_is_unconstrained():
    result = detect(
        sql="SELECT 1 FROM `p.d.left` l JOIN `p.d.right` r "
        "ON l.ts BETWEEN r.s AND r.e"
    )

    assert result["failure_mode"] == "UNCONSTRAINED_JOIN"


def test_small_tables_are_pattern_only():
    result = detect(table_rows={"p.d.left": 500, "p.d.right": 200})

    assert result["confidence_state"] == "PATTERN_ONLY"
    assert result["reason"] == "all_sides_below_min_side_rows"


def test_unknown_table_sizes_do_not_suppress():
    result = detect(
        table_rows={"p.d.left": None, "p.d.right": None},
        stages=analyze(stage(compute_ms_avg=1_000, compute_ms_max=19_000)),
    )

    assert result["confidence_state"] == "CONFIRMED"
    assert result["failure_mode"] == "KEY_SKEW"


# Classification from measured stages.


def test_skew_from_compute_ratio():
    result = detect(
        stages=analyze(stage(compute_ms_avg=1_000, compute_ms_max=19_000))
    )

    assert result["failure_mode"] == "KEY_SKEW"
    assert result["confidence_state"] == "CONFIRMED"
    assert result["savings_currency"] == "elapsed_time_and_reliability"


def test_skew_from_spill_even_when_compute_is_balanced():
    """A large share of the shuffle spilling is skew evidence on its own."""

    result = detect(
        stages=analyze(
            stage(
                shuffle_output_bytes=1 * GIB,
                shuffle_output_bytes_spilled=int(0.5 * GIB),
            )
        )
    )

    assert result["failure_mode"] == "KEY_SKEW"
    assert result["severity"] == "HIGH"


def test_trivial_spill_does_not_outrank_a_measured_fanout():
    """Regression: spill was an absolute floor and hijacked classification.

    At the sandbox floor a single spilled byte cleared it, so KEY_SKEW —
    tested first — won over a 2500x fan-out with perfectly balanced
    workers. The ratio test keeps the diagnosis stable across profiles.
    """

    result = detect(
        stages=analyze(
            stage(
                compute_ms_avg=1_000,
                compute_ms_max=1_100,
                records_read=10_000,
                records_written=25_000_000,
                shuffle_output_bytes=500 * 1024 * 1024,
                shuffle_output_bytes_spilled=1,
            )
        )
    )

    assert result["failure_mode"] == "FAN_OUT"


def test_spill_ratio_is_ignored_on_a_trivial_shuffle():
    result = detect(
        stages=analyze(
            stage(
                shuffle_output_bytes=1024,
                shuffle_output_bytes_spilled=1024,
            )
        )
    )

    assert result["failure_mode"] != "KEY_SKEW"


def test_fused_aggregation_is_recorded_on_the_stage():
    """Fan-out is understated when the join stage also aggregates."""

    fused = analyze(
        stage(steps=[{"kind": "JOIN", "substeps": []}, {"kind": "AGGREGATE"}])
    )

    assert fused["fanout_measurable"] is False
    assert fused["aggregate_fused_stages"] == 1

    plain = analyze(stage())

    assert plain["fanout_measurable"] is True
    assert plain["aggregate_fused_stages"] == 0


def test_fanout_from_records_ratio():
    result = detect(
        stages=analyze(
            stage(records_read=1_000_000, records_written=40_000_000)
        )
    )

    assert result["failure_mode"] == "FAN_OUT"
    assert result["savings_currency"] == "slot_ms"
    assert result["recoverable"]["savings_fraction"] == pytest.approx(0.975)


def test_skew_wins_over_fanout_when_both_fire():
    result = detect(
        stages=analyze(
            stage(
                compute_ms_avg=1_000,
                compute_ms_max=19_000,
                records_read=1_000_000,
                records_written=40_000_000,
            )
        )
    )

    assert result["failure_mode"] == "KEY_SKEW"


def test_shuffle_volume_needs_ratio_and_absolute_floor():
    big_shuffle = stage(
        shuffle_output_bytes=max(T.SHUFFLE_FLOOR_BYTES, 300 * GIB)
    )

    result = detect(
        job={"job_id": "j1", "total_bytes_processed": 10 * GIB},
        stages=analyze(big_shuffle),
    )

    assert result["failure_mode"] == "SHUFFLE_VOLUME"


def test_high_shuffle_ratio_below_absolute_floor_is_not_an_incident():
    result = detect(
        job={"job_id": "j1", "total_bytes_processed": 1024},
        stages=analyze(stage(shuffle_output_bytes=1_000_000)),
    )

    assert result["confidence_state"] == "PATTERN_ONLY"


def test_healthy_join_is_pattern_only():
    result = detect()

    assert result["confidence_state"] == "PATTERN_ONLY"
    assert result["reason"] == "no_join_pathology_in_stage_metrics"


def test_scan_dominated_query_routes_away():
    result = detect(
        stages=analyze(
            stage(slot_ms=100_000),
            scan_stage(),
            total_slot_ms=10_000_000,
        )
    )

    assert result["confidence_state"] == "NOT_CONFIRMED"
    assert result["routing_hint"] == "MISSING_PARTITION_FILTER"


# Tier 0 fallback when stages are unavailable.


def test_declared_primary_key_short_circuits_for_free():
    result = detect(
        stages=analyze_join_stages(None),
        pk_columns={("p.d.right", "k")},
    )

    assert result["confidence_state"] == "NOT_CONFIRMED"
    assert result["reason"] == "declared_primary_key_on_every_join_key"


def test_no_stages_and_no_constraint_is_probable():
    result = detect(stages=analyze_join_stages(None))

    assert result["confidence_state"] == "PROBABLE"
    assert result["missing_evidence"] == ["job_stages"]


def test_derived_key_without_stages_is_inconclusive():
    result = detect(
        sql="WITH c AS (SELECT k FROM `p.d.right`) "
        "SELECT 1 FROM `p.d.left` l JOIN c ON l.k = c.k",
        stages=analyze_join_stages(None),
        table_rows={},
    )

    assert result["confidence_state"] == "INCONCLUSIVE"


def test_fanout_against_declared_pk_is_flagged_as_contradiction():
    result = detect(
        stages=analyze(
            stage(records_read=1_000_000, records_written=40_000_000)
        ),
        pk_columns={("p.d.right", "k")},
    )

    assert result["failure_mode"] == "FAN_OUT"
    assert result["constraint_contradicted"] is True


# The recurrence gate.


def test_one_off_query_is_confirmed_but_not_routed():
    result = detect(
        stages=analyze(stage(compute_ms_avg=1_000, compute_ms_max=19_000)),
        expected_future_runs=1.0,
        slot_ms_reference=1_000.0,
    )

    assert result["confidence_state"] == "CONFIRMED"
    assert result["routed"] is False
    assert result["routing_reason"] == "below_min_expected_runs"


def test_recurring_query_is_routed():
    result = detect(
        stages=analyze(stage(compute_ms_avg=1_000, compute_ms_max=19_000)),
        expected_future_runs=720.0,
        slot_ms_reference=6_800_000.0,
    )

    assert result["routed"] is True


def test_cheap_recurring_query_below_reference_is_not_routed():
    result = detect(
        stages=analyze(
            stage(slot_ms=10, compute_ms_avg=1_000, compute_ms_max=19_000),
            total_slot_ms=20,
        ),
        expected_future_runs=30.0,
        slot_ms_reference=6_800_000.0,
    )

    assert result["routed"] is False
    assert result["routing_reason"] == "below_slot_ms_reference"


def test_disabled_percentile_gate_routes_on_recurrence_alone():
    result = detect(
        stages=analyze(stage(compute_ms_avg=1_000, compute_ms_max=19_000)),
        expected_future_runs=30.0,
        slot_ms_reference=None,
    )

    assert result["routed"] is True
    assert result["routing_reason"] == "percentile_gate_disabled"


# Failed jobs are evidence, not noise.


def test_resources_exceeded_raises_severity():
    result = detect(
        job={
            "job_id": "j1",
            "total_bytes_processed": 100 * GIB,
            "error_result": {"reason": "resourcesExceeded", "message": "boom"},
        },
        stages=analyze(
            stage(records_read=1_000_000, records_written=6_000_000)
        ),
    )

    assert result["resources_exceeded"] is True
    assert result["severity"] == "HIGH"


def test_collapsing_key_survives_a_low_dominance_join():
    """A collapsing key is a property of the SQL, not of the plan.

    Statement 6 of the suite reported PROBABLE / FAN_OUT for four runs at
    dominance 0.72-0.81, then vanished at 0.175 — the finding was not
    weaker, it was skipped, because the collapsing check sat below the
    dominance gate. Row multiplication inflates aggregates whatever share
    of the cost the join took.
    """

    from tools.bigquery.join_detection import detect_high_cardinality_join
    from utils.join_parser import extract_joins

    sql = (
        "SELECT 1 FROM `p.d.transactions` AS t "
        "JOIN `p.d.loans` AS l "
        "ON EXTRACT(DAY FROM t.ts) = EXTRACT(DAY FROM l.ts)"
    )

    result = detect_high_cardinality_join(
        job={"job_id": "j"},
        joins=extract_joins(sql)["joins"],
        stages={
            "available": True,
            "join_stage_count": 1,
            "join_dominance": 0.175,
            "fanout_measurable": False,
        },
        # Above the conftest-pinned production floor of 1,000,000.
        table_rows={"p.d.transactions": 2_000_000, "p.d.loans": 2_000_000},
    )

    assert result["failure_mode"] == "FAN_OUT"
    assert result["reason"] == "join_key_expression_collapses_cardinality"
    assert result["join_cost_share_below_gate"] is True
    assert result["join_dominance"] == 0.175


def test_low_dominance_without_a_collapsing_key_still_defers():
    """The gate must keep routing scan-bound queries to the partition check."""

    from tools.bigquery.join_detection import detect_high_cardinality_join
    from utils.join_parser import extract_joins

    sql = (
        "SELECT 1 FROM `p.d.transactions` AS t "
        "JOIN `p.d.loans` AS l ON t.customer_id = l.customer_id"
    )

    result = detect_high_cardinality_join(
        job={"job_id": "j"},
        joins=extract_joins(sql)["joins"],
        stages={
            "available": True,
            "join_stage_count": 1,
            "join_dominance": 0.175,
            "fanout_measurable": False,
        },
        # Above the conftest-pinned production floor of 1,000,000.
        table_rows={"p.d.transactions": 2_000_000, "p.d.loans": 2_000_000},
    )

    assert result["reason"] == "join_stage_does_not_dominate_cost"
    assert result["routing_hint"] == "MISSING_PARTITION_FILTER"


def test_measured_stage_evidence_still_outranks_the_static_key_reading():
    """Only the gate is bypassed. A plan that measures a real pathology
    must still win over an inference from the SQL text."""

    from tools.bigquery.join_detection import detect_high_cardinality_join
    from utils.join_parser import extract_joins

    sql = (
        "SELECT 1 FROM `p.d.transactions` AS t "
        "JOIN `p.d.loans` AS l "
        "ON EXTRACT(DAY FROM t.ts) = EXTRACT(DAY FROM l.ts)"
    )

    result = detect_high_cardinality_join(
        job={"job_id": "j"},
        joins=extract_joins(sql)["joins"],
        stages={
            "available": True,
            "join_stage_count": 1,
            "join_dominance": 0.9,
            "max_skew_ratio": 12.0,
            "fanout_measurable": False,
            "join_slot_ms": 1000,
        },
        # Above the conftest-pinned production floor of 1,000,000.
        table_rows={"p.d.transactions": 2_000_000, "p.d.loans": 2_000_000},
    )

    assert result["failure_mode"] == "KEY_SKEW"
    assert result["reason"] == "classified_from_stage_metrics"
