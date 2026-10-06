"""End-to-end wiring for the join review, with BigQuery mocked out."""

import pytest

from tools.bigquery import join_review


GIB = 1024 ** 3

SKEWED_SQL = "SELECT 1 FROM `p.d.fact` f JOIN `p.d.dim` d ON f.k = d.k"


def job(job_id="j1", query=SKEWED_SQL, **overrides):
    base = {
        "job_id": job_id,
        "query": query,
        "state": "DONE",
        "query_hash": "hash1",
        "total_slot_ms": 10_000_000,
        "total_bytes_processed": 100 * GIB,
        "user_email": "someone@example.com",
        "referenced_tables": [
            {"project_id": "p", "dataset_id": "d", "table_id": "fact"},
            {"project_id": "p", "dataset_id": "d", "table_id": "dim"},
        ],
    }
    base.update(overrides)

    return base


def skewed_stages():
    return [
        {
            "name": "S01: Join+",
            "slot_ms": 9_000_000,
            "compute_ms_avg": 1_000,
            "compute_ms_max": 19_000,
            "records_read": 10_000_000,
            "records_written": 10_500_000,
            "shuffle_output_bytes": 40 * GIB,
            "shuffle_output_bytes_spilled": 20 * GIB,
            "parallel_inputs": 400,
            "steps": [{"kind": "JOIN", "substeps": ["INNER HASH JOIN ON k"]}],
        }
    ]


@pytest.fixture(autouse=True)
def no_bigquery(monkeypatch):
    """Replace every BigQuery round trip with a fixed response."""

    monkeypatch.setattr(
        join_review,
        "get_job_stages",
        lambda job_ids, **kw: {
            "success": True,
            "returned": len(job_ids),
            "stages": {
                jid: {
                    "total_slot_ms": 10_000_000,
                    "total_bytes_processed": 100 * GIB,
                    "job_stages": skewed_stages(),
                }
                for jid in job_ids
            },
        },
    )

    monkeypatch.setattr(
        join_review,
        "get_query_recurrence",
        lambda hashes, **kw: {
            "success": True,
            "recurrence": {
                h: {"runs": 700, "scheduled": True, "expected_future_runs": 720.0}
                for h in hashes
            },
        },
    )

    monkeypatch.setattr(
        join_review, "get_slot_ms_reference", lambda **kw: 6_800_000.0
    )

    monkeypatch.setattr(
        join_review,
        "get_primary_key_columns",
        lambda tables, **kw: {"success": True, "primary_keys": set()},
    )

    monkeypatch.setattr(
        join_review,
        "get_table_rows",
        lambda tables: {t: 50_000_000 for t in tables},
    )

    monkeypatch.setattr(join_review, "build_sqlglot_schema", lambda tables: {})


def test_skewed_recurring_join_is_a_routed_candidate():
    result = join_review.review_jobs_for_joins([job()])

    assert result["success"] is True
    assert result["jobs_with_joins"] == 1
    assert result["candidate_count"] == 1
    assert result["routed_count"] == 1

    detection = result["candidates"][0]["analysis"]["detection"]

    assert detection["failure_mode"] == "KEY_SKEW"
    assert detection["confidence_state"] == "CONFIRMED"
    assert detection["recurrence"]["expected_future_runs"] == 720.0


def test_candidate_carries_both_joined_tables():
    result = join_review.review_jobs_for_joins([job()])

    assert result["candidates"][0]["analysis"]["tables"] == [
        "p.d.dim",
        "p.d.fact",
    ]


def test_jobs_without_joins_never_reach_bigquery(monkeypatch):
    called = []

    monkeypatch.setattr(
        join_review,
        "get_job_stages",
        lambda job_ids, **kw: called.append(job_ids) or {"stages": {}},
    )

    result = join_review.review_jobs_for_joins(
        [job(query="SELECT 1 FROM `p.d.fact` WHERE d = '2026-01-01'")]
    )

    assert result["jobs_with_joins"] == 0
    assert result["candidates"] == []
    assert called == []


def test_unnest_only_job_is_prefiltered_out():
    result = join_review.review_jobs_for_joins(
        [job(query="SELECT 1 FROM `p.d.fact` f CROSS JOIN UNNEST(f.items) AS i")]
    )

    assert result["jobs_with_joins"] == 0


def test_job_without_query_text_is_skipped():
    result = join_review.review_jobs_for_joins([job(query=None)])

    assert result["jobs_with_joins"] == 0


def test_one_off_query_is_evaluated_but_not_routed(monkeypatch):
    monkeypatch.setattr(
        join_review,
        "get_query_recurrence",
        lambda hashes, **kw: {
            "success": True,
            "recurrence": {
                h: {"runs": 1, "scheduled": False, "expected_future_runs": 1.0}
                for h in hashes
            },
        },
    )

    result = join_review.review_jobs_for_joins([job()])

    assert result["candidate_count"] == 1
    assert result["routed_count"] == 0

    detection = result["candidates"][0]["analysis"]["detection"]

    assert detection["confidence_state"] == "CONFIRMED"
    assert detection["routing_reason"] == "below_min_expected_runs"


def test_missing_stages_degrade_to_probable(monkeypatch):
    monkeypatch.setattr(
        join_review,
        "get_job_stages",
        lambda job_ids, **kw: {"success": False, "message": "denied", "stages": {}},
    )

    result = join_review.review_jobs_for_joins([job()])

    detection = result["candidates"][0]["analysis"]["detection"]

    assert detection["confidence_state"] == "PROBABLE"
    assert detection["missing_evidence"] == ["job_stages"]


def test_the_active_scale_profile_is_reported():
    """Every floor differs between sandbox and production, so a verdict
    cannot be read without knowing which profile produced it. The full
    threshold dump was validation scaffolding; the profile name is not."""

    result = join_review.review_jobs_for_joins([job()])

    assert result["scale_profile"] in ("sandbox", "production")


def test_settled_diagnostics_are_no_longer_reported():
    """These answered questions that validation closed. Keeping them
    made `evaluated` the largest block in the response."""

    result = join_review.review_jobs_for_joins([job()])

    assert "stages_returned" not in result
    assert "slot_ms_reference" not in result
    assert "thresholds" not in result

    for entry in result["evaluated"]:
        for field in (
            "stage_row_returned",
            "cache_hit",
            "total_slot_ms",
            "fanout_measurable",
            "join_stage_count",
        ):
            assert field not in entry, f"{field} survived the strip"

        # What remains has to stay: the verdict, why, and how strong.
        for field in (
            "job_id",
            "confidence_state",
            "failure_mode",
            "routed",
            "reason",
            "explanation",
            "evidence_tier",
            "join_dominance",
        ):
            assert field in entry, f"{field} was stripped by mistake"


def test_every_job_is_recorded_even_when_not_a_candidate():
    result = join_review.review_jobs_for_joins(
        [job("j1"), job("j2", query="SELECT 1 FROM `p.d.fact` f CROSS JOIN `p.d.dim` d")]
    )

    assert len(result["evaluated"]) == 2
    assert {e["job_id"] for e in result["evaluated"]} == {"j1", "j2"}
