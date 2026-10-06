import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google.adk.agents import Agent

logger = logging.getLogger(__name__)

INSTRUCTIONS_PATH = Path(__file__).parent / "instructions.md"
MEMORY_AGENT_INSTRUCTION = INSTRUCTIONS_PATH.read_text(encoding="utf-8") if INSTRUCTIONS_PATH.exists() else "Autonomous Memory Agent"
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")


def analyze_memory_metrics(memory_data: Any) -> Dict[str, Any]:
    """
    Invokes the LLM to autonomously evaluate memory telemetry (used_gb, free_gb, total_gb, percent),
    determine threshold breaches, diagnose OOM / memory pressure, and formulate remediations.
    """
    from services.llm_agent_service import call_llm_agent
    return call_llm_agent(
        agent_name="memory_agent",
        resource_type="RAM",
        metrics_payload=memory_data,
        system_instructions=MEMORY_AGENT_INSTRUCTION,
    )


memory_agent = Agent(
    name="memory_agent",
    model=MODEL_NAME,
    description=(
        "Autonomous Memory & RAM Reliability Agent that analyzes host memory consumption, "
        "detects OOM danger and memory leakage, diagnoses root causes via LLM, and formulates remediation plans."
    ),
    instruction=MEMORY_AGENT_INSTRUCTION,
    tools=[analyze_memory_metrics],
)

__all__ = ["memory_agent", "analyze_memory_metrics"]
