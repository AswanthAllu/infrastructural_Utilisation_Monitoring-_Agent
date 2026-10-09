from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from google.cloud import bigquery

from .job_labels import label_config


def _field(stage: Dict[str, Any], snake: str, camel: str) -> Any:
    """Read a stage field written either snake_case or camelCase.

    INFORMATION_SCHEMA returns snake_case; the jobs.get REST API returns
    camelCase. Accepting both keeps the analyzer usable from either.
    """

    value = stage.get(snake)

    return stage.get(camel) if value is None else value


def _number(value: Any) -> Optional[float]:
    """Coerce a stage metric to a number, or None if absent."""

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ratio(numerator: Any, denominator: Any) -> Optional[float]:
    """Divide two stage metrics, guarding absent and zero denominators."""

    top = _number(numerator)
    bottom = _number(denominator)

    if top is None or not bottom:
        return None

    return top / bottom


def _steps(stage: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return a stage's steps list, tolerating an absent field."""

    return _field(stage, "steps", "steps") or []


def _is_join_stage(stage: Dict[str, Any]) -> bool:
    """True when any of the stage's steps is a JOIN operator."""

    return any(
        (step.get("kind") or "").upper() == "JOIN"
        for step in _steps(stage)
    )


def _aggregate_is_fused(stage: Dict[str, Any]) -> bool:
    """Whether the stage aggregates as well as joins.

    When BigQuery fuses a join and its partial aggregation into one
    stage, records_written is the post-aggregation row count, so the
    fan-out ratio taken from it understates the join's real output. This
    flag records that the measurement is not trustworthy for that stage;
    it does not by itself change any verdict.
    """

    return any(
        (step.get("kind") or "").upper() == "AGGREGATE"
        for step in _steps(stage)
    )


def _substep_text(stage: Dict[str, Any]) -> List[str]:
    """Flatten the JOIN steps' substeps into plain strings.

    Substeps name the join operator and keys, which is the only link
    between a plan stage and a join in the SQL text.
    """

    out: List[str] = []

    for step in _steps(stage):
        if (step.get("kind") or "").upper() != "JOIN":
            continue

        for substep in step.get("substeps") or []:
            out.append(str(substep))

    return out


def _stage_metrics(stage: Dict[str, Any]) -> Dict[str, Any]:
    """Derive the join-relevant metrics for one stage.

    skew_ratio is the slowest worker's compute time over the average
    worker's; fanout_ratio is rows emitted over rows read.
    """

    compute_avg = _field(stage, "compute_ms_avg", "computeMsAvg")
    compute_max = _field(stage, "compute_ms_max", "computeMsMax")
    records_read = _field(stage, "records_read", "recordsRead")
    records_written = _field(stage, "records_written", "recordsWritten")

    fused = _aggregate_is_fused(stage)

    return {
        "stage_name": _field(stage, "name", "name"),
        "aggregate_fused": fused,
        "fanout_measurable": not fused,
        "step_kinds": [
            (step.get("kind") or "").upper() for step in _steps(stage)
        ],
        "slot_ms": _number(_field(stage, "slot_ms", "slotMs")),
        "shuffle_output_bytes": _number(
            _field(stage, "shuffle_output_bytes", "shuffleOutputBytes")
        ),
        "shuffle_spilled_bytes": _number(
            _field(
                stage,
                "shuffle_output_bytes_spilled",
                "shuffleOutputBytesSpilled",
            )
        ),
        "records_read": _number(records_read),
        "records_written": _number(records_written),
        "skew_ratio": _ratio(compute_max, compute_avg),
        "fanout_ratio": _ratio(records_written, records_read),
        "parallel_inputs": _number(
            _field(stage, "parallel_inputs", "parallelInputs")
        ),
        "wait_ms_max": _number(_field(stage, "wait_ms_max", "waitMsMax")),
        "substeps": _substep_text(stage),
    }


def _max_of(values: Iterable[Optional[float]]) -> Optional[float]:
    """Largest non-None value, or None when there are none."""

    present = [v for v in values if v is not None]

    return max(present) if present else None


def _sum_of(values: Iterable[Optional[float]]) -> Optional[float]:
    """Sum of non-None values, or None when there are none."""

    present = [v for v in values if v is not None]

    return sum(present) if present else None


def analyze_join_stages(
    job_stages: Optional[List[Dict[str, Any]]],
    total_slot_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Reduce a job's execution plan to join-stage evidence.

    Returns only derived metrics. The raw stage list is deliberately not
    included: it is large, and these results are passed into agent
    context where size is a cost.
    """

    if not job_stages:
        return {
            "available": False,
            "reason": "no_job_stages",
            "join_stage_count": 0,
            "join_stages": [],
        }

    join_stages = [
        _stage_metrics(stage)
        for stage in job_stages
        if _is_join_stage(stage)
    ]

    if not join_stages:
        return {
            "available": True,
            "join_stage_count": 0,
            "join_stages": [],
            "stage_count": len(job_stages),
        }

    join_slot_ms = _sum_of(s["slot_ms"] for s in join_stages)

    return {
        "available": True,
        "stage_count": len(job_stages),
        "join_stage_count": len(join_stages),
        "join_stages": join_stages,
        "join_slot_ms": join_slot_ms,
        "join_dominance": _ratio(join_slot_ms, total_slot_ms),
        "max_skew_ratio": _max_of(s["skew_ratio"] for s in join_stages),
        "max_fanout_ratio": _max_of(s["fanout_ratio"] for s in join_stages),
        "total_shuffle_bytes": _sum_of(
            s["shuffle_output_bytes"] for s in join_stages
        ),
        "max_spilled_bytes": _max_of(
            s["shuffle_spilled_bytes"] for s in join_stages
        ),
        "fanout_measurable": any(
            s["fanout_measurable"] for s in join_stages
        ),
        "aggregate_fused_stages": sum(
            1 for s in join_stages if s["aggregate_fused"]
        ),
    }


def get_job_stages(
    job_ids: List[str],
    region: str = "US",
    lookback_hours: int = 48,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch execution plans for specific jobs.

    Phase two of the two-phase fetch: job_stages is a large repeated
    field, so it is pulled only for the jobs the parser flagged as
    containing an analyzable join, never for the whole review window.
    """

    if not job_ids:
        return {"success": True, "stages": {}, "requested": 0}

    client = bigquery.Client(project=project) if project else bigquery.Client()

    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    sql = f"""
        SELECT
          job_id,
          total_slot_ms,
          total_bytes_processed,
          job_stages
        FROM `region-{region}`.INFORMATION_SCHEMA.JOBS
        WHERE creation_time >= @since
          AND job_id IN UNNEST(@job_ids)
    """

    config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("since", "TIMESTAMP", since),
            bigquery.ArrayQueryParameter("job_ids", "STRING", list(job_ids)),
        ]
    )

    try:
        rows = client.query(sql, job_config=label_config(config)).result()

        stages = {
            row["job_id"]: {
                "total_slot_ms": row["total_slot_ms"],
                "total_bytes_processed": row["total_bytes_processed"],
                "job_stages": row["job_stages"],
            }
            for row in rows
        }

        return {
            "success": True,
            "requested": len(job_ids),
            "returned": len(stages),
            "stages": stages,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": "JOB_STAGES_QUERY_FAILED",
            "message": str(exc),
            "stages": {},
        }
