from pathlib import Path
from fastapi import APIRouter, HTTPException

from tools.metrics_fetcher import fetch_metrics_history, store_metrics_json, get_latest_metrics_file

router = APIRouter(prefix="/api/metrics", tags=["Metrics Ingestion & Storage"])


@router.post("/fetch")
@router.get("/fetch")
async def trigger_metrics_fetch():
    """
    Triggers fetching history from http://20.15.164.79:8080/api/history
    and stores it as a timestamped .json file in logs/ (e.g. logs/system_metrics_YYYYMMDD_HHMMSS.json)
    and updates logs/system_metrics_latest.json.
    """
    try:
        data = fetch_metrics_history()
        saved_file = store_metrics_json(data)
        return {
            "success": True,
            "message": "Successfully fetched and stored system metrics JSON",
            "saved_file": str(saved_file),
            "filename": saved_file.name,
            "records_count": len(data),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch metrics: {str(exc)}")


@router.get("/alerts")
async def get_email_alerts_log():
    """Returns recent threshold alert emails dispatched to vnarava@miraclesoft.com."""
    log_file = Path(__file__).resolve().parent.parent / "logs" / "email_alerts.log"
    if not log_file.exists():
        return {"alerts": []}
    
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    import json
    parsed = [json.loads(line) for line in lines if line.strip()]
    return {"total_alerts": len(parsed), "alerts": parsed[-20:]}
