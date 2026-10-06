from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from google.cloud import bigquery

from config import join_thresholds as T

from .job_labels import label_config


def _span_days(first_seen, last_seen) -> float:
    """Days between the first and last observed run."""

    if not first_seen or not last_seen:
        return 0.0

    return max((last_seen - first_seen).total_seconds() / 86400.0, 0.0)


def _expected_future_runs(runs: int, span_days: float) -> float:
    """Project runs over the horizon from the observed rate.

    A single run establishes no rate, and a burst inside one day
    extrapolates absurdly, so both fall back to conservative values
    rather than inventing a cadence.
    """

    if runs < 2:
        return T.UNKNOWN_HASH_EXPECTED_RUNS

    if span_days < 1.0:
        return float(runs)

    return runs * (T.RECURRENCE_HORIZON_DAYS / span_days)


def _interval_cov(mean_gap: Optional[float], sd_gap: Optional[float]):
    """Coefficient of variation of the gaps between runs.

    Low variation means a schedule; high variation means a person.
    Undefined below three runs, where there is at most one gap.
    """

    if not mean_gap or sd_gap is None:
        return None

    return sd_gap / mean_gap


def _summarise(row) -> Dict[str, Any]:
    """Turn one aggregated history row into a recurrence summary."""

    runs = int(row["runs"] or 0)
    span = _span_days(row["first_seen"], row["last_seen"])
    cov = _interval_cov(row["mean_gap_s"], row["sd_gap_s"])

    scheduled = bool(row["scheduled_runs"]) or (
        cov is not None and cov <= T.INTERVAL_COV_SCHEDULED
    )

    return {
        "runs": runs,
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
        "observed_span_days": span,
        "mean_gap_seconds": row["mean_gap_s"],
        "interval_cov": cov,
        "scheduled": scheduled,
        "user_email": row["user_email"],
        "expected_future_runs": _expected_future_runs(runs, span),
    }


def unknown_recurrence() -> Dict[str, Any]:
    """Recurrence summary for a query hash with no history.

    A brand-new query is assumed to run once more, which keeps it below
    the routing gate: it is recorded, not sent to a person.
    """

    return {
        "runs": 0,
        "scheduled": False,
        "expected_future_runs": T.UNKNOWN_HASH_EXPECTED_RUNS,
        "source": "no_history",
    }


def get_query_recurrence(
    query_hashes: Iterable[str],
    region: str = "US",
    history_days: int = T.HISTORY_DAYS,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    """Summarise how often each query shape has run.

    The job under review has already been paid for, so the value of a
    finding lives entirely in future runs. This is the input to that
    judgement: see section 6.5 of the design note.
    """

    hashes: List[str] = [h for h in query_hashes if h]

    if not hashes:
        return {"success": True, "recurrence": {}, "requested": 0}

    client = bigquery.Client(project=project) if project else bigquery.Client()

    since = datetime.now(timezone.utc) - timedelta(days=history_days)

    sql = f"""
        WITH history AS (
          SELECT
            query_info.query_hashes.normalized_literals AS query_hash,
            creation_time,
            job_id,
            user_email
          FROM `region-{region}`.INFORMATION_SCHEMA.JOBS
          WHERE creation_time >= @since
            AND job_type = 'QUERY'
            AND statement_type != 'SCRIPT'
            AND query_info.query_hashes.normalized_literals IN UNNEST(@hashes)
        ),
        gaps AS (
          SELECT
            query_hash,
            job_id,
            user_email,
            creation_time,
            TIMESTAMP_DIFF(
              creation_time,
              LAG(creation_time) OVER (
                PARTITION BY query_hash ORDER BY creation_time
              ),
              SECOND
            ) AS gap_s
          FROM history
        )
        SELECT
          query_hash,
          COUNT(*) AS runs,
          MIN(creation_time) AS first_seen,
          MAX(creation_time) AS last_seen,
          AVG(gap_s) AS mean_gap_s,
          STDDEV_SAMP(gap_s) AS sd_gap_s,
          COUNTIF(STARTS_WITH(job_id, 'scheduled_query')) AS scheduled_runs,
          ANY_VALUE(user_email) AS user_email
        FROM gaps
        GROUP BY query_hash
    """

    config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("since", "TIMESTAMP", since),
            bigquery.ArrayQueryParameter("hashes", "STRING", hashes),
        ]
    )

    try:
        rows = client.query(sql, job_config=label_config(config)).result()

        recurrence = {row["query_hash"]: _summarise(row) for row in rows}

        for query_hash in hashes:
            recurrence.setdefault(query_hash, unknown_recurrence())

        return {
            "success": True,
            "requested": len(hashes),
            "recurrence": recurrence,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": "RECURRENCE_QUERY_FAILED",
            "message": str(exc),
            "recurrence": {h: unknown_recurrence() for h in hashes},
        }


def get_slot_ms_reference(
    region: str = "US",
    history_days: int = T.HISTORY_DAYS,
    project: Optional[str] = None,
) -> Optional[float]:
    """Slot-time percentile that defines 'materially expensive'.

    Defined relative to what the organisation actually runs, so the check
    needs no budget configuration to cold-start. Returns None when the
    percentile gate is disabled or the history cannot be read.
    """

    if T.SLOT_MS_PERCENTILE is None:
        return None

    client = bigquery.Client(project=project) if project else bigquery.Client()

    since = datetime.now(timezone.utc) - timedelta(days=history_days)

    sql = f"""
        SELECT
          APPROX_QUANTILES(total_slot_ms, 100)[OFFSET(@percentile)] AS reference
        FROM `region-{region}`.INFORMATION_SCHEMA.JOBS
        WHERE creation_time >= @since
          AND job_type = 'QUERY'
          AND statement_type != 'SCRIPT'
          AND state = 'DONE'
          AND cache_hit = FALSE
          AND total_slot_ms > 0
    """

    config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("since", "TIMESTAMP", since),
            bigquery.ScalarQueryParameter(
                "percentile", "INT64", T.SLOT_MS_PERCENTILE
            ),
        ]
    )

    try:
        for row in client.query(sql, job_config=label_config(config)).result():
            return float(row["reference"]) if row["reference"] else None

    except Exception:
        return None

    return None
