from typing import Any, Dict, List, Optional

from config import join_thresholds as T

from .column_profile import profile_columns
from .job_stages import analyze_join_stages, get_job_stages
from .join_detection import detect_high_cardinality_join, profile_targets
from .reason_text import explain
from .query_recurrence import (
    get_query_recurrence,
    get_slot_ms_reference,
    unknown_recurrence,
)
from .table_constraints import get_primary_key_columns
from .table_metadata import (
    build_sqlglot_schema,
    get_table_rows,
    referenced_table_names,
)

from utils.join_parser import extract_joins


def _prefilter(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only jobs whose SQL contains an analyzable join.

    Parsed without a schema first, because parsing is free and schema
    lookups are not. Jobs with no join at all never reach the metadata
    or stage fetches.
    """

    candidates = []

    for job in jobs:
        query = job.get("query")

        if not query:
            continue

        parsed = extract_joins(query)

        if not parsed.get("success") or not parsed.get("analyzable_joins"):
            continue

        candidates.append({"job": job, "parsed": parsed})

    return candidates


def _requalify(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Re-parse a job's SQL with its tables' real schema.

    Only worthwhile for jobs already known to contain a join, and only
    matters when the query leaves join columns unqualified.
    """

    job = entry["job"]
    tables = referenced_table_names(job.get("referenced_tables"))

    if not tables:
        return entry["parsed"]

    schema = build_sqlglot_schema(tables)

    if not schema:
        return entry["parsed"]

    requalified = extract_joins(job["query"], schema=schema)

    return requalified if requalified.get("success") else entry["parsed"]


def _joined_tables(parsed: Dict[str, Any]) -> List[str]:
    """Every base table named by an analyzable join's keys."""

    return sorted(
        {
            table
            for join in parsed.get("analyzable_joins", [])
            for table in join.get("tables") or []
        }
    )


def _candidate(
    job: Dict[str, Any],
    parsed: Dict[str, Any],
    detection: Dict[str, Any],
) -> Dict[str, Any]:
    """Shape one detection into the candidate contract used by review."""

    base_tables = parsed.get("base_tables") or []

    return {
        "candidate": detection.get("detected", False),
        "incident_type": "HIGH_CARDINALITY_JOIN",
        "reason": detection.get("reason"),
        "job_id": job.get("job_id"),
        "tables": _joined_tables(parsed),
        # The table the query reads first. `tables` is sorted, so taking
        # its head named a table the SQL did not start FROM on 10 of the
        # 12 multi-table statements in the validation suite, and on CTE
        # joins it named the CTE rather than any real table.
        "primary_table": base_tables[0] if base_tables else None,
        "detection": detection,
    }


def review_jobs_for_joins(
    jobs: List[Dict[str, Any]],
    region: str = "US",
    lookback_hours: int = 48,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate completed jobs against the HIGH_CARDINALITY_JOIN incident.

    Batches every BigQuery lookup across the whole review rather than
    per job: stages, recurrence, row counts and constraints are each a
    single round trip for the jobs that need them.
    """

    entries = _prefilter(jobs)

    if not entries:
        return {
            "success": True,
            "jobs_with_joins": 0,
            "candidates": [],
            "scale_profile": T.SCALE_PROFILE,
        }

    for entry in entries:
        entry["parsed"] = _requalify(entry)

    job_ids = [e["job"]["job_id"] for e in entries if e["job"].get("job_id")]

    stages_response = get_job_stages(
        job_ids,
        region=region,
        lookback_hours=lookback_hours,
        project=project,
    )

    query_hashes = {
        e["job"].get("query_hash") for e in entries if e["job"].get("query_hash")
    }

    recurrence_response = get_query_recurrence(
        query_hashes,
        region=region,
        project=project,
    )

    tables = sorted(
        {table for e in entries for table in _joined_tables(e["parsed"])}
    )

    table_rows = get_table_rows(tables)

    constraints = get_primary_key_columns(tables, project=project)

    slot_ms_reference = get_slot_ms_reference(region=region, project=project)

    stages_by_job = stages_response.get("stages", {})
    recurrence_by_hash = recurrence_response.get("recurrence", {})

    def evaluate(entry, key_stats=None):
        job = entry["job"]
        parsed = entry["parsed"]

        stage_record = stages_by_job.get(job.get("job_id")) or {}

        total_slot_ms = stage_record.get("total_slot_ms") or job.get(
            "total_slot_ms"
        )

        stage_analysis = analyze_join_stages(
            stage_record.get("job_stages"),
            total_slot_ms=total_slot_ms,
        )

        recurrence = recurrence_by_hash.get(
            job.get("query_hash"), unknown_recurrence()
        )

        detection = detect_high_cardinality_join(
            job=job,
            joins=parsed.get("joins", []),
            stages=stage_analysis,
            table_rows=table_rows,
            pk_columns=constraints.get("primary_keys", set()),
            expected_future_runs=recurrence.get(
                "expected_future_runs", T.UNKNOWN_HASH_EXPECTED_RUNS
            ),
            slot_ms_reference=slot_ms_reference,
            key_stats=key_stats,
        )

        detection["recurrence"] = recurrence
        # The other two detectors already carry this in their evidence.
        # Without it the results table has no numeric column at all, so
        # incidents cannot be ranked by cost without parsing JSON.
        detection["total_slot_ms"] = total_slot_ms

        return detection, stage_analysis

    # Pass one: classify from the execution plan alone.
    results = {id(entry): evaluate(entry) for entry in entries}

    # Pass two: only the jobs whose fan-out the plan could not measure
    # are worth paying to profile, and only their join key columns.
    needs_profile = [
        entry
        for entry in entries
        if results[id(entry)][0].get("reason")
        == "fanout_unmeasurable_aggregate_fused"
    ]

    profile_result = {"key_stats": {}, "profiled": 0}

    if needs_profile:
        targets = []

        for entry in needs_profile:
            for target in profile_targets(
                entry["parsed"].get("analyzable_joins", [])
            ):
                if target not in targets:
                    targets.append(target)

        profile_result = profile_columns(targets, project=project)

        if profile_result.get("key_stats"):
            for entry in needs_profile:
                results[id(entry)] = evaluate(
                    entry, key_stats=profile_result["key_stats"]
                )

    candidates = []
    evaluated = []

    for entry in entries:
        job = entry["job"]
        parsed = entry["parsed"]

        detection, stage_analysis = results[id(entry)]

        evaluated.append(
            {
                "job_id": job.get("job_id"),
                "confidence_state": detection.get("confidence_state"),
                "failure_mode": detection.get("failure_mode"),
                "routed": detection.get("routed"),
                # PATTERN_ONLY has two unrelated causes — tables below the
                # size floor, and a plan that showed nothing — and without
                # the reason they are indistinguishable from the outside.
                "reason": detection.get("reason"),
                "explanation": explain(detection.get("reason")),
                "evidence_tier": detection.get("evidence_tier"),
                # The gate that decides three of the four failure modes,
                # and the one threshold still being tuned.
                "join_dominance": stage_analysis.get("join_dominance"),
            }
        )

        if detection.get("detected"):
            candidates.append(
                {
                    "job": job,
                    "analysis": _candidate(job, parsed, detection),
                }
            )

    return {
        "success": True,
        "jobs_with_joins": len(entries),
        "stages_error": stages_response.get("message"),
        # Tier 2 is the only part of the check that bills, so its counters
        # are a cost meter rather than diagnostics.
        "profiling": {
            "requested_for_jobs": len(needs_profile),
            "columns_profiled": profile_result.get("profiled", 0),
            "columns_from_cache": profile_result.get("from_cache", 0),
            "skipped": profile_result.get("skipped", []),
            "skipped_reason": profile_result.get("skipped_reason"),
        },
        "scale_profile": T.SCALE_PROFILE,
        "evaluated": evaluated,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "routed_count": sum(
            1 for c in candidates if c["analysis"]["detection"].get("routed")
        ),
    }
