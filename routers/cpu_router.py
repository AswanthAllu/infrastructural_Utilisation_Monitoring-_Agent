import json
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query

from tools.system_agent_pipeline import process_system_cpu_metrics
from tools.metrics_fetcher import HISTORY_API_URL, load_configured_metrics, store_metrics_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cpu", tags=["CPU Agent (Direct 3-Subagent Pipeline)"])

DEFAULT_HISTORY_URL = HISTORY_API_URL


@router.get("/analyze")
async def analyze_cpu_latest_history(
):
    """
    Direct CPU Agent Endpoint:
    1. Calls http://20.15.164.79:8080/api/history to ingest the telemetry history.
    2. Python preprocessing script extracts and segregates ONLY CPU data (stripping disk and ram).
    3. Runs LLM-powered Detection -> Diagnosis -> Remediation on CPU data.
    4. Evaluates the highest threshold exceeded (e.g., if 50% and 70% are exceeded, sends the 70% limit alert).
    5. Dispatches a single alert email via Nodemailer to sirivennelanarava@gmail.com with the highest limit details.
    6. Returns detection, root cause, remediation, and all individual remediation plans.
    """
    try:
        url = HISTORY_API_URL
        try:
            raw_telemetry, data_source = load_configured_metrics(url)
            store_metrics_json(raw_telemetry)
        except Exception as exc:
            logger.error(f"Live fetch from {url} failed: {exc}")
            raise HTTPException(status_code=503, detail=f"Configured telemetry source is unavailable: {exc}") from exc

        # Runs CPU Agent: CPU data segregation -> LLM decision -> single highest threshold email
        result = process_system_cpu_metrics(source=raw_telemetry)
        result["source_url"] = url
        result["source_file"] = None
        result["data_source"] = data_source
        return result
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        logger.error(f"CPU Agent error: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"CPU Agent failed to process telemetry: {str(exc)}",
        )
