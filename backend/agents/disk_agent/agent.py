import csv
import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Ensure project root is in sys.path so 'config', 'schemas', 'tools', etc. can always be resolved
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google.adk.agents import Agent

logger = logging.getLogger(__name__)

INSTRUCTIONS_PATH = Path(__file__).parent / "instructions.md"
DISK_AGENT_INSTRUCTION = INSTRUCTIONS_PATH.read_text(encoding="utf-8") if INSTRUCTIONS_PATH.exists() else "Autonomous Disk Agent"
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")


def analyze_disk_metrics(
    disk_data: Optional[Union[str, Path, List[Dict[str, Any]], Dict[str, Any]]] = None,
    recipient_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Autonomous VM-Level Disk & Storage Monitoring Tool:
    1. Ingests host storage telemetry (/api/metrics, /api/history): used GB, free GB, total GB, disk percent.
    2. Identifies processes with notable disk I/O or storage footprint (/api/processes).
    3. Correlates system service logs (/api/service-logs): systemd journal storage, database, and logging events.
    4. Evaluates storage capacity threshold tiers (70%, 90%, 100%).
    5. Formulates AI-powered root-cause diagnosis and storage remediation actions (e.g., log rotation, cache purge, volume expansion).
    """
    from tools.system_agent_pipeline import process_system_disk_metrics
    return process_system_disk_metrics(source=disk_data, recipient_email=recipient_email)


def parse_and_classify_disk_logs(
    data: Union[str, Dict[str, Any], List[Dict[str, Any]]],
    recipient_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Entrypoint for Disk telemetry and logs ingestion.
    Parses VM storage telemetry (JSON or CSV format) and delegates to the VM Disk pipeline.
    """
    # If passed as string, check if it's CSV
    if isinstance(data, str) and not data.strip().startswith(("[", "{")):
        try:
            reader = csv.DictReader(io.StringIO(data.strip()))
            rows = list(reader)
            if rows:
                converted_items = []
                for row in rows:
                    used_gb = float(row.get("used_gb", row.get("total_bytes_processed", 0)) or 0)
                    total_gb = float(row.get("total_gb", 100) or 100)
                    if used_gb > total_gb and total_gb == 100:
                        # Value was in bytes
                        used_gb = round(used_gb / (1024 ** 3), 2)
                        total_gb = max(round(used_gb * 1.25, 2), 100)
                    free_gb = max(total_gb - used_gb, 0.0)
                    percent = round((used_gb / total_gb) * 100, 1) if total_gb > 0 else 0.0

                    converted_items.append({
                        "timestamp": row.get("timestamp", ""),
                        "hostname": row.get("hostname", "cpu-utilization-vm"),
                        "disk": {
                            "percent": percent,
                            "used_gb": used_gb,
                            "free_gb": free_gb,
                            "total_gb": total_gb,
                        },
                        "uptime": row.get("uptime", ""),
                    })
                return analyze_disk_metrics(converted_items, recipient_email=recipient_email)
        except Exception as exc:
            logger.warning(f"Disk CSV parsing fallback encountered: {exc}")

    return analyze_disk_metrics(data, recipient_email=recipient_email)


disk_agent = Agent(
    name="disk_agent",
    model=MODEL_NAME,
    description=(
        "Autonomous Disk Utilization & Storage Reliability Agent that inspects VM storage capacity, "
        "monitors disk volume usage (used/free/total GB), tracks process I/O consumption, "
        "correlates systemd journal logs, diagnoses storage exhaustion, and formulates remediation actions."
    ),
    instruction=DISK_AGENT_INSTRUCTION,
    tools=[analyze_disk_metrics],
)

root_agent = disk_agent

__all__ = ["disk_agent", "root_agent", "analyze_disk_metrics", "parse_and_classify_disk_logs"]
