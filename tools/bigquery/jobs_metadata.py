from typing import Any, Dict, List, Optional

from google.cloud import bigquery

from .job_labels import EXCLUDE_AGENT_JOBS_SQL, agent_job_config


def get_recent_query_jobs(
    region: str = "US",
    lookback_hours: int = 24,
    limit: int = 100,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return recent completed BigQuery query jobs from
    INFORMATION_SCHEMA.JOBS.

    The query intentionally reviews normal query jobs across
    the project rather than restricting results to a specific
    table or query string.

    INFORMATION_SCHEMA queries are excluded so that the
    monitoring query itself does not appear in the results.
    """

    client = (
        bigquery.Client(project=project)
        if project
        else bigquery.Client()
    )

    dataset = f"region-{region}.INFORMATION_SCHEMA.JOBS"

    sql = f"""
        SELECT
            creation_time,
            start_time,
            end_time,
            project_id,
            user_email,
            job_id,
            job_type,
            state,
            query,
            statement_type,
            query_info.query_hashes.normalized_literals AS query_hash,
            total_bytes_processed,
            total_bytes_billed,
            total_slot_ms,
            cache_hit,
            error_result,
            referenced_tables
        FROM `{dataset}`
        WHERE creation_time >= TIMESTAMP_SUB(
            CURRENT_TIMESTAMP(),
            INTERVAL {lookback_hours} HOUR
        )
        AND job_type = 'QUERY'
        AND state = 'DONE'
        AND query IS NOT NULL
        AND NOT REGEXP_CONTAINS(
            LOWER(query),
            r'information_schema'
        )
        -- The review profiles real tables to recover join-key
        -- cardinality. Those queries read nothing from
        -- INFORMATION_SCHEMA, so the filter above does not catch them and
        -- each run would otherwise generate the next run's incidents.
        AND {EXCLUDE_AGENT_JOBS_SQL}
        ORDER BY creation_time DESC
        LIMIT {limit};
    """

    try:
        query_job = client.query(
            sql,
            location=region,
            job_config=agent_job_config(),
        )

        rows = query_job.result()

        jobs: List[Dict[str, Any]] = []

        for row in rows:
            jobs.append(
                {
                    key: row[key]
                    for key in row.keys()
                }
            )

        return {
            "success": True,
            "region": region,
            "lookback_hours": lookback_hours,
            "count": len(jobs),
            "jobs": jobs,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": "BIGQUERY_QUERY_FAILED",
            "message": str(exc),
        }