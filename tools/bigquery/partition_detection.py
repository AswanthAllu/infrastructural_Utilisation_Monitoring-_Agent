from typing import Any, Dict

from tools.bigquery.table_metadata import (
    get_partition_range,
    get_table_partition_info,
)

from utils.sql_parser import has_partition_filter


def _with_partition_range(metadata: Dict[str, Any], table_name: str) -> Dict[str, Any]:
    """Attach the table's populated partition range to its metadata.

    Advisory only: a failed lookup leaves the keys absent rather than
    failing detection.
    """

    partition_range = get_partition_range(table_name)

    if partition_range.get("success"):
        metadata["partition_min"] = partition_range.get("partition_min")
        metadata["partition_max"] = partition_range.get("partition_max")

    return metadata


def detect_missing_partition_filter(
    table_name: str,
    sql: str,
) -> Dict[str, Any]:
    """Detect whether a query is missing a usable partition filter."""

    metadata = get_table_partition_info(table_name)

    # Metadata lookup failed
    if not metadata.get("success"):

        return {
            "detected": False,
            "status": "FAILED",
            "incident_type": (
                "MISSING_PARTITION_FILTER"
            ),
            "reason": metadata.get(
                "message",
                "Unable to retrieve "
                "table metadata.",
            ),
            "metadata": metadata,
        }

    # Table is not partitioned
    if not metadata.get(
        "is_partitioned"
    ):

        return {
            "detected": False,
            "status": "NOT_APPLICABLE",
            "incident_type": (
                "MISSING_PARTITION_FILTER"
            ),
            "reason": (
                "The table is not partitioned, "
                "so the Missing Partition Filter "
                "issue does not apply."
            ),
            "metadata": metadata,
            "sql_has_partition_filter": False,
        }

    partition_column = metadata.get(
        "partition_column"
    )

    # Partitioned table but no column
    if not partition_column:

        return {
            "detected": False,
            "status": "FAILED",
            "incident_type": (
                "MISSING_PARTITION_FILTER"
            ),
            "reason": (
                "The table is partitioned, "
                "but no partition column "
                "was returned."
            ),
            "metadata": metadata,
        }

    metadata = _with_partition_range(metadata, table_name)

    # Analyze SQL
    sql_has_partition_filter = (has_partition_filter(sql,partition_column))

    # Filter exists
    if sql_has_partition_filter:

        return {
            "detected": False,
            "status": "NOT_DETECTED",
            "incident_type": (
                "MISSING_PARTITION_FILTER"
            ),
            "reason": (
                f"The query contains a usable "
                f"filter on partition column "
                f"'{partition_column}'."
            ),
            "metadata": metadata,
            "sql_has_partition_filter": True,
        }

    # Filter missing
    return {
    "detected": True,
    "status": "DETECTED",
    "incident_type": "MISSING_PARTITION_FILTER",
    "reason": (
        f"The table is partitioned by '{partition_column}', "
        "but the query does not contain a usable partition filter."
    ),
    "metadata": metadata,
    "sql_has_partition_filter": False,
}