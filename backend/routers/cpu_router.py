import json
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Form, HTTPException, Query, Request

from tools.system_agent_pipeline import process_system_cpu_metrics
from tools.metrics_fetcher import HISTORY_API_URL, load_configured_metrics, store_metrics_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cpu", tags=["CPU Agent (Direct 3-Subagent Pipeline)"])

DEFAULT_HISTORY_URL = HISTORY_API_URL


@router.api_route("/analyze", methods=["GET", "POST"])
async def analyze_cpu_latest_history(
    request: Request,
    text: Optional[str] = Form(None),
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
        # POST text is supported for compatibility with the orchestrator-style
        # API. JSON telemetry is processed by the system pipeline; CSV input is
        # classified by the legacy BigQuery CPU agent.
        if text and text.strip():
            from agents.cpu_agent.agent import parse_and_classify_cpu_logs
            if not text.lstrip().startswith(("[", "{")):
                result = parse_and_classify_cpu_logs(text)
                result["designated_agent"] = "cpu_agent"
                result["routed_by"] = "cpu_agent"
                return result
            source = text
        else:
            source = None

        url = HISTORY_API_URL
        try:
            raw_telemetry, data_source = load_configured_metrics(url) if source is None else (source, "request body")
            if source is None:
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


@router.get("/history")
async def analyze_cpu_history(force_fetch: bool = Query(False)):
    """Backward-compatible alias for the direct CPU history analysis endpoint."""
    raw_telemetry, data_source = load_configured_metrics(HISTORY_API_URL)
    result = process_system_cpu_metrics(source=raw_telemetry)
    result["source_url"] = HISTORY_API_URL
    result["source_file"] = None
    result["data_source"] = data_source
    return result


@router.get("/segregated-data")
async def get_segregated_cpu_data():
    """Return the latest CPU-only records used by the CPU pipeline."""
    from tools.cpu_preprocessor import segregate_cpu_data

    raw_telemetry, data_source = load_configured_metrics(HISTORY_API_URL)
    records = segregate_cpu_data(raw_telemetry)
    return {
        "success": True,
        "data_source": data_source,
        "segregated_cpu_records": records,
    }
