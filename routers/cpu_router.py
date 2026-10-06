import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query

from tools.system_agent_pipeline import process_system_cpu_metrics
from tools.metrics_fetcher import HISTORY_API_URL, fetch_metrics_history, get_latest_metrics_file, store_metrics_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cpu", tags=["CPU Agent (Direct 3-Subagent Pipeline)"])

DEFAULT_HISTORY_URL = HISTORY_API_URL
LOCAL_METRICS_FILE = Path(__file__).resolve().parent.parent / "logs" / "system_metrics_latest.json"


@router.get("/analyze")
async def analyze_cpu_latest_history(
    url: str = Query(DEFAULT_HISTORY_URL, description="History telemetry endpoint URL"),
    force_fetch: bool = Query(False, description="Fetch fresh data from the remote history endpoint"),
    use_local_file: bool = Query(True, description="Use logs/system_metrics_latest.json as the agent input"),
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
        raw_telemetry = None
        if use_local_file and LOCAL_METRICS_FILE.exists():
            raw_telemetry = json.loads(LOCAL_METRICS_FILE.read_text(encoding="utf-8-sig"))
        elif force_fetch:
            try:
                raw_telemetry = fetch_metrics_history(url)
                store_metrics_json(raw_telemetry)
            except Exception as exc:
                logger.warning(f"Live fetch from {url} failed: {exc}, checking local cache")

        if not raw_telemetry:
            latest = get_latest_metrics_file()
            if latest and latest.exists():
                raw_telemetry = json.loads(latest.read_text(encoding="utf-8-sig"))
            else:
                raw_telemetry = fetch_metrics_history(url)
                store_metrics_json(raw_telemetry)

        # Runs CPU Agent: CPU data segregation -> LLM decision -> single highest threshold email
        result = process_system_cpu_metrics(source=raw_telemetry)
        result["source_url"] = url
        result["source_file"] = str(LOCAL_METRICS_FILE) if use_local_file and LOCAL_METRICS_FILE.exists() else None
        return result
    except Exception as exc:
        logger.error(f"CPU Agent error: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"CPU Agent failed to process telemetry: {str(exc)}",
        )
