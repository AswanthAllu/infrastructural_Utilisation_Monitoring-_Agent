"""
LLM Agent Service:
Directly invokes Gemini (using google.genai and GOOGLE_API_KEY) so that the LLM
autonomously decides detection, diagnosis, and remediation for CPU, Disk, and Memory agents.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Load environment variables from project root .env and tests/.env
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "tests" / ".env")

logger = logging.getLogger(__name__)

API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")

_genai_client = None


def get_genai_client():
    global _genai_client
    if _genai_client is None:
        try:
            from google import genai
            api_key = os.getenv("GOOGLE_API_KEY")
            if api_key:
                _genai_client = genai.Client(api_key=api_key)
            else:
                _genai_client = genai.Client()
        except Exception as exc:
            logger.warning(f"Could not initialize google.genai Client: {exc}")
            _genai_client = None
    return _genai_client


def _clean_json_markdown(text: str) -> str:
    """Removes ```json and ``` code fence markers from model output."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def call_llm_agent(
    agent_name: str,
    resource_type: str,
    metrics_payload: Any,
    system_instructions: str,
) -> Dict[str, Any]:
    """
    Invokes the LLM (Gemini) with the agent's instructions and segregated telemetry.
    The LLM autonomously decides the detection, root cause diagnosis, and remediation plan.
    """
    client = get_genai_client()
    prompt = f"""
You are the autonomous {agent_name} in an enterprise reliability engineering ecosystem.
Resource under investigation: {resource_type}

AGENT ROLE & INSTRUCTIONS:
{system_instructions}

SEGREATED METRIC TELEMETRY DATA (non-{resource_type} metrics have already been stripped):
{json.dumps(metrics_payload, indent=2)}

TASK:
Analyze the provided telemetry thoroughly. Do NOT use canned or generic responses.
Generate an accurate, technical assessment based on the exact numbers observed.
If there are multiple problematic records / spikes, formulate an individualized remediation plan
for each distinct spike.

Respond ONLY with a valid JSON object matching this structure:
{{
  "agent": "{agent_name}",
  "resource": "{resource_type}",
  "detection": {{
    "detected": true,
    "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
    "highest_threshold_crossed": 100 | 70 | 50 | null,
    "summary": "Concise summary of what was detected"
  }},
  "diagnosis": {{
    "diagnosis_status": "CONFIRMED" | "HEALTHY",
    "root_cause": "Specific technical root cause based on the metrics",
    "explanation": "Detailed technical explanation of the issue"
  }},
  "remediation": {{
    "action_required": "Concrete actionable steps to mitigate the issue",
    "preventive_guardrail": "Long-term architectural guardrail to prevent recurrence"
  }},
       "remediation_plans": [
     {{
       "plan_id": "REMED-{resource_type.upper()}-001",
       "service_name": "Service responsible for this specific spike",
       "timestamp": "Timestamp of the spike/record",
      "severity": "CRITICAL" | "HIGH" | "MEDIUM",
      "root_cause": "Root cause for this specific spike",
      "action_required": "Specific action for this record",
      "preventive_guardrail": "Guardrail"
    }}
  ]
}}
"""

    if client:
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )
            if response and response.text:
                cleaned_text = _clean_json_markdown(response.text)
                parsed_json = json.loads(cleaned_text)
                parsed_json["llm_powered"] = True
                parsed_json["model_used"] = MODEL_NAME
                return parsed_json
        except Exception as exc:
            logger.warning(f"LLM call with model {MODEL_NAME} failed: {exc}")

    # Graceful fallback if LLM is offline / quota exhausted
    logger.info(f"Generating structured response via local intelligence fallback for {agent_name}")
    return _generate_fallback_agent_response(agent_name, resource_type, metrics_payload)


def _generate_fallback_agent_response(
    agent_name: str,
    resource_type: str,
    metrics_payload: Any,
) -> Dict[str, Any]:
    """Fallback when external LLM API is unreachable."""
    peak = 0.0
    if isinstance(metrics_payload, list) and metrics_payload:
        peak = max([float(m.get("usage_percent", m.get("total", 0.0))) for m in metrics_payload if isinstance(m, dict)] or [0.0])
    elif isinstance(metrics_payload, dict):
        peak = float(metrics_payload.get("usage_percent", metrics_payload.get("total", metrics_payload.get("percent", 0.0))))

    threshold = 100 if peak >= 99.0 else (70 if peak >= 70.0 else (50 if peak >= 50.0 else None))
    severity = "CRITICAL" if threshold == 100 else ("HIGH" if threshold == 70 else ("MEDIUM" if threshold == 50 else "LOW"))

    return {
        "agent": agent_name,
        "resource": resource_type,
        "llm_powered": False,
        "detection": {
            "subagent": "detection_agent",
            "detected": threshold is not None,
            "severity": severity,
            "highest_threshold_crossed": threshold,
            "summary": f"{resource_type} utilization reached {peak:.1f}%. Exceeded threshold tier: {threshold}%.",
        },
        "diagnosis": {
            "subagent": "diagnosis_agent",
            "diagnosis_status": "CONFIRMED" if threshold else "HEALTHY",
            "root_cause": f"Elevated {resource_type} resource demand ({peak:.1f}%).",
            "explanation": f"Host is operating at {peak:.1f}% capacity.",
        },
        "remediation": {
            "subagent": "remediation_agent",
            "action_required": f"Scale host {resource_type} resources immediately and inspect top consumers.",
            "preventive_guardrail": f"Configure proactive alerts at 70% for {resource_type}.",
        },
        "remediation_plans": [
            {
                "plan_id": f"REMED-{resource_type.upper()}-001",
                "severity": severity,
                "root_cause": f"{resource_type} reached {peak:.1f}%",
                "action_required": f"Scale host capacity or throttle non-critical tasks.",
                "preventive_guardrail": f"Set automated alert policies for {resource_type}.",
            }
        ] if threshold else [],
    }
