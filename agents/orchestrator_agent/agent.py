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
    MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")

from google.adk.agents import Agent

from agents.cpu_agent.agent import cpu_agent, parse_and_classify_cpu_logs
from agents.disk_agent.agent import disk_agent, parse_and_classify_disk_logs
from agents.memory_agent.agent import memory_agent

INSTRUCTIONS_PATH = Path(__file__).parent / "instructions.md"
ORCHESTRATOR_INSTRUCTION = INSTRUCTIONS_PATH.read_text(encoding="utf-8") if INSTRUCTIONS_PATH.exists() else "Master Orchestrator Agent"


def route_incident_workload(input_data: Any) -> str:
    """
    Invokes the LLM to autonomously inspect the workload and classify which subagent
    should handle it: 'cpu_agent', 'disk_agent', or 'memory_agent'.
    """
    from services.llm_agent_service import get_genai_client
    client = get_genai_client()
    if client:
        try:
            prompt = f"""
You are the Master Orchestrator Router.
Classify this log/telemetry input and decide which specialized agent must process it:
- "cpu_agent" for CPU utilization, slots utilized, BigQuery CPU, compute contention, processor cores.
- "disk_agent" for disk usage, unpartitioned table scans, storage bytes, file systems.
- "memory_agent" for RAM, memory usage, heap, OOM risks, swap.

INPUT PREVIEW:
{str(input_data)[:800]}

Respond ONLY with one of: ["cpu_agent", "disk_agent", "memory_agent"]. Do not include extra text.
"""
            resp = client.models.generate_content(model=MODEL_NAME, contents=prompt)
            if resp and resp.text:
                cleaned = resp.text.strip().lower().replace('"', '').replace("'", "")
                if "disk" in cleaned:
                    return "disk_agent"
                if "memory" in cleaned or "ram" in cleaned:
                    return "memory_agent"
                if "cpu" in cleaned:
                    return "cpu_agent"
        except Exception:
            pass

    # Fallback heuristic if LLM is offline
    raw_str = str(input_data).lower()
    if any(k in raw_str for k in ["disk", "storage", "partition", "bytes_processed", "bytes_billed"]):
        return "disk_agent"
    if any(k in raw_str for k in ["memory", "ram", "swap", "heap"]):
        return "memory_agent"
    return "cpu_agent"


def orchestrate_log_analysis(input_data: str, filename: Optional[str] = None) -> Dict[str, Any]:
    """
    Main orchestration function that uses LLM-driven routing to direct the workload
    to the designated agent (CPU, Disk, or Memory), executes end-to-end detection, diagnosis,
    and remediation, and returns the result.
    """
    from tools.system_agent_pipeline import (
        process_system_cpu_metrics,
        process_system_disk_metrics,
        process_system_memory_metrics,
    )

    routing_key = f"{filename or ''} {input_data[:500]}"
    designated_agent = route_incident_workload(routing_key)

    is_json = input_data.strip().startswith("[") or input_data.strip().startswith("{")

    if designated_agent == "disk_agent":
        if is_json:
            result = process_system_disk_metrics(source=input_data)
        else:
            result = parse_and_classify_disk_logs(input_data)
    elif designated_agent == "memory_agent":
        result = process_system_memory_metrics(source=input_data)
    else:
        if is_json:
            result = process_system_cpu_metrics(source=input_data)
        else:
            result = parse_and_classify_cpu_logs(input_data)

    result["routed_by"] = "orchestrator_agent_llm"
    result["designated_agent"] = designated_agent
    result["input_filename"] = filename

    return result


# Multi-agent orchestrator with CPU, Disk, and Memory subagents
orchestrator_agent = Agent(
    name="orchestrator_agent",
    model=MODEL_NAME,
    description=(
        "Master Orchestrator Agent that routes telemetry and log analysis tasks "
        "via LLM to specialized subagents: cpu_agent, disk_agent, or memory_agent."
    ),
    instruction=ORCHESTRATOR_INSTRUCTION,
    sub_agents=[cpu_agent, disk_agent, memory_agent],
    tools=[route_incident_workload, orchestrate_log_analysis],
)

__all__ = ["orchestrator_agent", "route_incident_workload", "orchestrate_log_analysis"]
