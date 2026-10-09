import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger(__name__)

DEFAULT_ALERT_EMAIL = os.getenv("DEFAULT_ALERT_EMAIL", "")
EMAIL_ALERTS_LOG = Path(__file__).resolve().parent.parent / "logs" / "email_alerts.log"
NODEMAILER_SCRIPT = Path(__file__).resolve().parent / "nodemailer_service.js"


def get_highest_crossed_threshold(
    usage_percent: float,
    per_core: Optional[List[float]] = None,
) -> Optional[int]:
    """
    Identifies ONLY the highest/latest crossed threshold tier (50%, 70%, or 100%)
    instead of triggering all three simultaneously.
    - If 100% total or any core at 100% -> returns 100
    - If >= 70% and < 99% -> returns 70
    - If >= 50% and < 70% -> returns 50
    - Else None
    """
    is_saturated_core = per_core and any(c >= 99.0 for c in per_core)
    if usage_percent >= 99.0 or is_saturated_core:
        return 100
    elif usage_percent >= 70.0:
        return 70
    elif usage_percent >= 50.0:
        return 50
    return None


def evaluate_history_highest_threshold(
    records: List[Dict[str, Any]],
    resource_key: str = "usage_percent",
) -> Optional[int]:
    """
    Evaluates all historical records and determines the single highest threshold crossed.
    Suppose in history we have 50% and 70% threshold exceeded -> returns 70.
    If 100% is exceeded -> returns 100.
    """
    highest = None
    for r in records:
        val = float(r.get(resource_key, 0.0))
        per_core = r.get("per_core")
        th = get_highest_crossed_threshold(val, per_core)
        if th is not None:
            if highest is None or th > highest:
                highest = th
    return highest


def check_resource_thresholds(
    usage_percent: float,
    resource_name: str = "CPU",
    per_core: Optional[List[float]] = None,
) -> List[int]:
    """
    Backward-compatible helper returning crossed tiers.
    """
    highest = get_highest_crossed_threshold(usage_percent, per_core)
    return [highest] if highest is not None else []


def send_threshold_alert_email(
    resource_name: str,
    usage_percent: float,
    threshold: int,
    hostname: str,
    timestamp: str,
    details: Dict[str, Any],
    remediation_summary: Optional[str] = None,
    recipient_email: str = DEFAULT_ALERT_EMAIL,
) -> Dict[str, Any]:
    """
    Dispatches a single threshold alert email to the recipient using Nodemailer (via Node.js)
    with local audit-logging fallback to logs/email_alerts.log.
    """
    subject = f"Limit crossed {threshold}% {resource_name} usage"
    
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 15px; border-radius: 5px;">
          <h2 style="color: #721c24; margin-top: 0;">⚠️ System Resource Alert: {subject}</h2>
          <p><strong>Host:</strong> {hostname}</p>
          <p><strong>Timestamp:</strong> {timestamp}</p>
          <p><strong>Metric:</strong> {resource_name} Utilization</p>
          <p><strong>Observed Usage:</strong> <span style="font-size: 1.2em; font-weight: bold; color: #d9534f;">{usage_percent:.1f}%</span> (Threshold: {threshold}%)</p>
        </div>
        
        <h3>Metric Details:</h3>
        <pre style="background: #f4f4f4; padding: 10px; border-radius: 4px;">{json.dumps(details, indent=2)}</pre>
        
        <h3>Recommended Remediation Action:</h3>
        <p style="background: #e2f0cb; padding: 10px; border-left: 4px solid #6b8e23;">
          {remediation_summary or "Investigate high utilization processes and allocate appropriate compute resources."}
        </p>
        
        <p style="font-size: 0.85em; color: #777;">Notification delivered via Nodemailer by Multi-Agent System Ecosystem.</p>
      </body>
    </html>
    """

    payload = {
        "to": recipient_email,
        "subject": subject,
        "resource": resource_name,
        "threshold": threshold,
        "usage_percent": usage_percent,
        "hostname": hostname,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "html": html_content,
        "text": f"Limit crossed {threshold}% {resource_name} usage on {hostname}. Usage: {usage_percent}%. Remediation: {remediation_summary}",
    }

    # Attempt execution via Node.js Nodemailer service
    node_bin = shutil.which("node")
    if node_bin and NODEMAILER_SCRIPT.exists():
        try:
            import base64
            b64_arg = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
            proc = subprocess.run(
                [node_bin, str(NODEMAILER_SCRIPT), b64_arg],
                text=True,
                capture_output=True,
                timeout=5,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                try:
                    result = json.loads(proc.stdout.strip())
                    return result
                except json.JSONDecodeError:
                    pass
        except Exception as exc:
            logger.warning(f"Nodemailer execution failed, falling back to local file log: {exc}")

    # Fallback to local audit log
    alert_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recipient": recipient_email,
        "subject": subject,
        "resource": resource_name,
        "threshold": threshold,
        "usage_percent": usage_percent,
        "hostname": hostname,
        "status": "RECORDED_LOCALLY",
        "provider": "nodemailer_fallback",
        "action_taken": f"Threshold {threshold}% alert registered for {recipient_email}",
    }

    EMAIL_ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(EMAIL_ALERTS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(alert_record) + "\n")

    return alert_record
