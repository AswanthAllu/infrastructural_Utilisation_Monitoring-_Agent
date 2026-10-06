"""Equality between expressions is a join key, not a missing predicate.

`UPPER(a.k) = UPPER(b.k)` is an ordinary equi-join: BigQuery evaluates
both sides and hash joins on the result. Treating it as ABSENT reported
two sandbox queries as cartesian products when neither was one.

What distinguishes a harmless computed key from a harmful one is whether
the expression collapses cardinality. EXTRACT(DAY FROM ts) has at most 31
values however unique the column was.
"""

import pytest

from tools.bigquery.job_stages import analyze_join_stages
from tools.bigquery.join_detection import detect_high_cardinality_join
from utils.join_parser import extract_joins


# Clears the pinned production size floor, so verdicts reflect
# classification rather than suppression.
BOTH = {"p.d.t": 50_000_000, "p.d.l": 50_000_000}


def join(sql):
    return extract_joins(sql)["joins"][0]


def verdict(sql, stages=None, job_overrides=None, **kwargs):
    kwargs.setdefault("table_rows", BOTH)

    job = {"job_id": "j", "total_bytes_processed": 2_000_000}
    job.update(job_overrides or {})

    return detect_high_cardinality_join(
        job=job,
        joins=extract_joins(sql)["joins"],
        stages=stages if stages is not None else analyze_join_stages(None),
        **kwargs,
    )


# Classification.


@pytest.mark.parametrize(
    "predicate,kind,collapsing",
    [
        ("t.k = l.k", "EQUI", False),
        ("UPPER(t.k) = UPPER(l.k)", "EQUI_COMPUTED", False),
        ("TRIM(t.k) = TRIM(l.k)", "EQUI_COMPUTED", False),
        ("CAST(t.k AS STRING) = CAST(l.k AS STRING)", "EQUI_COMPUTED", False),
        ("COALESCE(t.k, '') = COALESCE(l.k, '')", "EQUI_COMPUTED", False),
        ("EXTRACT(DAY FROM t.d) = EXTRACT(DAY FROM l.d)", "EQUI_COMPUTED", True),
        ("DATE_TRUNC(t.d, MONTH) = DATE_TRUNC(l.d, MONTH)", "EQUI_COMPUTED", True),
        ("MOD(t.n, 10) = MOD(l.n, 10)", "EQUI_COMPUTED", True),
        ("SUBSTR(t.k, 1, 3) = SUBSTR(l.k, 1, 3)", "EQUI_COMPUTED", True),
        ("ROUND(t.n) = ROUND(l.n)", "EQUI_COMPUTED", True),
    ],
)
def test_predicate_classification(predicate, kind, collapsing):
    parsed = join(f"SELECT 1 FROM `p.d.t` t JOIN `p.d.l` l ON {predicate}")

    assert parsed["predicate_kind"] == kind
    assert parsed["cardinality_collapsing"] is collapsing


def test_only_a_missing_or_range_predicate_is_unconstrained():
    assert join("SELECT 1 FROM `p.d.t` t CROSS JOIN `p.d.l` l")[
        "predicate_kind"
    ] == "ABSENT"

    assert join(
        "SELECT 1 FROM `p.d.t` t JOIN `p.d.l` l ON t.ts BETWEEN l.s AND l.e"
    )["predicate_kind"] == "RANGE"


def test_one_bare_key_pair_keeps_the_join_plain_equi():
    """A mixed predicate still hashes on the bare pair."""

    parsed = join(
        "SELECT 1 FROM `p.d.t` t JOIN `p.d.l` l "
        "ON t.k = l.k AND UPPER(t.x) = UPPER(l.x)"
    )

    assert parsed["predicate_kind"] == "EQUI"
    assert parsed["resolved"] is True


def test_computed_keys_are_not_profilable():
    """NDV of the base column does not describe the expression's key."""

    parsed = join(
        "SELECT 1 FROM `p.d.t` t JOIN `p.d.l` l "
        "ON EXTRACT(DAY FROM t.d) = EXTRACT(DAY FROM l.d)"
    )

    assert parsed["resolved"] is False


# Verdicts.


def test_preserving_functions_are_not_an_incident_on_their_own():
    result = verdict(
        "SELECT 1 FROM `p.d.t` t JOIN `p.d.l` l "
        "ON CAST(UPPER(TRIM(t.k)) AS STRING) = CAST(UPPER(TRIM(l.k)) AS STRING)"
    )

    assert result["failure_mode"] != "UNCONSTRAINED_JOIN"
    assert result["confidence_state"] in ("INCONCLUSIVE", "PROBABLE")


def test_collapsing_key_is_a_fanout_finding_without_any_plan():
    """The only fan-out route that survives a cache hit."""

    result = verdict(
        "SELECT 1 FROM `p.d.t` t JOIN `p.d.l` l "
        "ON EXTRACT(DAY FROM t.d) = EXTRACT(DAY FROM l.d)"
    )

    assert result["failure_mode"] == "FAN_OUT"
    assert result["confidence_state"] == "PROBABLE"
    assert result["reason"] == "join_key_expression_collapses_cardinality"
    assert result["routing_reason"] == "static_sql_evidence"


def test_collapsing_key_survives_a_cache_hit():
    """The static signal must outrank the no-plan short-circuit.

    A cached job has no execution plan, but the key expression is still
    visible in the SQL, so the finding still stands.
    """

    result = verdict(
        "SELECT 1 FROM `p.d.t` t JOIN `p.d.l` l "
        "ON EXTRACT(DAY FROM t.d) = EXTRACT(DAY FROM l.d)",
        job_overrides={"cache_hit": True},
    )

    assert result["failure_mode"] == "FAN_OUT"
    assert result["reason"] == "join_key_expression_collapses_cardinality"
    assert result["cache_hit"] is True


def test_cache_hit_without_a_collapsing_key_stays_inconclusive():
    result = verdict(
        "SELECT 1 FROM `p.d.t` t JOIN `p.d.l` l "
        "ON UPPER(t.k) = UPPER(l.k)",
        job_overrides={"cache_hit": True},
    )

    assert result["reason"] == "cache_hit_no_execution_plan"


def test_declared_pk_does_not_bound_a_computed_key():
    """A unique column stays unique; an expression over it does not."""

    result = verdict(
        "SELECT 1 FROM `p.d.t` t JOIN `p.d.l` l "
        "ON EXTRACT(DAY FROM t.d) = EXTRACT(DAY FROM l.d)",
        pk_columns={("p.d.t", "d"), ("p.d.l", "d")},
    )

    assert result["failure_mode"] == "FAN_OUT"


def test_declared_pk_still_bounds_a_bare_key():
    result = verdict(
        "SELECT 1 FROM `p.d.t` t JOIN `p.d.l` l ON t.k = l.k",
        pk_columns={("p.d.l", "k")},
    )

    assert result["confidence_state"] == "NOT_CONFIRMED"


def test_cartesian_product_is_still_unconstrained_and_high():
    result = verdict("SELECT 1 FROM `p.d.t` t CROSS JOIN `p.d.l` l")

    assert result["failure_mode"] == "UNCONSTRAINED_JOIN"
    assert result["severity"] == "HIGH"


def test_measured_stages_still_outrank_the_static_signal():
    """A real plan beats an inference drawn from the SQL text."""

    skewed = analyze_join_stages(
        [
            {
                "name": "S01: Join+",
                "slot_ms": 9_000,
                "compute_ms_avg": 1_000,
                "compute_ms_max": 19_000,
                "records_read": 10_000,
                "records_written": 11_000,
                "shuffle_output_bytes": 100_000,
                "shuffle_output_bytes_spilled": 0,
                "steps": [{"kind": "JOIN", "substeps": []}],
            }
        ],
        total_slot_ms=10_000,
    )

    result = verdict(
        "SELECT 1 FROM `p.d.t` t JOIN `p.d.l` l "
        "ON EXTRACT(DAY FROM t.d) = EXTRACT(DAY FROM l.d)",
        stages=skewed,
    )

    assert result["failure_mode"] == "KEY_SKEW"
    assert result["evidence_tier"] == 1


# The agent must flag a tool defect, not quietly reverse it.


def test_detection_agent_records_disagreement_instead_of_overriding():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parent.parent
        / "agents"
        / "detection_agent"
        / "instructions.md"
    ).read_text(encoding="utf-8")

    assert "evidence_disagreement" in text
    assert "Do not change `detected` or `confidence_state`" in text
