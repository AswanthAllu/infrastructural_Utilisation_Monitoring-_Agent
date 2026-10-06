from typing import Any, Dict, List, Optional

from .partition_detection import detect_missing_partition_filter


def _format_table_ref(table_struct: Dict[str, Any]) -> Optional[str]:
    """Convert INFORMATION_SCHEMA referenced_tables entry to a full table name."""

    project = table_struct.get("project_id")
    dataset = table_struct.get("dataset_id")
    table = table_struct.get("table_id")

    if project and dataset and table:
        return f"{project}.{dataset}.{table}"

    return None


def evaluate_missing_partition_filter_candidate(
    job: Dict[str, Any],
) -> Dict[str, Any]:
    """Evaluate whether a BigQuery job is a Missing Partition Filter candidate."""

    query = job.get("query")

    if not query:
        return {
            "candidate": False,
            "incident_type": "MISSING_PARTITION_FILTER",
            "reason": "missing_query_text",
            "job_id": job.get("job_id"),
        }

    if job.get("cache_hit") is True:
        return {
            "candidate": False,
            "incident_type": "MISSING_PARTITION_FILTER",
            "reason": "cache_hit_no_referenced_tables",
            "job_id": job.get("job_id"),
        }
    referenced_tables = job.get("referenced_tables") or []

    if not referenced_tables:
        return {
            "candidate": False,
            "incident_type": "MISSING_PARTITION_FILTER",
            "reason": "no_referenced_tables",
            "job_id": job.get("job_id"),
        }

    table_results: List[Dict[str, Any]] = []

    for table_ref in referenced_tables:
        table_name = _format_table_ref(table_ref)

        if not table_name:
            continue

        detection = detect_missing_partition_filter(
            table_name=table_name,
            sql=query,
        )

        metadata = detection.get("metadata", {})

        evidence = {
            "job_id": job.get("job_id"),
            "table_name": table_name,
            "query": query,
            "is_partitioned": metadata.get("is_partitioned"),
            "partition_column": metadata.get("partition_column"),
            "partition_type": metadata.get("partition_type"),
            "require_partition_filter": metadata.get(
                "require_partition_filter"
            ),
            "partition_min": metadata.get("partition_min"),
            "partition_max": metadata.get("partition_max"),
            "total_bytes_processed": job.get(
                "total_bytes_processed"
            ),
            "total_slot_ms": job.get("total_slot_ms"),
            "sql_has_partition_filter": detection.get(
                "sql_has_partition_filter"
            ),
        }

        table_results.append(
            {
                "table_name": table_name,
                "detected": detection.get("detected", False),
                "status": detection.get("status"),
                "reason": detection.get("reason"),
                "evidence": evidence,
            }
        )

    detected_tables = [
        result
        for result in table_results
        if result.get("detected") is True
    ]

    return {
        "candidate": bool(detected_tables),
        "incident_type": "MISSING_PARTITION_FILTER",
        "reason": (
            "missing_partition_filter_detected"
            if detected_tables
            else "no_missing_partition_filter_detected"
        ),
        "job_id": job.get("job_id"),
        "table_results": table_results,
        "detected_tables": detected_tables,
    }