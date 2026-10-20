import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tools.metrics_fetcher import fetch_metrics_history, store_metrics_json, get_latest_metrics_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/metrics", tags=["Metrics Ingestion & Storage"])


class ThresholdRuleCreate(BaseModel):
    resource: str = Field(..., description="Target resource: CPU, RAM, Disk, or ALL")
    threshold_percent: int = Field(..., ge=1, le=100, description="Threshold percentage (1-100)")
    severity: str = Field("HIGH", description="Severity: LOW, MEDIUM, HIGH, CRITICAL")
    recipient: str = Field("", description="Optional custom recipient email override")
    enabled: bool = Field(True, description="Whether rule is active")


class ThresholdRuleUpdate(BaseModel):
    resource: Optional[str] = None
    threshold_percent: Optional[int] = Field(None, ge=1, le=100)
    severity: Optional[str] = None
    recipient: Optional[str] = None
    enabled: Optional[bool] = None


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
    """Returns recent threshold alert emails in descending order (latest first) with dynamic filter thresholds."""
    try:
        from services.alert_db import get_all_alerts, get_alerts_count, get_distinct_thresholds
        total_count = get_alerts_count()
        alerts = get_all_alerts(limit=100)
        filter_thresholds = get_distinct_thresholds()
        return {
            "total_alerts": total_count,
            "alerts": alerts,
            "filter_thresholds": filter_thresholds,
        }
    except Exception as exc:
        logger.error(f"Error reading alerts from database: {exc}")
        log_file = Path(__file__).resolve().parent.parent / "logs" / "email_alerts.log"
        if not log_file.exists():
            return {"total_alerts": 0, "alerts": [], "filter_thresholds": [70, 90, 100]}
        
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        import json
        parsed = []
        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
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
            except Exception:
                pass
        # Latest first
        parsed.reverse()
        return {"total_alerts": len(parsed), "alerts": parsed[:100], "filter_thresholds": [70, 90, 100]}


@router.post("/alerts/clear")
@router.delete("/alerts")
async def clear_email_alerts_log():
    """Clear the persisted alert audit log without changing alert dispatching."""
    log_file = Path(__file__).resolve().parent.parent / "logs" / "email_alerts.log"
    try:
        from services.alert_db import clear_alerts
        clear_alerts()
        if log_file.exists():
            log_file.write_text("", encoding="utf-8")
        return {"success": True, "total_alerts": 0, "alerts": []}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to clear email alerts: {exc}")


# ---------------------------------------------------------------------------
# Threshold Alert Rules Management Endpoints
# ---------------------------------------------------------------------------

@router.get("/thresholds")
async def list_threshold_rules():
    """Returns all configured threshold alert rules and available distinct threshold values."""
    try:
        from services.alert_db import get_threshold_rules, get_distinct_thresholds
        rules = get_threshold_rules()
        distinct_thresholds = get_distinct_thresholds()
        return {
            "success": True,
            "rules": rules,
            "distinct_thresholds": distinct_thresholds,
        }
    except Exception as exc:
        logger.error(f"Failed to load threshold rules: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to load threshold rules: {exc}")


@router.post("/thresholds")
async def add_threshold_rule(payload: ThresholdRuleCreate):
    """Creates a new threshold alert rule configured from the UI."""
    try:
        from services.alert_db import create_threshold_rule, get_distinct_thresholds
        created = create_threshold_rule(
            resource=payload.resource,
            threshold_percent=payload.threshold_percent,
            severity=payload.severity,
            recipient=payload.recipient,
            enabled=1 if payload.enabled else 0,
        )
        if not created:
            raise HTTPException(status_code=400, detail="Failed to create threshold rule")
        return {
            "success": True,
            "message": f"Successfully created {payload.resource} {payload.threshold_percent}% threshold rule",
            "rule": created,
            "distinct_thresholds": get_distinct_thresholds(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to create threshold rule: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/thresholds/{rule_id}")
async def edit_threshold_rule(rule_id: int, payload: ThresholdRuleUpdate):
    """Updates an existing threshold rule."""
    try:
        from services.alert_db import update_threshold_rule, get_distinct_thresholds
        ok = update_threshold_rule(
            rule_id=rule_id,
            resource=payload.resource,
            threshold_percent=payload.threshold_percent,
            severity=payload.severity,
            recipient=payload.recipient,
            enabled=payload.enabled,
        )
        if not ok:
            raise HTTPException(status_code=404, detail="Threshold rule not found or could not be updated")
        return {
            "success": True,
            "message": f"Updated threshold rule #{rule_id}",
            "distinct_thresholds": get_distinct_thresholds(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to update threshold rule: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/thresholds/{rule_id}")
async def remove_threshold_rule(rule_id: int):
    """Deletes a threshold rule by ID."""
    try:
        from services.alert_db import delete_threshold_rule, get_distinct_thresholds
        ok = delete_threshold_rule(rule_id=rule_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Threshold rule not found")
        return {
            "success": True,
            "message": f"Deleted threshold rule #{rule_id}",
            "distinct_thresholds": get_distinct_thresholds(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to delete threshold rule: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/thresholds/{rule_id}/toggle")
async def toggle_rule_enabled(rule_id: int):
    """Toggles active/inactive state of a threshold rule."""
    try:
        from services.alert_db import toggle_threshold_rule, get_distinct_thresholds
        ok = toggle_threshold_rule(rule_id=rule_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Threshold rule not found")
        return {
            "success": True,
            "message": f"Toggled threshold rule #{rule_id}",
            "distinct_thresholds": get_distinct_thresholds(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to toggle threshold rule: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
