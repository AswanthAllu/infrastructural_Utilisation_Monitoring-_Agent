import json
import logging
import os
import shutil
import smtplib
import ssl
import subprocess
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

logger = logging.getLogger(__name__)

DEFAULT_ALERT_EMAIL = os.getenv("DEFAULT_ALERT_EMAIL", "")
EMAIL_ALERTS_LOG = Path(__file__).resolve().parent.parent / "logs" / "email_alerts.log"
NODEMAILER_SCRIPT = Path(__file__).resolve().parent / "nodemailer_service.js"


def get_highest_crossed_threshold(
    usage_percent: float,
    per_core: Optional[List[float]] = None,
    resource_name: str = "CPU",
) -> Optional[int]:
    """
    Identifies the highest crossed threshold tier from configured rules.
    If database lookup fails, falls back to default tiers (70%, 90%, 100%).
    """
    try:
        from services.alert_db import get_highest_matching_threshold
        matched = get_highest_matching_threshold(resource_name, usage_percent, per_core)
        if matched is not None:
            return matched
    except Exception as exc:
        logger.warning(f"Failed dynamic threshold match, falling back to static tiers: {exc}")

    # Fallback to standard 70/90/100 logic
    is_saturated_core = per_core and any(c >= 99.0 for c in per_core)
    if usage_percent >= 99.0 or is_saturated_core:
        return 100
    elif usage_percent >= 90.0:
        return 90
    elif usage_percent >= 70.0:
        return 70
    return None


def evaluate_history_highest_threshold(
    records: List[Dict[str, Any]],
    resource_key: str = "usage_percent",
) -> Optional[int]:
    """
    Evaluates all historical records and determines the single highest threshold crossed.
    Suppose in history we have 70% and 90% threshold exceeded -> returns 90.
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


def _send_via_smtp(
    recipient: str,
    subject: str,
    html_content: str,
    text_content: str,
) -> Optional[Dict[str, Any]]:
    """
    Sends email directly using Python standard smtplib with TLS/SSL.
    Reads current credentials directly from the environment.
    """
    load_dotenv(ENV_PATH, override=True)
    smtp_enabled = (os.getenv("SMTP_ENABLED") or "false").lower() == "true"
    if not smtp_enabled:
        return None

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = (os.getenv("SMTP_USER") or "").strip()
    smtp_pass = (os.getenv("SMTP_PASS") or "").replace(" ", "").strip()
    smtp_from = (os.getenv("SMTP_FROM") or smtp_user or "system-monitor@agentecosystem.local").strip()

    if not (smtp_user and smtp_pass and recipient):
        logger.warning("SMTP missing required credentials (SMTP_USER, SMTP_PASS, or recipient)")
        return None

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = recipient

        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        if smtp_port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=15) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            context = ssl.create_default_context()
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

        logger.info(f"Threshold email successfully dispatched via SMTP to {recipient}")
        return {
            "status": "SENT",
            "provider": "smtp",
            "action_taken": f"Email sent successfully via SMTP to {recipient}",
        }
    except Exception as exc:
        logger.error(f"Python SMTP delivery failed: {exc}")
        return None


def send_threshold_alert_email(
    resource_name: str,
    usage_percent: float,
    threshold: int,
    hostname: str,
    timestamp: str,
    details: Dict[str, Any],
    remediation_summary: Optional[str] = None,
    recipient_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Dispatches a single threshold alert email to the recipient using Python native SMTP,
    falling back to Node.js Nodemailer or local audit-logging to logs/email_alerts.log.
    """
    # Reload environment to ensure freshly saved recipient / credentials are used
    load_dotenv(ENV_PATH, override=True)
    recipient_email = (recipient_email or os.getenv("DEFAULT_ALERT_EMAIL") or os.getenv("SMTP_USER", "")).strip()
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
        
        <p style="font-size: 0.85em; color: #777;">Notification delivered via Autonomous Multi-Agent Monitoring Ecosystem.</p>
      </body>
    </html>
    """
    text_content = f"Limit crossed {threshold}% {resource_name} usage on {hostname}. Usage: {usage_percent}%. Remediation: {remediation_summary}"

    from services.alert_db import insert_alert

    # 1. Primary: Native Python SMTP delivery
    smtp_res = _send_via_smtp(recipient_email, subject, html_content, text_content)
    if smtp_res and smtp_res.get("status") == "SENT":
        alert_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "recipient": recipient_email,
            "subject": subject,
            "resource": resource_name,
            "threshold": threshold,
            "usage_percent": usage_percent,
            "hostname": hostname,
            "status": "SENT",
            "provider": "smtp",
            "action_taken": f"Threshold {threshold}% alert email sent successfully via SMTP to {recipient_email}",
            "details": details,
        }
        EMAIL_ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(EMAIL_ALERTS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(alert_record) + "\n")
        try:
            insert_alert(alert_record)
        except Exception as db_err:
            logger.warning(f"Failed to record alert in SQLite DB: {db_err}")
        return alert_record

    # 2. Secondary: Node.js Nodemailer fallback (if configured)
    payload = {
        "to": recipient_email,
        "subject": subject,
        "resource": resource_name,
        "threshold": threshold,
        "usage_percent": usage_percent,
        "hostname": hostname,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "html": html_content,
        "text": text_content,
    }

    node_bin = shutil.which("node")
    if node_bin and NODEMAILER_SCRIPT.exists():
        try:
            import base64
            b64_arg = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
            proc = subprocess.run(
                [node_bin, str(NODEMAILER_SCRIPT), b64_arg],
                text=True,
                capture_output=True,
                timeout=20,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                try:
                    result = json.loads(proc.stdout.strip())
                    if result.get("status") == "SENT":
                        result["resource"] = resource_name
                        result["threshold"] = threshold
                        result["usage_percent"] = usage_percent
                        result["hostname"] = hostname
                        result["details"] = details
                        try:
                            insert_alert(result)
                        except Exception as db_err:
                            logger.warning(f"Failed to record Nodemailer alert in SQLite DB: {db_err}")
                        return result
                except json.JSONDecodeError:
                    pass
        except Exception as exc:
            logger.warning(f"Nodemailer fallback execution failed: {exc}")

    # 3. Fallback: Local audit log & database
    alert_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recipient": recipient_email,
        "subject": subject,
        "resource": resource_name,
        "threshold": threshold,
        "usage_percent": usage_percent,
        "hostname": hostname,
        "status": "RECORDED_LOCALLY",
        "provider": "local_fallback",
        "action_taken": f"Threshold {threshold}% alert recorded locally (SMTP dispatch failed or disabled) for {recipient_email}",
        "details": details,
    }

    EMAIL_ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(EMAIL_ALERTS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(alert_record) + "\n")

    try:
        insert_alert(alert_record)
    except Exception as db_err:
        logger.warning(f"Failed to record fallback alert in SQLite DB: {db_err}")

    return alert_record
