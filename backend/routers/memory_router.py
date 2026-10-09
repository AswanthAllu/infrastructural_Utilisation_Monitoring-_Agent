import json
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query

from tools.system_agent_pipeline import process_system_memory_metrics
from tools.metrics_fetcher import CURRENT_METRICS_API_URL, HISTORY_API_URL, load_configured_metrics, store_metrics_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["Memory / RAM Agent (Direct 3-Subagent Pipeline)"])

DEFAULT_METRICS_URL = CURRENT_METRICS_API_URL


@router.get("/analyze")
async def analyze_memory_latest_history(
):
    """
    Direct Memory Agent Endpoint:
    1. Calls http://20.15.164.79:8080/api/metrics to ingest live current memory data, plus 5 recordings from /api/history.
    2. Runs LLM-powered Detection -> Diagnosis -> Remediation on Memory data.
    3. Evaluates the highest threshold exceeded (50%, 70%, or 100%).
    4. Dispatches a single alert email via Nodemailer to sirivennelanarava@gmail.com with the highest limit details.
    5. Returns detection, root cause, and remediation.
    """
    try:
        result = process_system_memory_metrics(source=None)
        result["source_url"] = CURRENT_METRICS_API_URL
        result["source_file"] = None
        return result
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        logger.error(f"Memory Agent error: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Memory Agent failed to process telemetry: {str(exc)}",
        )
