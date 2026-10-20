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
MEMORY_AGENT_INSTRUCTION = INSTRUCTIONS_PATH.read_text(encoding="utf-8") if INSTRUCTIONS_PATH.exists() else "Autonomous Memory Agent"
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")


def analyze_memory_metrics(
    memory_data: Optional[Union[str, Path, List[Dict[str, Any]], Dict[str, Any]]] = None,
    recipient_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Autonomous VM-Level Memory & RAM Monitoring Tool:
    1. Ingests host memory telemetry (/api/metrics, /api/history): used GB, available GB, total GB, RAM percent.
    2. Gathers active process memory footprints (/api/processes): RSS MB, VMS MB, memory percent, PID, thread count.
    3. Correlates system service logs (/api/service-logs): systemd journal logs, service allocations, OOM warnings.
    4. Evaluates operational threshold tiers (70%, 90%, 100%) and memory leakage trends.
    5. Formulates AI-powered root-cause diagnosis and VM remediation actions (e.g., service restart, cache cleanup, process termination).
    """
    from tools.system_agent_pipeline import process_system_memory_metrics
    return process_system_memory_metrics(source=memory_data, recipient_email=recipient_email)


def parse_and_classify_memory_logs(
    data: Union[str, Dict[str, Any], List[Dict[str, Any]]],
    recipient_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Entrypoint for Memory telemetry and logs ingestion.
    Parses VM memory telemetry (JSON or CSV format) and delegates to the VM Memory pipeline.
    """
    # If passed as string, check if it's CSV
    if isinstance(data, str) and not data.strip().startswith(("[", "{")):
        try:
            reader = csv.DictReader(io.StringIO(data.strip()))
            rows = list(reader)
            if rows:
                converted_items = []
                for row in rows:
                    used_gb = float(row.get("used_gb", row.get("memory_used_gb", 0)) or 0)
                    total_gb = float(row.get("total_gb", row.get("memory_total_gb", 16)) or 16)
                    available_gb = float(row.get("available_gb", row.get("free_gb", max(total_gb - used_gb, 0.0))) or 0)
                    percent = float(row.get("percent", row.get("ram_percent", (used_gb / total_gb * 100) if total_gb > 0 else 0)) or 0)

                    converted_items.append({
                        "timestamp": row.get("timestamp", ""),
                        "hostname": row.get("hostname", "cpu-utilization-vm"),
                        "ram": {
                            "percent": percent,
                            "used_gb": used_gb,
                            "available_gb": available_gb,
                            "total_gb": total_gb,
                        },
                        "uptime": row.get("uptime", ""),
                    })
                return analyze_memory_metrics(converted_items, recipient_email=recipient_email)
        except Exception as exc:
            logger.warning(f"Memory CSV parsing fallback encountered: {exc}")

    return analyze_memory_metrics(data, recipient_email=recipient_email)


memory_agent = Agent(
    name="memory_agent",
    model=MODEL_NAME,
    description=(
        "Autonomous Memory & RAM Reliability Agent that inspects VM memory consumption, "
        "monitors RAM allocation (used/available/total GB), tracks process RSS footprints and thread counts, "
        "correlates systemd journal logs, diagnoses OOM risks and memory leaks, and formulates remediation plans."
    ),
    instruction=MEMORY_AGENT_INSTRUCTION,
    tools=[analyze_memory_metrics],
)

root_agent = memory_agent

__all__ = ["memory_agent", "root_agent", "analyze_memory_metrics", "parse_and_classify_memory_logs"]
