import csv
import io
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path so 'config', 'schemas', etc. can always be resolved
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from config.settings import MODEL_NAME
except ModuleNotFoundError:
    MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.6-flash")

from google.adk.agents import Agent

INSTRUCTIONS_PATH = Path(__file__).parent / "instructions.md"
DISK_AGENT_INSTRUCTION = INSTRUCTIONS_PATH.read_text(encoding="utf-8")


def parse_and_classify_disk_logs(csv_text: str) -> Dict[str, Any]:
    """
    Parse BigQuery Disk and Storage logs CSV, detect unpartitioned full-table scans,
    diagnose excessive storage bytes read, and generate remediation actions.
    """
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    total_rows = 0
    healthy_count = 0
    incidents: List[Dict[str, Any]] = []
    csv_rows: List[List[str]] = []

    for row in reader:
        total_rows += 1
        job_id = row.get("job_id", f"disk_job_{total_rows}").strip()
        timestamp = row.get("timestamp", "").strip()
        table_name = row.get("table_name", "unknown_table").strip()
        
        try:
            bytes_processed = float(row.get("total_bytes_processed", 0))
            bytes_billed = float(row.get("total_bytes_billed", bytes_processed))
        except (ValueError, TypeError):
            continue

        is_partitioned = str(row.get("is_partitioned", "false")).lower() in ["true", "1", "yes"]
        partition_col = row.get("partition_column", "date_col").strip()

        # Healthy: low scan bytes (< 1 GB)
        if bytes_processed < 1_000_000_000:
            healthy_count += 1
            continue

        severity = "CRITICAL" if bytes_processed >= 10_000_000_000_000 else "HIGH"
        detected_issue = (
            f"Query scanned {bytes_processed / (1024**3):.2f} GB without efficient partition pruning "
            f"on table {table_name}."
        )
        recommended_action = (
            f"Add WHERE clause filter on partition column `{partition_col}` and cluster on "
            f"high-cardinality join/filter keys."
        )
        preventive_guardrail = (
            f"Enable require_partition_filter = TRUE on `{table_name}` and set maximum_bytes_billed."
        )

        incident = {
            "job_id": job_id,
            "incident_type": "MISSING_PARTITION_FILTER",
            "table_name": table_name,
            "severity": severity,
            "detection": {
                "detected": True,
                "incident_type": "MISSING_PARTITION_FILTER",
                "status": "DETECTED",
                "severity": severity,
                "confidence": 0.95,
                "summary": f"Table scan of {bytes_processed / (1024**3):.2f} GB detected on {table_name}.",
                "evidence": {
                    "timestamp": timestamp,
                    "table_name": table_name,
                    "total_bytes_processed": bytes_processed,
                    "is_partitioned": is_partitioned,
                    "partition_column": partition_col,
                },
                "reasons": [f"Unpruned table scan exceeding storage budget: {bytes_processed:,.0f} bytes."],
                "recommended_next_step": "DIAGNOSIS",
            },
            "diagnosis": {
                "incident_type": "MISSING_PARTITION_FILTER",
                "diagnosis_status": "CONFIRMED",
                "root_cause": detected_issue,
                "explanation": (
                    f"Full table scan read {bytes_processed:,.0f} bytes directly from disk storage because "
                    f"the partition filter was absent or unusable."
                ),
                "confidence": 0.95,
                "severity": severity,
                "action_category": "RECOMMENDATION_ONLY",
                "recommended_action": recommended_action,
                "investigation_evidence": {"total_bytes_processed": bytes_processed},
                "safety_notes": ["No SQL was executed.", "No BigQuery resources were modified."],
                "escalation_required": (severity == "CRITICAL"),
                "escalation_reason": "Extreme disk scan volume" if severity == "CRITICAL" else None,
            },
            "remediation": {
                "action_category": "RECOMMENDATION_ONLY",
                "status": "REMEDIATION_DRAFTED",
                "action_taken": "A partition pruning and storage optimization recommendation was prepared.",
                "action_required": recommended_action,
                "preventive_guardrail": preventive_guardrail,
                "executed": False,
                "verification_required": True,
                "safety_notes": ["No SQL was executed.", "No BigQuery resources were modified."],
                "metadata": {
                    "incident_type": "MISSING_PARTITION_FILTER",
                    "job_id": job_id,
                    "table_name": table_name,
                    "detected_issue": detected_issue,
                    "recommended_action": recommended_action,
                    "preventive_guardrail": preventive_guardrail,
                },
            },
        }
        incidents.append(incident)
        csv_rows.append([job_id, timestamp, severity, str(bytes_processed), f'"{detected_issue}"', f'"{recommended_action}"', f'"{preventive_guardrail}"'])

    csv_header = "job_id,timestamp,severity,total_bytes_processed,detected_issue,recommended_action,preventive_guardrail\n"
    csv_body = "\n".join(",".join(r) for r in csv_rows)

    return {
        "success": True,
        "metric_type": "BQ_DISK_USAGE",
        "total_rows_processed": total_rows,
        "healthy_queries_count": healthy_count,
        "negative_incidents_count": len(incidents),
        "incidents": incidents,
        "disk_remediation_actions_csv": csv_header + (csv_body + "\n" if csv_body else ""),
    }


disk_agent = Agent(
    name="disk_agent",
    model=MODEL_NAME,
    description=(
        "Specialized BigQuery Storage and Disk Agent that analyzes disk and storage logs, "
        "detects unpartitioned and inefficient table scans, diagnoses storage I/O bottlenecks, "
        "and recommends partition pruning and clustering remediations."
    ),
    instruction=DISK_AGENT_INSTRUCTION,
    tools=[parse_and_classify_disk_logs],
)

root_agent = disk_agent

__all__ = ["disk_agent", "root_agent", "parse_and_classify_disk_logs"]

