import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from google.cloud import bigquery

from config import join_thresholds as T

from .job_labels import agent_job_config, label_config


CACHE_TTL_SECONDS = 86_400

_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}


def _client(project: Optional[str] = None) -> bigquery.Client:
    return bigquery.Client(project=project) if project else bigquery.Client()


def _profile_sql(table: str, column: str) -> str:
    """Count rows and distinct values of one column.

    Only the join key is read. APPROX_COUNT_DISTINCT is HLL++, so the
    NDV carries roughly a percent of error — fine for deciding an order
    of magnitude, not for a near-threshold call.
    """

    return f"""
        SELECT
          COUNT(*)                        AS row_count,
          APPROX_COUNT_DISTINCT(`{column}`) AS ndv,
          COUNTIF(`{column}` IS NULL)     AS null_rows
        FROM `{table}`
    """


def _estimate_bytes(
    sql: str,
    client: bigquery.Client,
) -> Optional[int]:
    """Dry-run a profiling query to price it before running it."""

    config = agent_job_config(dry_run=True, use_query_cache=False)

    try:
        return client.query(sql, job_config=config).total_bytes_processed
    except Exception:
        return None


def profile_columns(
    targets: Iterable[Tuple[str, str]],
    project: Optional[str] = None,
    max_bytes: int = T.PROFILE_MAX_BYTES,
) -> Dict[str, Any]:
    """Read row count and distinct-value count for join key columns.

    This is the only part of the check that spends money, so each column
    is dry-run first and skipped when it would read more than max_bytes.
    A refusal degrades the verdict to INCONCLUSIVE rather than guessing.
    """

    targets = [t for t in targets if t and t[0] and t[1]]

    if not targets:
        return {"success": True, "key_stats": {}, "profiled": 0}

    if not T.PROFILING_ENABLED:
        return {
            "success": True,
            "key_stats": {},
            "profiled": 0,
            "skipped_reason": "profiling_disabled",
        }

    client = _client(project)

    key_stats: Dict[Tuple[str, str], Dict[str, Any]] = {}
    skipped: List[Dict[str, Any]] = []
    profiled = 0
    # Counted separately from `profiled`, which only records columns this
    # call paid for. Without it a run served entirely from cache reports
    # "profiled: 0" while returning a full set of estimates, which reads
    # as though no profiling backed the verdicts.
    from_cache = 0

    for table, column in targets:
        cached = _cache.get((table, column))

        if cached and time.monotonic() - cached["fetched_at"] < CACHE_TTL_SECONDS:
            key_stats[(table, column)] = cached["stats"]
            from_cache += 1
            continue

        sql = _profile_sql(table, column)

        estimated = _estimate_bytes(sql, client)

        if estimated is None:
            skipped.append({"table": table, "column": column, "reason": "dry_run_failed"})
            continue

        if estimated > max_bytes:
            skipped.append(
                {
                    "table": table,
                    "column": column,
                    "reason": "over_budget",
                    "estimated_bytes": estimated,
                }
            )
            continue

        try:
            rows = list(
                client.query(sql, job_config=agent_job_config()).result()
            )
        except Exception as exc:
            skipped.append(
                {
                    "table": table,
                    "column": column,
                    "reason": "profile_query_failed",
                    "message": str(exc),
                }
            )
            continue

        if not rows:
            continue

        row = rows[0]

        stats = {
            "table": table,
            "column": column,
            "row_count": row["row_count"],
            "ndv": row["ndv"],
            "null_rows": row["null_rows"],
            "estimated_bytes": estimated,
            "source": "profiled",
        }

        _cache[(table, column)] = {"stats": stats, "fetched_at": time.monotonic()}
        key_stats[(table, column)] = stats
        profiled += 1

    return {
        "success": True,
        "key_stats": key_stats,
        "profiled": profiled,
        "from_cache": from_cache,
        "skipped": skipped,
    }


def clear_cache() -> None:
    """Drop cached column profiles."""

    _cache.clear()
