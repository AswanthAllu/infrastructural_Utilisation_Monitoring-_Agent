import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from google.cloud import bigquery
from google.cloud.exceptions import NotFound

from config.settings import (
    BQ_RAW_RESULTS_TABLE,
    BQ_RESULTS_DATASET,
    BQ_RESULTS_TABLE,
    PROJECT_ID,
)


TABLE_SCHEMA = [
    bigquery.SchemaField("record_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("job_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("incident_type", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("table_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("original_query", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("detection_status", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("diagnosis_status", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("remediation_status", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("severity", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("confidence", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("action_category", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("incident_summary", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("diagnosed_root_cause", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("remediation_recommendation", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("remediation_query", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("executed", "BOOL", mode="NULLABLE"),
    bigquery.SchemaField("verification_required", "BOOL", mode="NULLABLE"),
    bigquery.SchemaField("verification_result", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("escalation_reason", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("workflow_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("task_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("incident_evidence", "JSON", mode="NULLABLE"),
]

RAW_TABLE_SCHEMA = [
    bigquery.SchemaField("record_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("job_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("raw_response", "JSON", mode="NULLABLE"),
]


def _dataset_id(project: Optional[str] = None) -> str:
    return f"{project or PROJECT_ID}.{BQ_RESULTS_DATASET}"


def _table_id(project: Optional[str] = None) -> str:
    return f"{project or PROJECT_ID}.{BQ_RESULTS_DATASET}.{BQ_RESULTS_TABLE}"


def _raw_table_id(project: Optional[str] = None) -> str:
    return f"{project or PROJECT_ID}.{BQ_RESULTS_DATASET}.{BQ_RAW_RESULTS_TABLE}"


def _ensure_table(
    client: bigquery.Client,
    project: Optional[str],
    table_id: str,
    schema: list,
) -> Dict[str, Any]:
    dataset_id = _dataset_id(project)

    try:
        client.get_dataset(dataset_id)
    except NotFound:
        try:
            client.create_dataset(bigquery.Dataset(dataset_id))
        except Exception as exc:  # keep broad to avoid failing callers
            return {"success": False, "error": "BIGQUERY_CREATE_DATASET_FAILED", "message": str(exc)}
    except Exception as exc:
        return {"success": False, "error": "BIGQUERY_GET_DATASET_FAILED", "message": str(exc)}

    try:
        client.get_table(table_id)
        return {"success": True, "created": False, "table_id": table_id}
    except Exception:
        try:
            client.create_table(bigquery.Table(table_id, schema=schema))
            return {"success": True, "created": True, "table_id": table_id}
        except Exception as exc:  # keep broad to avoid failing callers
            return {"success": False, "error": "BIGQUERY_CREATE_TABLE_FAILED", "message": str(exc)}


def ensure_results_table(project: Optional[str] = None) -> Dict[str, Any]:
    """Create the results dataset and structured table if they do not already exist."""

    client = bigquery.Client(project=project) if project else bigquery.Client()
    return _ensure_table(client, project, _table_id(project), TABLE_SCHEMA)


def ensure_raw_results_table(project: Optional[str] = None) -> Dict[str, Any]:
    """Create the raw response archive table if it does not already exist."""

    client = bigquery.Client(project=project) if project else bigquery.Client()
    return _ensure_table(client, project, _raw_table_id(project), RAW_TABLE_SCHEMA)


def _qualified_incident_type(detection: Dict[str, Any]) -> Optional[str]:
    """Incident type, suffixed with the failure mode when there is one.

    HIGH_CARDINALITY_JOIN is four distinct problems with four different
    fixes and different owners, so reporting them under one value made
    them indistinguishable. They are qualified rather than given a column
    of their own: `HIGH_CARDINALITY_JOIN.KEY_SKEW`.

    The other detectors have no sub-types and are unchanged.
    """

    incident_type = detection.get("incident_type")
    failure_mode = detection.get("failure_mode")

    if not incident_type or not failure_mode:
        return incident_type

    return f"{incident_type}.{failure_mode}"


def _incident_evidence(detection: Dict[str, Any]) -> Optional[str]:
    """The detection evidence, carrying the detector's own verdict.

    `evidence_strength` is CONFIRMED or PROBABLE — whether the finding was
    measured from the execution plan or inferred from the SQL. No column
    records it: `diagnosis_status` says only that a diagnosis was produced
    and `confidence` is the agent's confidence in its own reasoning, so a
    tier-0 inference is otherwise indistinguishable from a measurement.
    """

    evidence = detection.get("evidence")
    strength = detection.get("confidence_state")

    if evidence is None and strength is None:
        return None

    merged = dict(evidence or {})

    if strength is not None:
        merged["evidence_strength"] = strength

    return json.dumps(merged, default=str)


def _flatten_agent_response(
    issue_reference: Optional[str],
    agent_response: Dict[str, Any],
) -> Dict[str, Any]:
    """Pull the key fields out of the detection/diagnosis/remediation stage
    outputs into the flattened row shape used by incident_results."""

    detection = agent_response.get("detection") or {}
    diagnosis = agent_response.get("diagnosis") or {}
    remediation = agent_response.get("remediation") or {}
    remediation_metadata = remediation.get("metadata") or {}

    return {
        "job_id": detection.get("job_id") or issue_reference,
        "incident_type": _qualified_incident_type(detection),
        "table_name": detection.get("table_name"),
        "original_query": detection.get("query"),
        "detection_status": detection.get("status"),
        "diagnosis_status": diagnosis.get("diagnosis_status"),
        "remediation_status": remediation.get("status"),
        "severity": diagnosis.get("severity"),
        "confidence": diagnosis.get("confidence"),
        "action_category": diagnosis.get("action_category"),
        "incident_summary": detection.get("summary"),
        "diagnosed_root_cause": diagnosis.get("root_cause"),
        "remediation_recommendation": remediation.get("action_required"),
        "remediation_query": remediation_metadata.get("recommended_query"),
        "executed": remediation.get("executed"),
        "verification_required": remediation.get("verification_required"),
        "verification_result": remediation.get("verification_result"),
        "escalation_reason": diagnosis.get("escalation_reason"),
        "workflow_id": remediation.get("workflow_id"),
        "task_id": remediation.get("task_id"),
        "incident_evidence": _incident_evidence(detection),
    }


def store_result(
    issue_reference: Optional[str],
    agent_response: Dict[str, Any],
    project: Optional[str] = None,
) -> Dict[str, Any]:
    """Store the full raw agent response in the raw archive table, and the
    flattened detection/diagnosis/remediation fields in incident_results,
    both rows linked by the same record_id."""

    results_status = ensure_results_table(project)

    if not results_status.get("success"):
        return results_status

    raw_status = ensure_raw_results_table(project)

    if not raw_status.get("success"):
        return raw_status

    client = bigquery.Client(project=project) if project else bigquery.Client()

    record_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    flattened = _flatten_agent_response(issue_reference, agent_response)

    structured_row = {
        "record_id": record_id,
        "created_at": created_at,
        **flattened,
    }

    raw_row = {
        "record_id": record_id,
        "job_id": flattened["job_id"],
        "created_at": created_at,
        "raw_response": json.dumps(agent_response, default=str),
    }

    raw_errors = client.insert_rows_json(raw_status["table_id"], [raw_row])

    if raw_errors:
        return {"success": False, "error": "BIGQUERY_RAW_INSERT_FAILED", "message": str(raw_errors)}

    structured_errors = client.insert_rows_json(results_status["table_id"], [structured_row])

    if structured_errors:
        return {"success": False, "error": "BIGQUERY_INSERT_FAILED", "message": str(structured_errors)}

    return {
        "success": True,
        "record_id": record_id,
        "table_id": results_status["table_id"],
        "raw_table_id": raw_status["table_id"],
    }
