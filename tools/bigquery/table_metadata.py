import time
from typing import Any, Dict, Iterable, List, Optional

from google.api_core.exceptions import (
    GoogleAPICallError,
    NotFound,
)
from google.cloud import bigquery

from .job_labels import label_config


CACHE_TTL_SECONDS = 900

_client: Optional[bigquery.Client] = None
_table_cache: Dict[str, Any] = {}


def _get_client() -> bigquery.Client:
    """Return a lazily constructed, reused BigQuery client."""

    global _client

    if _client is None:
        _client = bigquery.Client()

    return _client


def _get_table(table_name: str):
    """Fetch table metadata, reusing a recent result when available.

    A join references at least two tables per job, so the uncached
    lookup ran once per table per job. Failures are not cached: they
    propagate so the caller's existing error handling still applies.
    """

    cached = _table_cache.get(table_name)

    if cached and time.monotonic() - cached["fetched_at"] < CACHE_TTL_SECONDS:
        return cached["table"]

    table = _get_client().get_table(table_name)

    _table_cache[table_name] = {
        "table": table,
        "fetched_at": time.monotonic(),
    }

    return table


def clear_cache() -> None:
    """Drop cached table metadata."""

    _table_cache.clear()
    _partition_range_cache.clear()


def get_table_partition_info(
    table_name: str,
) -> Dict[str, Any]:
    """
    Retrieve BigQuery table partition metadata.

    V1 supports time-partitioned tables.
    """

    try:
        table = _get_table(table_name)

        if table.time_partitioning is not None:

            partitioning = (
                table.time_partitioning
            )

            return {
                "success": True,
                "table": table.full_table_id,
                "table_type": table.table_type,
                "is_partitioned": True,
                "partition_column": (
                    partitioning.field
                ),
                "partition_type": (
                    partitioning.type_
                ),
                "partition_expiration_ms": (
                    partitioning.expiration_ms
                ),
                "require_partition_filter": (
                    partitioning.require_partition_filter
                ),
            }

        return {
            "success": True,
            "table": table.full_table_id,
            "table_type": table.table_type,
            "is_partitioned": False,
            "partition_column": None,
            "partition_type": None,
            "partition_expiration_ms": None,
            "require_partition_filter": False,
        }

    except NotFound:
        return {
            "success": False,
            "error": "TABLE_NOT_FOUND",
            "message": (
                f"Table '{table_name}' "
                "was not found."
            ),
        }

    except GoogleAPICallError as exc:
        return {
            "success": False,
            "error": "BIGQUERY_API_ERROR",
            "message": str(exc),
        }

    except Exception as exc:
        return {
            "success": False,
            "error": "UNKNOWN_ERROR",
            "message": str(exc),
        }


_partition_range_cache: Dict[str, Any] = {}


def get_partition_range(table_name: str) -> Dict[str, Any]:
    """Return the first and last populated partition of a table.

    Remediation otherwise has no factual anchor for a date predicate and
    falls back to CURRENT_DATE(), which on historical data produces a
    filter matching no rows at all.
    """

    cached = _partition_range_cache.get(table_name)

    if cached and time.monotonic() - cached["fetched_at"] < CACHE_TTL_SECONDS:
        return cached["range"]

    parts = table_name.split(".")

    if len(parts) != 3:
        return {"success": False, "error": "UNQUALIFIED_TABLE_NAME"}

    project, dataset, table = parts

    sql = f"""
        SELECT
          MIN(partition_id) AS partition_min,
          MAX(partition_id) AS partition_max,
          COUNT(*)          AS partition_count
        FROM `{project}.{dataset}`.INFORMATION_SCHEMA.PARTITIONS
        WHERE table_name = @table
          AND partition_id NOT IN ('__NULL__', '__UNPARTITIONED__')
    """

    config = label_config(
        bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("table", "STRING", table)
            ]
        )
    )

    try:
        rows = list(_get_client().query(sql, job_config=config).result())

        row = rows[0] if rows else None

        result = {
            "success": True,
            "partition_min": row["partition_min"] if row else None,
            "partition_max": row["partition_max"] if row else None,
            "partition_count": row["partition_count"] if row else 0,
        }

    except Exception as exc:
        result = {
            "success": False,
            "error": "PARTITION_RANGE_FAILED",
            "message": str(exc),
        }

    _partition_range_cache[table_name] = {
        "range": result,
        "fetched_at": time.monotonic(),
    }

    return result


def get_table_stats(table_name: str) -> Dict[str, Any]:
    """Retrieve the size and shape metadata the join check needs.

    Row count is the Tier 0 size floor; clustering on a join key means
    BigQuery can co-locate and shuffle less.
    """

    try:
        table = _get_table(table_name)

        return {
            "success": True,
            "table": table_name,
            "rows": table.num_rows,
            "logical_bytes": table.num_bytes,
            "clustering_fields": list(table.clustering_fields or []),
            "columns": [
                {"name": field.name, "type": field.field_type}
                for field in table.schema
            ],
        }

    except NotFound:
        return {
            "success": False,
            "error": "TABLE_NOT_FOUND",
            "message": f"Table '{table_name}' was not found.",
        }

    except Exception as exc:
        return {
            "success": False,
            "error": "TABLE_STATS_FAILED",
            "message": str(exc),
        }


def get_table_rows(
    table_names: Iterable[str],
) -> Dict[str, Optional[int]]:
    """Map table name to row count, None where the lookup failed.

    None is distinct from zero: an unreadable table is not a small one,
    and the size floor must not suppress on missing data.
    """

    rows: Dict[str, Optional[int]] = {}

    for table_name in table_names:
        stats = get_table_stats(table_name)
        rows[table_name] = stats.get("rows") if stats.get("success") else None

    return rows


def build_sqlglot_schema(
    table_names: Iterable[str],
) -> Dict[str, Any]:
    """Build a sqlglot schema mapping for the given tables.

    The join parser uses it to resolve unqualified join columns to their
    source table. Tables that cannot be read are simply absent, which
    leaves their joins unresolved rather than misresolved.
    """

    schema: Dict[str, Any] = {}

    for table_name in table_names:
        parts = table_name.split(".")

        if len(parts) != 3:
            continue

        stats = get_table_stats(table_name)

        if not stats.get("success"):
            continue

        project, dataset, table = parts

        columns = {
            column["name"]: column["type"]
            for column in stats.get("columns", [])
        }

        schema.setdefault(project, {}).setdefault(dataset, {})[table] = columns

    return schema


def referenced_table_names(
    referenced_tables: Optional[List[Dict[str, Any]]],
) -> List[str]:
    """Convert INFORMATION_SCHEMA referenced_tables into dotted names."""

    names = []

    for entry in referenced_tables or []:
        project = entry.get("project_id")
        dataset = entry.get("dataset_id")
        table = entry.get("table_id")

        if project and dataset and table:
            names.append(f"{project}.{dataset}.{table}")

    return names
