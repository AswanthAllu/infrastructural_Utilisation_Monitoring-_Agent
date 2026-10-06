import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.email_service import (
    DEFAULT_ALERT_EMAIL,
    evaluate_history_highest_threshold,
    get_highest_crossed_threshold,
    send_threshold_alert_email,
)
from services.llm_agent_service import call_llm_agent
from tools.cpu_preprocessor import (
    generate_all_cpu_remediation_plans,
    save_segregated_cpu_data,
    segregate_cpu_data,
)
from tools.metrics_fetcher import (
    extract_metric_series,
    fetch_current_metrics,
    get_latest_metrics_file,
)

logger = logging.getLogger(__name__)

CPU_INSTRUCTIONS_PATH = PROJECT_ROOT / "agents" / "cpu_agent" / "instructions.md"
DISK_INSTRUCTIONS_PATH = PROJECT_ROOT / "agents" / "disk_agent" / "instructions.md"
MEMORY_INSTRUCTIONS_PATH = PROJECT_ROOT / "agents" / "memory_agent" / "instructions.md"

CPU_INSTRUCTIONS = CPU_INSTRUCTIONS_PATH.read_text(encoding="utf-8") if CPU_INSTRUCTIONS_PATH.exists() else "Autonomous CPU Agent"
DISK_INSTRUCTIONS = DISK_INSTRUCTIONS_PATH.read_text(encoding="utf-8") if DISK_INSTRUCTIONS_PATH.exists() else "Autonomous Disk Agent"
MEMORY_INSTRUCTIONS = MEMORY_INSTRUCTIONS_PATH.read_text(encoding="utf-8") if MEMORY_INSTRUCTIONS_PATH.exists() else "Autonomous Memory Agent"


def _load_metrics_data(source: Optional[Union[str, Path, List[Dict[str, Any]]]] = None) -> List[Dict[str, Any]]:
    """Loads metrics list from in-memory data, a filepath, or fetches latest from logs/endpoint."""
    if isinstance(source, list):
        return source
    if isinstance(source, (str, Path)):
        p = Path(source)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8-sig"))
        elif isinstance(source, str) and source.strip().startswith("["):
            return json.loads(source)

    latest_file = get_latest_metrics_file()
    if latest_file and latest_file.exists():
        return json.loads(latest_file.read_text(encoding="utf-8-sig"))
    
    raise ValueError("No metrics data available from logs or remote endpoint.")


def process_system_cpu_metrics(
    source: Optional[Union[str, Path, List[Dict[str, Any]]]] = None,
    recipient_email: str = DEFAULT_ALERT_EMAIL,
) -> Dict[str, Any]:
    """
    Direct CPU Agent tool that:
    1. Loads telemetry and executes Python segregation script to extract ONLY CPU data.
    2. Invokes LLM (Gemini) to decide detection, diagnosis, and remediation.
    3. Considers the latest limit usage (from current metrics or latest snapshot) to send
       the alert email for the single highest crossed threshold (50%, 70%, or 100%) via Nodemailer,
       avoiding sending all 3 at once.
    4. Delivers all remediation plans in the API response.
    """
    raw_data = _load_metrics_data(source)

    # STEP 1: Python Preprocessing Script - Segregate CPU-only data
    segregated_cpu = segregate_cpu_data(raw_data)
    if not segregated_cpu:
        return {"success": False, "error": "No CPU records found in telemetry data"}

    try:
        save_segregated_cpu_data(segregated_cpu)
    except Exception as exc:
        logger.warning(f"Could not save segregated CPU metrics file: {exc}")

    # Telemetry aggregate stats
    total_samples = len(segregated_cpu)
    latest_rec = segregated_cpu[0]
    hostname = latest_rec.get("hostname", "cpu-utilization-vm")
    timestamp = latest_rec.get("timestamp", "")
    current_usage = latest_rec.get("usage_percent", 0.0)
    per_core = latest_rec.get("per_core", [])
    cores = latest_rec.get("cores", 1)
    usages = [r.get("usage_percent", 0.0) for r in segregated_cpu]
    peak_usage = max(usages) if usages else current_usage

    # Try fetching live snapshot from http://20.15.164.79:8080/api/metrics to verify current details if source is not provided
    live_usage = current_usage
    live_per_core = per_core
    if source is None:
        try:
            live_snapshot = fetch_current_metrics()
            if live_snapshot and "cpu" in live_snapshot:
                live_cpu = live_snapshot["cpu"]
                live_usage = float(live_cpu.get("total", current_usage))
                live_per_core = [float(c) for c in live_cpu.get("per_core", per_core)]
                timestamp = live_snapshot.get("timestamp", timestamp)
                hostname = live_snapshot.get("hostname", hostname)
        except Exception as exc:
            logger.debug(f"Could not fetch live snapshot from /api/metrics, using latest history entry: {exc}")

    # STEP 2: Autonomous LLM Agent Call (Decides detection, diagnosis, and remediation)
    llm_result = call_llm_agent(
        agent_name="cpu_agent",
        resource_type="CPU",
        metrics_payload=segregated_cpu[:15],  # provide recent historical window to LLM
        system_instructions=CPU_INSTRUCTIONS,
    )

    detection = llm_result.get("detection", {})
    diagnosis = llm_result.get("diagnosis", {})
    remediation = llm_result.get("remediation", {})
    remediation_plans = llm_result.get("remediation_plans", [])

    # Determine the single highest threshold exceeded across the utilization series
    # e.g., if history has 50% and 70% exceeded, highest_threshold is 70%
    highest_threshold = evaluate_history_highest_threshold(segregated_cpu, "usage_percent")
    live_th = get_highest_crossed_threshold(live_usage, live_per_core)
    if live_th and (highest_threshold is None or live_th > highest_threshold):
        highest_threshold = live_th

    detection.setdefault("subagent", "detection_agent")
    detection.setdefault("resource", "CPU")
    detection.setdefault("detected", highest_threshold is not None)
    detection.setdefault("crossed_thresholds", [th for th in [100, 70, 50] if highest_threshold and highest_threshold >= th])
    detection.setdefault("severity", "CRITICAL" if highest_threshold == 100 else ("HIGH" if highest_threshold == 70 else ("MEDIUM" if highest_threshold == 50 else "LOW")))

    diagnosis.setdefault("subagent", "diagnosis_agent")
    diagnosis.setdefault("severity", detection.get("severity"))
    diagnosis.setdefault("diagnosis_status", "CONFIRMED" if highest_threshold else "HEALTHY")

    remediation.setdefault("subagent", "remediation_agent")
    remediation.setdefault("status", "REMEDIATION_DRAFTED" if highest_threshold else "HEALTHY")

    # If LLM returned fewer plans, supplement with deterministic multi-incident plans
    if not remediation_plans:
        remediation_plans = generate_all_cpu_remediation_plans(segregated_cpu, only_problematic=True)

    # Keep the service associated with each telemetry spike visible in the response,
    # including when the LLM supplies the remediation plan.
    service_by_timestamp = {record.get("timestamp"): record.get("service_name", "unknown-service") for record in segregated_cpu}
    for plan in remediation_plans:
        plan.setdefault("service_name", service_by_timestamp.get(plan.get("timestamp"), latest_rec.get("service_name", "unknown-service")))

    # STEP 3: Single Highest Threshold Email Alert using Nodemailer
    # Suppose in history we have 50% and 70% threshold exceeded, send the email with 70% limit details
    email_alerts_dispatched = []

    if highest_threshold is not None:
        reported_cpu_usage = max(live_usage, peak_usage)
        alert_info = send_threshold_alert_email(
            resource_name="CPU",
            usage_percent=reported_cpu_usage,
            threshold=highest_threshold,
            hostname=hostname,
            timestamp=timestamp,
            details={
                "current_usage": f"{live_usage:.1f}%",
                "peak_usage": f"{peak_usage:.1f}%",
                "cores": cores,
                "per_core": live_per_core,
                "highest_threshold_crossed": highest_threshold,
                "root_cause": diagnosis.get("root_cause"),
                "llm_powered": llm_result.get("llm_powered", False),
            },
            remediation_summary=remediation.get("action_required"),
            recipient_email=recipient_email,
        )
        email_alerts_dispatched.append(alert_info)

    return {
        "success": True,
        "agent": "cpu_agent",
        "resource": "CPU",
        "hostname": hostname,
        "service_name": latest_rec.get("service_name", "unknown-service"),
        "records": segregated_cpu,
        "timestamp": timestamp,
        "peak_usage_percent": peak_usage,
        "current_usage_percent": live_usage,
        "highest_threshold_crossed": highest_threshold,
        "total_records_analyzed": total_samples,
        "problematic_records_count": len(remediation_plans),
        "remediation_plans": remediation_plans,
        "remediation_summary": remediation,
        "remediation": remediation,
        "detection": detection,
        "diagnosis": diagnosis,
        "email_alerts": email_alerts_dispatched,
        "llm_powered": llm_result.get("llm_powered", False),
        "model_used": llm_result.get("model_used"),
    }


def process_system_disk_metrics(
    source: Optional[Union[str, Path, List[Dict[str, Any]]]] = None,
    recipient_email: str = DEFAULT_ALERT_EMAIL,
) -> Dict[str, Any]:
    """
    Direct Disk Agent tool:
    1. Extracts ONLY Disk telemetry.
    2. Invokes LLM (Gemini) to autonomously decide detection, diagnosis, and remediation.
    3. Evaluates single highest crossed threshold (50%, 70%, 100%) and sends alert email via Nodemailer.
    """
    raw_data = _load_metrics_data(source)
    disk_records = extract_metric_series(raw_data, "disk")
    if not disk_records:
        return {"success": False, "error": "No Disk records found"}

    latest = disk_records[0]
    usage_percent = float(latest.get("usage_percent", 0.0))
    used_gb = float(latest.get("used_gb", 0.0))
    total_gb = float(latest.get("total_gb", 0.0))
    free_gb = float(latest.get("free_gb", 0.0))
    hostname = latest.get("hostname", "unknown-host")
    timestamp = latest.get("timestamp", "")

    # Live check from /api/metrics if available and source is None
    if source is None:
        try:
            live_snapshot = fetch_current_metrics()
            if live_snapshot and "disk" in live_snapshot:
                ldisk = live_snapshot["disk"]
                usage_percent = float(ldisk.get("percent", usage_percent))
                used_gb = float(ldisk.get("used_gb", used_gb))
                total_gb = float(ldisk.get("total_gb", total_gb))
                free_gb = float(ldisk.get("free_gb", free_gb))
                timestamp = live_snapshot.get("timestamp", timestamp)
        except Exception:
            pass

    # LLM decision
    llm_result = call_llm_agent(
        agent_name="disk_agent",
        resource_type="Disk",
        metrics_payload=disk_records[:10],
        system_instructions=DISK_INSTRUCTIONS,
    )

    detection = llm_result.get("detection", {})
    diagnosis = llm_result.get("diagnosis", {})
    remediation = llm_result.get("remediation", {})

    disk_usages = [float(r.get("usage_percent", 0.0)) for r in disk_records]
    peak_disk_usage = max(disk_usages) if disk_usages else usage_percent
    highest_threshold = evaluate_history_highest_threshold(disk_records, "usage_percent")
    live_th = get_highest_crossed_threshold(usage_percent)
    if live_th and (highest_threshold is None or live_th > highest_threshold):
        highest_threshold = live_th

    detection.setdefault("subagent", "detection_agent")
    detection.setdefault("resource", "Disk")
    detection.setdefault("detected", highest_threshold is not None)
    detection.setdefault("crossed_thresholds", [th for th in [100, 70, 50] if highest_threshold and highest_threshold >= th])
    detection.setdefault("severity", "CRITICAL" if highest_threshold == 100 else ("HIGH" if highest_threshold == 70 else ("MEDIUM" if highest_threshold == 50 else "LOW")))

    diagnosis.setdefault("subagent", "diagnosis_agent")
    diagnosis.setdefault("severity", detection.get("severity"))
    diagnosis.setdefault("diagnosis_status", "CONFIRMED" if highest_threshold else "HEALTHY")

    remediation.setdefault("subagent", "remediation_agent")
    remediation.setdefault("status", "REMEDIATION_DRAFTED" if highest_threshold else "HEALTHY")

    email_alerts = []
    if highest_threshold is not None:
        reported_disk_usage = max(usage_percent, peak_disk_usage)
        email_alerts.append(send_threshold_alert_email(
            resource_name="Disk",
            usage_percent=reported_disk_usage,
            threshold=highest_threshold,
            hostname=hostname,
            timestamp=timestamp,
            details={"used_gb": used_gb, "total_gb": total_gb, "free_gb": free_gb, "peak_usage": f"{peak_disk_usage:.1f}%"},
            remediation_summary=remediation.get("action_required"),
            recipient_email=recipient_email,
        ))

    return {
        "success": True,
        "agent": "disk_agent",
        "resource": "Disk",
        "hostname": hostname,
        "total_records_analyzed": len(disk_records),
        "records": disk_records,
        "usage_percent": usage_percent,
        "peak_usage_percent": peak_disk_usage,
        "current_usage_percent": usage_percent,
        "highest_threshold_crossed": highest_threshold,
        "remediation_plans": [{
            "plan_id": "REMED-DISK-001",
            "service_name": latest.get("service_name", "unknown-service"),
            "severity": remediation.get("severity", detection.get("severity", "LOW")),
            "root_cause": diagnosis.get("root_cause"),
            "action_required": remediation.get("action_required") or diagnosis.get("recommended_action"),
        }],
        "detection": detection,
        "diagnosis": diagnosis,
        "remediation": remediation,
        "email_alerts": email_alerts,
        "llm_powered": llm_result.get("llm_powered", False),
        "model_used": llm_result.get("model_used"),
    }


def process_system_memory_metrics(
    source: Optional[Union[str, Path, List[Dict[str, Any]]]] = None,
    recipient_email: str = DEFAULT_ALERT_EMAIL,
) -> Dict[str, Any]:
    """
    Direct Memory Agent tool:
    1. Extracts ONLY RAM/Memory telemetry.
    2. Invokes LLM (Gemini) to autonomously decide detection, diagnosis, and remediation.
    3. Evaluates single highest crossed threshold (50%, 70%, 100%) and sends alert email via Nodemailer.
    """
    raw_data = _load_metrics_data(source)
    ram_records = extract_metric_series(raw_data, "ram")
    if not ram_records:
        return {"success": False, "error": "No RAM records found"}

    latest = ram_records[0]
    usage_percent = float(latest.get("usage_percent", 0.0))
    used_gb = float(latest.get("used_gb", 0.0))
    total_gb = float(latest.get("total_gb", 0.0))
    available_gb = float(latest.get("available_gb", 0.0))
    hostname = latest.get("hostname", "unknown-host")
    timestamp = latest.get("timestamp", "")

    # Live check from /api/metrics if available and source is None
    if source is None:
        try:
            live_snapshot = fetch_current_metrics()
            if live_snapshot and "ram" in live_snapshot:
                lram = live_snapshot["ram"]
                usage_percent = float(lram.get("percent", usage_percent))
                used_gb = float(lram.get("used_gb", used_gb))
                total_gb = float(lram.get("total_gb", total_gb))
                available_gb = float(lram.get("available_gb", available_gb))
                timestamp = live_snapshot.get("timestamp", timestamp)
        except Exception:
            pass

    # LLM decision
    llm_result = call_llm_agent(
        agent_name="memory_agent",
        resource_type="RAM",
        metrics_payload=ram_records[:10],
        system_instructions=MEMORY_INSTRUCTIONS,
    )

    detection = llm_result.get("detection", {})
    diagnosis = llm_result.get("diagnosis", {})
    remediation = llm_result.get("remediation", {})
    ram_usages = [float(r.get("usage_percent", 0.0)) for r in ram_records]
    peak_ram_usage = max(ram_usages) if ram_usages else usage_percent
    highest_threshold = evaluate_history_highest_threshold(ram_records, "usage_percent")
    live_th = get_highest_crossed_threshold(usage_percent)
    if live_th and (highest_threshold is None or live_th > highest_threshold):
        highest_threshold = live_th

    detection.setdefault("subagent", "detection_agent")
    detection.setdefault("resource", "RAM")
    detection.setdefault("detected", highest_threshold is not None)
    detection.setdefault("crossed_thresholds", [th for th in [100, 70, 50] if highest_threshold and highest_threshold >= th])
    detection.setdefault("severity", "CRITICAL" if highest_threshold == 100 else ("HIGH" if highest_threshold == 70 else ("MEDIUM" if highest_threshold == 50 else "LOW")))

    diagnosis.setdefault("subagent", "diagnosis_agent")
    diagnosis.setdefault("severity", detection.get("severity"))
    diagnosis.setdefault("diagnosis_status", "CONFIRMED" if highest_threshold else "HEALTHY")

    remediation.setdefault("subagent", "remediation_agent")
    remediation.setdefault("status", "REMEDIATION_DRAFTED" if highest_threshold else "HEALTHY")

    email_alerts = []
    if highest_threshold is not None:
        reported_ram_usage = max(usage_percent, peak_ram_usage)
        email_alerts.append(send_threshold_alert_email(
            resource_name="RAM",
            usage_percent=reported_ram_usage,
            threshold=highest_threshold,
            hostname=hostname,
            timestamp=timestamp,
            details={"used_gb": used_gb, "total_gb": total_gb, "available_gb": available_gb, "peak_usage": f"{peak_ram_usage:.1f}%"},
            remediation_summary=remediation.get("action_required"),
            recipient_email=recipient_email,
        ))

    return {
        "success": True,
        "agent": "memory_agent",
        "resource": "RAM",
        "hostname": hostname,
        "total_records_analyzed": len(ram_records),
        "records": ram_records,
        "usage_percent": usage_percent,
        "peak_usage_percent": peak_ram_usage,
        "current_usage_percent": usage_percent,
        "highest_threshold_crossed": highest_threshold,
        "remediation_plans": [{
            "plan_id": "REMED-RAM-001",
            "service_name": latest.get("service_name", "unknown-service"),
            "severity": remediation.get("severity", detection.get("severity", "LOW")),
            "root_cause": diagnosis.get("root_cause"),
            "action_required": remediation.get("action_required") or diagnosis.get("recommended_action"),
        }],
        "detection": detection,
        "diagnosis": diagnosis,
        "remediation": remediation,
        "email_alerts": email_alerts,
        "llm_powered": llm_result.get("llm_powered", False),
        "model_used": llm_result.get("model_used"),
    }
