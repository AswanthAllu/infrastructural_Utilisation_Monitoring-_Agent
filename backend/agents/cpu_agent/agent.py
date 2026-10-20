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
CPU_AGENT_INSTRUCTION = INSTRUCTIONS_PATH.read_text(encoding="utf-8") if INSTRUCTIONS_PATH.exists() else "Autonomous CPU Agent"
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")


def analyze_cpu_metrics(
    cpu_data: Optional[Union[str, Path, List[Dict[str, Any]], Dict[str, Any]]] = None,
    recipient_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Autonomous VM-Level CPU Utilization Monitoring Tool:
    1. Ingests host-level telemetry (/api/metrics, /api/history): total CPU %, per-core utilization, uptime.
    2. Gathers active process consumers (/api/processes): PID, process name, CPU %, memory %, thread count.
    3. Correlates system service logs (/api/service-logs): systemd journal logs, service restart events.
    4. Evaluates operational threshold tiers (70%, 90%, 100%) and saturated core contention.
    5. Formulates AI-powered root-cause diagnosis and VM remediation actions (e.g. process termination, renice, service restart).
    """
    from tools.system_agent_pipeline import process_system_cpu_metrics
    return process_system_cpu_metrics(source=cpu_data, recipient_email=recipient_email)


def parse_and_classify_cpu_logs(
    data: Union[str, Dict[str, Any], List[Dict[str, Any]]],
    recipient_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Entrypoint for CPU telemetry and logs ingestion.
    Parses VM telemetry data (JSON or CSV format) and delegates to the VM CPU pipeline.
    """
    # If passed as string, check if it's CSV
    if isinstance(data, str) and not data.strip().startswith(("[", "{")):
        try:
            reader = csv.DictReader(io.StringIO(data.strip()))
            rows = list(reader)
            if rows:
                converted_items = []
                for row in rows:
                    cpu_total = float(row.get("total", row.get("cpu_percent", row.get("avg_slots_utilized", 0))) or 0)
                    converted_items.append({
                        "timestamp": row.get("timestamp", ""),
                        "hostname": row.get("hostname", row.get("project_id", "cpu-utilization-vm")),
                        "cpu": {
                            "total": cpu_total,
                            "cores": int(row.get("cores", 2) or 2),
                            "per_core": [cpu_total],
                        },
                        "uptime": row.get("uptime", ""),
                    })
                return analyze_cpu_metrics(converted_items, recipient_email=recipient_email)
        except Exception as exc:
            logger.warning(f"CSV parsing fallback encountered: {exc}")

    return analyze_cpu_metrics(data, recipient_email=recipient_email)


cpu_agent = Agent(
    name="cpu_agent",
    model=MODEL_NAME,
    description=(
        "Autonomous CPU Utilization Monitoring Agent that inspects VM host telemetry, "
        "monitors overall and per-core processor saturation, identifies high-CPU processes, "
        "correlates systemd service events, diagnoses root cause, and formulates remediation actions."
    ),
    instruction=CPU_AGENT_INSTRUCTION,
    tools=[analyze_cpu_metrics],
)

root_agent = cpu_agent

__all__ = ["cpu_agent", "root_agent", "analyze_cpu_metrics", "parse_and_classify_cpu_logs"]
