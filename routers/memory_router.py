import json
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query

from tools.system_agent_pipeline import process_system_memory_metrics
from tools.metrics_fetcher import HISTORY_API_URL, load_configured_metrics, store_metrics_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["Memory / RAM Agent (Direct 3-Subagent Pipeline)"])

DEFAULT_HISTORY_URL = HISTORY_API_URL


@router.get("/analyze")
async def analyze_memory_latest_history(
):
    """
    Direct Memory Agent Endpoint:
    1. Calls http://20.15.164.79:8080/api/history to ingest the telemetry history.
    2. Extracts and segregates ONLY RAM/Memory data (used_gb, available_gb, total_gb, percent).
    3. Runs LLM-powered Detection -> Diagnosis -> Remediation on Memory data.
    4. Evaluates the highest threshold exceeded (50%, 70%, or 100%).
    5. Dispatches a single alert email via Nodemailer to sirivennelanarava@gmail.com with the highest limit details.
    6. Returns detection, root cause, and remediation.
    """
    try:
        url = HISTORY_API_URL
        try:
            raw_telemetry, data_source = load_configured_metrics(url)
            store_metrics_json(raw_telemetry)
        except Exception as exc:
            logger.error(f"Live fetch from {url} failed: {exc}")
            raise HTTPException(status_code=503, detail=f"Configured telemetry source is unavailable: {exc}") from exc

        result = process_system_memory_metrics(source=raw_telemetry)
        result["source_url"] = url
        result["source_file"] = None
        result["data_source"] = data_source
        return result
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        logger.error(f"Memory Agent error: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Memory Agent failed to process telemetry: {str(exc)}",
        )
