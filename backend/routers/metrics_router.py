from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import re
from services.email_service import get_alert_email, set_alert_email

from tools.metrics_fetcher import fetch_metrics_history, store_metrics_json, get_latest_metrics_file

router = APIRouter(prefix="/api/metrics", tags=["Metrics Ingestion & Storage"])


class AlertRecipientUpdate(BaseModel):
    email: str


@router.get("/alert-recipient")
async def get_alert_recipient():
    return {"email": get_alert_email()}


@router.put("/alert-recipient")
async def update_alert_recipient(payload: AlertRecipientUpdate):
    email = payload.email.strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=422, detail="A valid email address is required")
    return {"success": True, "email": set_alert_email(email)}


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
    parsed = []
    for line in lines:
        if not line.strip():
            continue
        record = json.loads(line)
        # Normalize the audit-log field names to the frontend alert contract.
        # Keep the original fields as well for backwards compatibility.
        threshold = record.get("threshold_level", record.get("threshold", ""))
        usage = record.get("value", record.get("usage_percent", 0))
        parsed.append({
            **record,
            "metric_name": record.get("metric_name", record.get("resource", "Unknown")),
            "threshold_level": (
                str(threshold) if str(threshold).endswith("%") else f"{threshold}%"
            ),
            "value": usage,
            "status": record.get("status", "QUEUED"),
            "details": record.get("details", record.get("action_taken", "")),
        })
    return {"total_alerts": len(parsed), "alerts": parsed[-20:]}


@router.post("/alerts/clear")
@router.delete("/alerts")
async def clear_email_alerts_log():
    """Clear the persisted alert audit log without changing alert dispatching."""
    log_file = Path(__file__).resolve().parent.parent / "logs" / "email_alerts.log"
    try:
        if log_file.exists():
            log_file.write_text("", encoding="utf-8")
        return {"success": True, "total_alerts": 0, "alerts": []}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to clear email alerts: {exc}")
