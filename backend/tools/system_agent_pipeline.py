import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.email_service import (
    DEFAULT_ALERT_EMAIL,
    evaluate_history_highest_threshold,
    get_alert_email,
    get_highest_crossed_threshold,
    send_threshold_alert_email,
)
from services.llm_agent_service import call_llm_agent
from tools.cpu_preprocessor import (
    build_single_cpu_remediation_plan,
    generate_all_cpu_remediation_plans,
    save_segregated_cpu_data,
    segregate_cpu_data,
)
from tools.data_merger import merge_telemetry_data
from tools.metrics_fetcher import (
    CURRENT_METRICS_API_URL,
    extract_metric_series,
    fetch_current_metrics,
    fetch_live_telemetry_unmerged,
    filter_latest_records_by_timestamp,
    get_latest_metrics_file,
)

logger = logging.getLogger(__name__)

CPU_INSTRUCTIONS_PATH = PROJECT_ROOT / "agents" / "cpu_agent" / "instructions.md"
DISK_INSTRUCTIONS_PATH = PROJECT_ROOT / "agents" / "disk_agent" / "instructions.md"
MEMORY_INSTRUCTIONS_PATH = PROJECT_ROOT / "agents" / "memory_agent" / "instructions.md"

CPU_INSTRUCTIONS = CPU_INSTRUCTIONS_PATH.read_text(encoding="utf-8") if CPU_INSTRUCTIONS_PATH.exists() else "Autonomous CPU Agent"
DISK_INSTRUCTIONS = DISK_INSTRUCTIONS_PATH.read_text(encoding="utf-8") if DISK_INSTRUCTIONS_PATH.exists() else "Autonomous Disk Agent"
MEMORY_INSTRUCTIONS = MEMORY_INSTRUCTIONS_PATH.read_text(encoding="utf-8") if MEMORY_INSTRUCTIONS_PATH.exists() else "Autonomous Memory Agent"


def _resolve_telemetry_bundle(
    source: Optional[Union[str, Path, List[Dict[str, Any]], Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Resolves live unmerged telemetry bundle containing:
    - current_metrics: live snapshot from /api/metrics (cpu, disk, ram)
    - latest_5_recordings: last 5 recordings from /api/history
    - top_5_processes: top 5 processes from /api/processes
    - services_logs_5: 1 log each from 5 services from /api/service-logs
    """
    if isinstance(source, dict) and "current_metrics" in source:
        return source

    if source is None:
        try:
            return fetch_live_telemetry_unmerged()
        except Exception as exc:
            logger.warning(f"Could not fetch unmerged live telemetry from VM endpoints: {exc}")

    if isinstance(source, list):
        items = source
    elif isinstance(source, (str, Path)):
        p = Path(source)
        if p.exists():
            items = json.loads(p.read_text(encoding="utf-8-sig"))
        elif isinstance(source, str) and source.strip().startswith("["):
            items = json.loads(source)
        else:
            items = []
    else:
        items = []

    latest_5 = filter_latest_records_by_timestamp(items, count=5) if items else []
    latest_item = latest_5[-1] if latest_5 else {}
    return {
        "current_metrics": latest_item,
        "latest_5_recordings": latest_5,
        "top_5_processes": [],
        "services_logs_5": [],
        "timestamp": latest_item.get("timestamp", ""),
        "hostname": latest_item.get("hostname", "cpu-utilization-vm"),
    }


def _classify_memory_workload(process: Dict[str, Any]) -> str:
    """Classify a process without exposing its raw command or script body."""
    name = str(process.get("process_name") or process.get("name") or "").lower()
    command = str(process.get("command_line") or process.get("cmdline") or "").lower()
    synthetic_markers = ("stress_wave", "stress", "bytearray", "allocated:", "memory spike")
    if any(marker in name or marker in command for marker in synthetic_markers):
        return "synthetic/test memory workload"
    if any(marker in name or marker in command for marker in ("postgres", "mysql", "nginx", "sshd", "systemd", "dockerd")):
        return "infrastructure service"
    if any(marker in name or marker in command for marker in ("worker", "celery", "queue", "consumer", "job")):
        return "application worker"
    return "application or user process"


def _safe_process_label(process: Dict[str, Any], service_name: str) -> str:
    """Return safe process context for an engineer-facing recommendation."""
    name = str(process.get("process_name") or process.get("name") or service_name)
    pid = process.get("pid", "unknown")
    return f"{name} (PID {pid})"


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
    source: Optional[Union[str, Path, List[Dict[str, Any]], Dict[str, Any]]] = None,
    recipient_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Direct CPU Agent tool that:
    1. Fetches live unmerged telemetry (/api/metrics for current CPU, 5 recordings from /api/history,
       top 5 processes from /api/processes, 5 services from /api/service-logs).
    2. Predicts & analyzes based on the latest recording (current_metrics).
    3. Invokes LLM (Gemini) with unmerged payload (no merge).
    4. Evaluates highest crossed threshold and sends email alert if exceeded.
    5. Delivers remediation plans (only for usage > 90%, deduplicated to 1 for 100%).
    """
    recipient_email = (recipient_email or get_alert_email()).strip()
    bundle = _resolve_telemetry_bundle(source)
    current_metrics = bundle.get("current_metrics") or {}
    latest_5 = bundle.get("latest_5_recordings") or []
    top_5_procs = bundle.get("top_5_processes") or []
    services_logs_5 = bundle.get("services_logs_5") or []

    hostname = current_metrics.get("hostname", "cpu-utilization-vm")
    timestamp = current_metrics.get("timestamp", "")
    uptime = current_metrics.get("uptime", "")

    cpu_info = current_metrics.get("cpu") or {}
    cores = int(cpu_info.get("cores", 2) or 2)
    per_core = [float(c) for c in cpu_info.get("per_core", [])]
    reported_total = float(cpu_info.get("total", 0.0) or 0.0)
    current_usage = (sum(per_core) / len(per_core)) if per_core and reported_total <= 0 else reported_total

    # Peak usage across latest 5 recordings
    recent_usages = []
    for r in latest_5:
        c_tot = (r.get("cpu") or {}).get("total")
        if c_tot is not None:
            recent_usages.append(float(c_tot))
    if not recent_usages:
        recent_usages = [current_usage]
    peak_usage = max(recent_usages)

    # Autonomous LLM call with unmerged telemetry payload (no merge)
    llm_result = call_llm_agent(
        agent_name="cpu_agent",
        resource_type="CPU",
        metrics_payload=bundle,
        system_instructions=CPU_INSTRUCTIONS,
    )

    cpu_analysis = llm_result.get("cpu_analysis")
    detection = llm_result.get("detection", {})
    diagnosis = llm_result.get("diagnosis", {})
    remediation = llm_result.get("remediation", {})

    # Evaluate threshold based on latest reading and saturated cores
    saturated_cores = [i for i, c in enumerate(per_core) if c >= 99.0]
    eval_usage = max(current_usage, peak_usage)
    highest_threshold = get_highest_crossed_threshold(current_usage, per_core)
    if eval_usage >= 100.0 or len(saturated_cores) == cores:
        highest_threshold = 100
    elif eval_usage >= 70.0 and (highest_threshold is None or highest_threshold < 70):
        highest_threshold = 70
    elif eval_usage >= 50.0 and (highest_threshold is None or highest_threshold < 50):
        highest_threshold = 50

    cpu_severity = (
        "CRITICAL" if highest_threshold == 100
        else "HIGH" if highest_threshold == 70
        else "MEDIUM" if highest_threshold == 50
        else "LOW"
    )
    current_cpu_alert = current_usage > 70.0
    if current_cpu_alert:
        primary = top_5_procs[0] if top_5_procs else {}
        primary_name = primary.get("process_name") or primary.get("name") or hostname
        primary_pid = primary.get("pid", "unknown")
        primary_cpu = float(primary.get("cpu_percent", 0.0) or 0.0)
        primary_threads = primary.get("thread_count") or primary.get("threads")
        history_start = recent_usages[0] if recent_usages else current_usage
        history_average = sum(recent_usages) / len(recent_usages) if recent_usages else current_usage
        trend = "rising" if current_usage > history_start + 2 else "falling" if current_usage < history_start - 2 else "stable"
        saturated = ", ".join(str(i + 1) for i in saturated_cores) or "none"
        thread_note = f" with {primary_threads} threads" if primary_threads is not None else ""
        urgency = "CRITICAL: reduce non-essential CPU work immediately and involve the on-call." if current_usage >= 90 else "HIGH: reduce the identified workload before CPU reaches the 90% escalation tier."
        remediation = {
            "subagent": "remediation_agent",
            "status": "REMEDIATION_DRAFTED",
            "action_required": "\n".join([
                urgency,
                f"Cause: CPU is {current_usage:.1f}% now versus a {history_average:.1f}% history average ({trend}); {primary_name} (PID {primary_pid}) is the leading process at {primary_cpu:.1f}% CPU{thread_note}.",
                f"Check {primary_name} logs, worker count, request/batch volume, and the next history sample to distinguish a workload burst from a runaway loop or retry storm. Saturated cores: {saturated}.",
                f"Reduce concurrency, pause the specific non-critical job, or rate-limit the workload owned by {primary_name}; do not terminate a critical service based only on CPU percentage.",
                f"After the change, rerun telemetry and confirm CPU falls below 70% and the process CPU share declines. If CPU remains above 90% after workload control, scale host capacity; escalate if all cores remain saturated.",
            ]),
            "preventive_guardrail": None,
        }
    elif not current_cpu_alert:
        remediation = {
            "subagent": "remediation_agent",
            "status": "NOT_REQUIRED",
            "action_required": "",
            "preventive_guardrail": None,
        }

    if highest_threshold is None:
        detection["subagent"] = "detection_agent"
        detection["resource"] = "CPU"
        detection["detected"] = False
        detection["severity"] = "LOW"
        detection["crossed_thresholds"] = []
        detection["summary"] = f"No issues detected. CPU utilization is normal at {current_usage:.1f}%."
        diagnosis["subagent"] = "diagnosis_agent"
        diagnosis["diagnosis_status"] = "HEALTHY"
        diagnosis["severity"] = "LOW"
        diagnosis["root_cause"] = f"No issues detected. CPU compute capacity on {hostname} is operating within normal baseline limits ({current_usage:.1f}%)."
        diagnosis["explanation"] = "Host CPU utilization is normal and operating within optimal operational headroom."
        remediation["subagent"] = "remediation_agent"
        remediation["status"] = "HEALTHY"
        remediation["action_required"] = "No issues detected. No remediation required."
        remediation["preventive_guardrail"] = "Continue standard monitoring."
    else:
        detection.setdefault("subagent", "detection_agent")
        detection.setdefault("resource", "CPU")
        detection.setdefault("detected", True)
        detection.setdefault("crossed_thresholds", [th for th in [100, 70, 50] if highest_threshold >= th])
        detection["severity"] = cpu_severity
        if not detection.get("summary") or "0.0%" in detection.get("summary", "") or "No issues detected" in detection.get("summary", ""):
            detection["summary"] = f"CPU utilization reached {eval_usage:.1f}% (current: {current_usage:.1f}%). Exceeded threshold tier: {highest_threshold}%."
        diagnosis.setdefault("subagent", "diagnosis_agent")
        diagnosis["severity"] = cpu_severity
        diagnosis.setdefault("diagnosis_status", "CONFIRMED")
        if not diagnosis.get("root_cause") or "0.0%" in diagnosis.get("root_cause", "") or "No issues detected" in diagnosis.get("root_cause", ""):
            primary_proc = top_5_procs[0].get("process_name") if top_5_procs else hostname
            if highest_threshold == 100:
                diagnosis["root_cause"] = f"Full CPU saturation reached {eval_usage:.1f}% on {hostname}, driven primarily by {primary_proc}."
            else:
                diagnosis["root_cause"] = f"Elevated CPU utilization ({eval_usage:.1f}%) exceeding the {highest_threshold}% threshold, driven primarily by {primary_proc}."
        remediation.setdefault("subagent", "remediation_agent")
        remediation.setdefault("status", "REMEDIATION_DRAFTED")

    # Remediation plans based on latest recording:
    # 1. Only show for CPU utilization data having values > 90%.
    # 2. If 100% saturation is present, emit only 1 plan.
    remediation_plans = []
    if current_cpu_alert:
        primary_svc_name = top_5_procs[0].get("process_name") if top_5_procs else hostname
        rep_rec = {
            "record_id": "cpu_live_latest",
            "timestamp": timestamp,
            "hostname": hostname,
            "service_name": primary_svc_name,
            "usage_percent": max(current_usage, peak_usage),
            "cores": cores,
            "per_core": per_core,
            "saturated_cores": saturated_cores,
            "breached_thresholds": [th for th in [100, 70, 50] if max(current_usage, peak_usage) >= th],
        }
        plan = build_single_cpu_remediation_plan(rep_rec, 1)
        plan["action_required"] = remediation["action_required"]
        plan["preventive_guardrail"] = None
        remediation_plans.append(plan)

    # Email only after the current CPU reading crosses the operational alert
    # threshold. Historical peak values remain evidence for diagnosis but do
    # not independently trigger an email.
    email_alerts_dispatched = []
    if current_usage > 70.0:
        reported_cpu_usage = current_usage
        email_threshold = max(get_highest_crossed_threshold(current_usage, per_core) or 70, 70)
        alert_info = send_threshold_alert_email(
            resource_name="CPU",
            usage_percent=reported_cpu_usage,
            threshold=email_threshold,
            hostname=hostname,
            timestamp=timestamp,
            details={
                "current_usage": f"{current_usage:.1f}%",
                "peak_usage": f"{peak_usage:.1f}%",
                "cores": cores,
                "per_core": per_core,
                "highest_threshold_crossed": email_threshold,
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
        "service_name": top_5_procs[0].get("process_name") if top_5_procs else hostname,
        "cpu_utilization_analysis": cpu_analysis,
        "records": latest_5,
        "timestamp": timestamp,
        "peak_usage_percent": round(peak_usage, 1),
        "current_usage_percent": round(current_usage, 1),
        "highest_threshold_crossed": highest_threshold,
        "total_records_analyzed": len(latest_5),
        "data_source": "VM live /api/metrics (latest 5 recordings)",
        "problematic_records_count": len(remediation_plans),
        "remediation_plans": remediation_plans,
        "remediation_summary": remediation,
        "remediation": remediation,
        "detection": detection,
        "diagnosis": diagnosis,
        "email_alerts": email_alerts_dispatched,
        "llm_powered": llm_result.get("llm_powered", False),
        "model_used": llm_result.get("model_used"),
        "top_processes": top_5_procs,
        "service_logs": services_logs_5,
    }


def process_system_disk_metrics(
    source: Optional[Union[str, Path, List[Dict[str, Any]], Dict[str, Any]]] = None,
    recipient_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Direct Disk Agent tool:
    1. Fetches live unmerged telemetry (/api/metrics for current Disk, 5 recordings from /api/history,
       top 5 processes from /api/processes, 5 services from /api/service-logs).
    2. Predicts & analyzes based on the latest recording (current_metrics).
    3. Invokes LLM (Gemini) with unmerged payload (no merge).
    4. Evaluates single highest crossed threshold (50%, 70%, 100%) and sends alert email via Nodemailer.
    """
    recipient_email = (recipient_email or get_alert_email()).strip()
    bundle = _resolve_telemetry_bundle(source)
    current_metrics = bundle.get("current_metrics") or {}
    latest_5 = bundle.get("latest_5_recordings") or []
    top_5_procs = bundle.get("top_5_processes") or []
    services_logs_5 = bundle.get("services_logs_5") or []

    hostname = current_metrics.get("hostname", "cpu-utilization-vm")
    timestamp = current_metrics.get("timestamp", "")

    disk_info = current_metrics.get("disk") or {}
    current_usage = float(disk_info.get("percent", 0.0) or 0.0)
    used_gb = float(disk_info.get("used_gb", 0.0) or 0.0)
    free_gb = float(disk_info.get("free_gb", 0.0) or 0.0)
    total_gb = float(disk_info.get("total_gb", 0.0) or 0.0)

    recent_disk = [float((r.get("disk") or {}).get("percent", current_usage) or current_usage) for r in latest_5]
    peak_disk_usage = max(recent_disk) if recent_disk else current_usage

    llm_result = call_llm_agent(
        agent_name="disk_agent",
        resource_type="Disk",
        metrics_payload=bundle,
        system_instructions=DISK_INSTRUCTIONS,
    )

    disk_analysis = llm_result.get("disk_analysis")
    detection = llm_result.get("detection", {})
    diagnosis = llm_result.get("diagnosis", {})
    remediation = llm_result.get("remediation", {})

    highest_threshold = None
    max_d = max(current_usage, peak_disk_usage)
    if max_d >= 100.0:
        highest_threshold = 100
    elif max_d >= 70.0:
        highest_threshold = 70
    elif max_d >= 50.0:
        highest_threshold = 50

    disk_severity = (
        "CRITICAL" if highest_threshold == 100
        else "HIGH" if highest_threshold == 70
        else "MEDIUM" if highest_threshold == 50
        else "LOW"
    )
    current_disk_alert = current_usage > 70.0
    if current_disk_alert:
        primary = top_5_procs[0] if top_5_procs else {}
        primary_name = primary.get("process_name") or primary.get("name") or hostname
        primary_pid = primary.get("pid", "unknown")
        read_rate = float(primary.get("disk_read_bytes_per_sec", 0.0) or 0.0)
        write_rate = float(primary.get("disk_write_bytes_per_sec", 0.0) or 0.0)
        history_start = recent_disk[0] if recent_disk else current_usage
        history_average = sum(recent_disk) / len(recent_disk) if recent_disk else current_usage
        trend = "rising" if current_usage > history_start + 2 else "falling" if current_usage < history_start - 2 else "stable"
        pressure = "CRITICAL: begin emergency cleanup and involve the on-call." if current_usage >= 90 else "HIGH: start targeted cleanup before free capacity becomes constrained."
        remediation = {
            "subagent": "remediation_agent",
            "status": "REMEDIATION_DRAFTED",
            "action_required": "\n".join([
                pressure,
                f"Cause: disk usage is {current_usage:.1f}% now versus a {history_average:.1f}% history average ({trend}); {primary_name} (PID {primary_pid}) is the leading observed I/O process.",
                f"Inspect {primary_name}'s logs and storage activity for the source of growth: rotating logs, temporary files, database files, uploads, or an unexpected write loop. Its observed rates are {read_rate:.1f} B/s read and {write_rate:.1f} B/s written.",
                f"Clean or rotate only the identified safe files, reduce the responsible workload, and preserve required database/log data. Do not delete an entire directory or stop a critical service without ownership confirmation.",
                f"Rerun disk telemetry after cleanup and confirm usage falls below 70%, free space increases, and the write rate declines. Escalate at 90% or when free space reaches the service's emergency reserve.",
            ]),
            "preventive_guardrail": None,
        }
    else:
        remediation = {
            "subagent": "remediation_agent",
            "status": "NOT_REQUIRED",
            "action_required": "",
            "preventive_guardrail": None,
        }

    if highest_threshold is None:
        detection = {
            "subagent": "detection_agent",
            "resource": "Disk",
            "metric_type": "SYSTEM_DISK_USAGE",
            "detected": False,
            "severity": "LOW",
            "crossed_thresholds": [],
            "summary": f"No issues detected. Disk utilization is normal at {current_usage:.1f}% ({used_gb:.2f} GB used of {total_gb:.2f} GB; {free_gb:.2f} GB free).",
        }
        diagnosis = {
            "subagent": "diagnosis_agent",
            "diagnosis_status": "HEALTHY",
            "severity": "LOW",
            "root_cause": f"No issues detected. System disk utilization on {hostname} is normal at {current_usage:.1f}%.",
            "explanation": f"The host has {free_gb:.2f} GB free out of {total_gb:.2f} GB. Capacity is healthy with no issues.",
        }
        remediation = {
            "subagent": "remediation_agent",
            "status": "HEALTHY",
            "action_required": "No issues detected. No remediation required.",
            "preventive_guardrail": "Maintain normal monitoring and log-retention policies.",
        }
    else:
        detection = {
            **detection,
            "subagent": "detection_agent",
            "resource": "Disk",
            "metric_type": "SYSTEM_DISK_USAGE",
            "detected": True,
            "severity": disk_severity,
            "crossed_thresholds": [th for th in [100, 70, 50] if highest_threshold >= th],
            "summary": f"{hostname} disk usage reached {current_usage:.1f}% ({used_gb:.2f} GB used of {total_gb:.2f} GB).",
        }
        diagnosis.setdefault("subagent", "diagnosis_agent")
        diagnosis["severity"] = disk_severity
        diagnosis.setdefault("diagnosis_status", "CONFIRMED")
        remediation.setdefault("subagent", "remediation_agent")
        remediation.setdefault("status", "REMEDIATION_DRAFTED")

    remediation_plans = []
    if current_disk_alert:
        remediation_plans.append({
            "plan_id": "REMED-DISK-001",
            "service_name": top_5_procs[0].get("process_name") if top_5_procs else hostname,
            "severity": disk_severity,
            "root_cause": diagnosis.get("root_cause") or f"Disk utilization reached {max_d:.1f}%",
            "action_required": remediation["action_required"],
            "preventive_guardrail": None,
        })

    email_alerts = []
    if current_usage > 70.0:
        reported_disk_usage = current_usage
        email_threshold = 100 if current_usage >= 100 else 70
        email_alerts.append(send_threshold_alert_email(
            resource_name="Disk",
            usage_percent=reported_disk_usage,
            threshold=email_threshold,
            hostname=hostname,
            timestamp=timestamp,
            details={
                "current_usage": f"{current_usage:.1f}%",
                "used_gb": used_gb,
                "total_gb": total_gb,
                "free_gb": free_gb,
                "peak_usage": f"{peak_disk_usage:.1f}%",
                "agent": "disk_agent",
            },
            remediation_summary=remediation.get("action_required"),
            recipient_email=recipient_email,
        ))

    disk_evidence = {
        "used_gb": round(used_gb, 2),
        "free_gb": round(free_gb, 2),
        "total_gb": round(total_gb, 2),
        "percent": round(current_usage, 1),
    }
    detection["evidence"] = disk_evidence

    return {
        "success": True,
        "agent": "disk_agent",
        "resource": "Disk",
        "hostname": hostname,
        "service_name": top_5_procs[0].get("process_name") if top_5_procs else hostname,
        "disk_utilization_analysis": disk_analysis,
        "total_records_analyzed": len(latest_5),
        "data_source": "VM live /api/metrics (latest 5 recordings)",
        "records": latest_5,
        "usage_percent": round(current_usage, 1),
        "peak_usage_percent": round(peak_disk_usage, 1),
        "current_usage_percent": round(current_usage, 1),
        "highest_threshold_crossed": highest_threshold,
        "disk_stats": {
            "hostname": hostname,
            "current_percent": round(current_usage, 1),
            "peak_percent": round(peak_disk_usage, 1),
            "used_gb": round(used_gb, 2),
            "free_gb": round(free_gb, 2),
            "total_gb": round(total_gb, 2),
            "threshold_crossed": highest_threshold,
        },
        "remediation_plans": remediation_plans,
        "detection": detection,
        "diagnosis": diagnosis,
        "remediation": remediation,
        "email_alerts": email_alerts,
        "llm_powered": llm_result.get("llm_powered", False),
        "model_used": llm_result.get("model_used"),
        "timestamp": timestamp,
        "top_processes": top_5_procs,
        "service_logs": services_logs_5,
    }


def process_system_memory_metrics(
    source: Optional[Union[str, Path, List[Dict[str, Any]], Dict[str, Any]]] = None,
    recipient_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Direct Memory Agent tool:
    1. Fetches live unmerged telemetry (/api/metrics for current RAM, 5 recordings from /api/history,
       top 5 processes from /api/processes, 5 services from /api/service-logs).
    2. Predicts & analyzes based on the latest recording (current_metrics).
    3. Invokes LLM (Gemini) with unmerged payload (no merge).
    4. Evaluates single highest crossed threshold (50%, 70%, 100%) and sends alert email via Nodemailer.
    """
    recipient_email = (recipient_email or get_alert_email()).strip()
    bundle = _resolve_telemetry_bundle(source)
    current_metrics = bundle.get("current_metrics") or {}
    latest_5 = bundle.get("latest_5_recordings") or []
    top_5_procs = bundle.get("top_5_memory_processes") or bundle.get("top_5_processes") or []
    services_logs_5 = bundle.get("services_logs_5") or []

    # /api/processes is ordered by CPU, so explicitly order this list by RAM
    # before selecting the processes shown by the memory agent.
    top_memory_procs = sorted(
        top_5_procs,
        key=lambda process: float(process.get("memory_percent", 0.0) or 0.0),
        reverse=True,
    )

    hostname = current_metrics.get("hostname", "cpu-utilization-vm")
    timestamp = current_metrics.get("timestamp", "")

    ram_info = current_metrics.get("ram") or {}
    current_usage = float(ram_info.get("percent", 0.0) or 0.0)
    used_gb = float(ram_info.get("used_gb", 0.0) or 0.0)
    available_gb = float(ram_info.get("available_gb", 0.0) or 0.0)
    total_gb = float(ram_info.get("total_gb", 0.0) or 0.0)

    recent_ram = [float((r.get("ram") or {}).get("percent", current_usage) or current_usage) for r in latest_5]
    peak_ram_usage = max(recent_ram) if recent_ram else current_usage

    llm_result = call_llm_agent(
        agent_name="memory_agent",
        resource_type="RAM",
        metrics_payload=bundle,
        system_instructions=MEMORY_INSTRUCTIONS,
    )

    memory_analysis = llm_result.get("memory_analysis")
    detection = llm_result.get("detection", {})
    diagnosis = llm_result.get("diagnosis", {})
    remediation = llm_result.get("remediation", {})

    # Historical peaks may inform diagnosis, but remediation is only valid for
    # the current live RAM reading when it is above the operational threshold.
    current_memory_alert = current_usage > 70.0
    if not current_memory_alert:
        remediation = {
            "subagent": "remediation_agent",
            "status": "NOT_REQUIRED",
            "action_required": "",
            "preventive_guardrail": None,
        }

    highest_threshold = None
    # Threshold severity and remediation must follow the current reading. A
    # historical peak is context only and must not make a 71% reading look
    # like a 90% incident.
    if current_usage >= 90.0:
        highest_threshold = 90
    elif current_usage > 70.0:
        highest_threshold = 70
    elif current_usage >= 50.0:
        highest_threshold = 50
    max_ram = max(current_usage, peak_ram_usage)

    mem_severity = (
        "CRITICAL" if highest_threshold == 90
        else "HIGH" if highest_threshold == 70
        else "MEDIUM" if highest_threshold == 50
        else "LOW"
    )
    primary_process = top_memory_procs[0] if top_memory_procs else {}
    service_name = (
        primary_process.get("service_name")
        or primary_process.get("process_name")
        or primary_process.get("name")
        or hostname
    )
    high_memory_services = []
    for event in services_logs_5:
        service_memory = event.get("memory_percent", event.get("memory_usage_percent"))
        service_rss = event.get("memory_rss_mb", event.get("rss_mb"))
        if service_memory is None and service_rss is None:
            continue
        high_memory_services.append({
            "service_name": event.get("service_name", "unknown-service"),
            "memory_percent": service_memory,
            "memory_rss_mb": service_rss,
            "active_state": event.get("active_state", "unknown"),
        })
    high_memory_services.sort(
        key=lambda service: float(service.get("memory_percent", 0.0) or 0.0),
        reverse=True,
    )

    remediation_steps = []
    if current_memory_alert:
        primary_name = primary_process.get("process_name") or primary_process.get("name") or service_name
        primary_pid = primary_process.get("pid", "unknown")
        primary_rss = float(primary_process.get("memory_rss_mb", 0.0) or 0.0)
        primary_percent = float(primary_process.get("memory_percent", 0.0) or 0.0)
        history_start = recent_ram[0] if recent_ram else current_usage
        history_average = sum(recent_ram) / len(recent_ram) if recent_ram else current_usage
        history_delta = current_usage - history_start
        trend = "rising" if history_delta > 2 else "falling" if history_delta < -2 else "stable"
        workload_type = _classify_memory_workload(primary_process)
        process_text = f"{primary_name} (PID {primary_pid}, {primary_rss:.1f} MB RSS)"
        service_text = str(primary_process.get("service_name") or primary_name)
        critical_service = workload_type == "infrastructure service" or any(word in service_text.lower() for word in ("sshd", "systemd", "db", "postgres", "mysql", "nginx"))
        synthetic_workload = workload_type == "synthetic/test memory workload"
        if current_usage >= 90:
            urgency = "CRITICAL: freeze non-essential work now and involve the on-call before the host reaches an out-of-memory condition."
        elif trend == "rising":
            urgency = "HIGH: usage is still rising, so investigate and reduce the identified workload before it reaches the 90% escalation tier."
        else:
            urgency = "HIGH: usage is already above the operational limit; validate the consumer before taking a disruptive action."
        cause = (
            f"Likely cause: the top process is a {workload_type} with sustained or increasing allocation; current RAM is {current_usage:.1f}% versus a {history_average:.1f}% history average."
            if trend in ("rising", "stable")
            else f"Likely cause: a recent workload burst is subsiding; RAM fell from {history_start:.1f}% to {current_usage:.1f}%, but {primary_name} is still the largest live consumer."
        )
        stop_guidance = (
            f"This appears to be a synthetic/test memory workload ({process_text}), not a production service. Stop the test workload gracefully after confirming it belongs to the current test session, then verify RAM returns below 70%."
            if synthetic_workload
            else
            f"Do not kill {process_text}; {service_text} appears critical. Check `systemctl status {service_text}` and active connections, then schedule a controlled restart only if service health confirms it is safe."
            if critical_service
            else f"Do not kill the process immediately. Confirm that {process_text} belongs to a non-critical workload; then stop it gracefully only if approved, and verify RAM drops below 70%."
        )
        remediation_steps = [
            urgency,
            f"{cause} The top process is {process_text}, using {primary_percent:.2f}% of RAM; compare its RSS with the next process before assigning the cause.",
            f"Inspect {process_text} logs and child processes for evidence of a leak, queue backlog, cache growth, batch workload, or synthetic test allocation. Do not copy or execute the process command from telemetry. Compare the next history sample with {current_usage:.1f}% to confirm the trend.",
            f"Reduce the specific workload owned by {primary_name} (pause its queue, lower worker concurrency, or limit the batch) rather than changing the whole host; verify available RAM increases and current usage returns below 70%.",
            stop_guidance,
            f"Escalate immediately at 90% current usage or below {total_gb * 0.15:.2f} GB available. Preserve the PID, RSS, command, history window, and service logs so the root cause can be tracked.",
        ]
        remediation["status"] = "REMEDIATION_DRAFTED"
        remediation["action_required"] = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(remediation_steps))
        remediation["preventive_guardrail"] = None
        diagnosis["root_cause"] = (
            f"RAM utilization is {max_ram:.1f}%, above the 70% operational threshold. "
            f"{primary_name} (PID {primary_pid}) is the largest reported RAM consumer."
        )

    if highest_threshold is None:
        detection["subagent"] = "detection_agent"
        detection["resource"] = "RAM"
        detection["detected"] = False
        detection["severity"] = "LOW"
        detection["crossed_thresholds"] = []
        detection["summary"] = f"No issues detected. RAM utilization is normal at {current_usage:.1f}% ({used_gb:.2f} GB used of {total_gb:.2f} GB; {available_gb:.2f} GB available)."
        diagnosis["subagent"] = "diagnosis_agent"
        diagnosis["diagnosis_status"] = "HEALTHY"
        diagnosis["severity"] = "LOW"
        diagnosis["root_cause"] = f"No issues detected. Host memory allocations on {hostname} are normal at {current_usage:.1f}% ({used_gb:.2f} GB used of {total_gb:.2f} GB)."
        diagnosis["explanation"] = f"The host has {available_gb:.2f} GB available out of {total_gb:.2f} GB. Capacity is healthy with no issues."
        remediation["subagent"] = "remediation_agent"
        remediation["status"] = "HEALTHY"
        remediation["action_required"] = "No issues detected. No remediation required."
        remediation["preventive_guardrail"] = "Continue standard monitoring."
    else:
        detection.setdefault("subagent", "detection_agent")
        detection.setdefault("resource", "RAM")
        detection.setdefault("detected", True)
        detection.setdefault("crossed_thresholds", [th for th in [90, 70, 50] if highest_threshold >= th])
        detection.setdefault("severity", mem_severity)
        if not detection.get("summary") or "0.0%" in detection.get("summary", "") or "No issues detected" in detection.get("summary", ""):
            detection["summary"] = f"RAM utilization reached {max_ram:.1f}% ({used_gb:.2f} GB of {total_gb:.2f} GB used). Exceeded threshold tier: {highest_threshold}%."
        diagnosis.setdefault("subagent", "diagnosis_agent")
        diagnosis.setdefault("severity", mem_severity)
        diagnosis.setdefault("diagnosis_status", "CONFIRMED")
        if not diagnosis.get("root_cause") or "0.0%" in diagnosis.get("root_cause", "") or "No issues detected" in diagnosis.get("root_cause", ""):
            diagnosis["root_cause"] = f"Elevated RAM usage ({max_ram:.1f}%) crossed the {highest_threshold}% threshold with {available_gb:.2f} GB available of {total_gb:.2f} GB."
        remediation.setdefault("subagent", "remediation_agent")
        remediation.setdefault("status", "REMEDIATION_DRAFTED")

    # A historical peak can affect diagnosis, but never creates a remediation
    # payload when the current RAM reading is at or below 70%.
    if not current_memory_alert:
        remediation["status"] = "NOT_REQUIRED"
        remediation["action_required"] = ""
        remediation["preventive_guardrail"] = None

    remediation_plans = []
    if current_memory_alert:
        primary_svc_name = primary_process.get("process_name") or hostname
        remediation_plans.append({
            "plan_id": "REMED-RAM-0001",
            "service_name": primary_svc_name,
            "severity": mem_severity,
            "memory_usage_percent": max_ram,
            "root_cause": diagnosis.get("root_cause") or f"Memory usage reached {max_ram:.1f}%",
            "action_required": remediation["action_required"],
            "preventive_guardrail": remediation["preventive_guardrail"],
        })

    email_alerts = []
    if current_usage > 70.0:
        reported_ram_usage = current_usage
        email_threshold = 90 if current_usage >= 90 else 70
        email_alerts.append(send_threshold_alert_email(
            resource_name="RAM",
            usage_percent=reported_ram_usage,
            threshold=email_threshold,
            hostname=hostname,
            timestamp=timestamp,
            details={
                "current_usage": f"{current_usage:.1f}%",
                "used_gb": used_gb,
                "total_gb": total_gb,
                "available_gb": available_gb,
                "peak_usage": f"{peak_ram_usage:.1f}%",
                "agent": "memory_agent",
            },
            remediation_summary=remediation.get("action_required"),
            recipient_email=recipient_email,
        ))
    ram_evidence = {
        "used_gb": round(used_gb, 2),
        "available_gb": round(available_gb, 2),
        "free_gb": round(available_gb, 2),
        "total_gb": round(total_gb, 2),
        "percent": round(current_usage, 1),
    }
    detection["evidence"] = ram_evidence

    return {
        "success": True,
        "agent": "memory_agent",
        "resource": "RAM",
        "hostname": hostname,
        "service_name": service_name,
        "memory_stats": {
            "service_name": service_name,
            "hostname": hostname,
            "current_percent": round(current_usage, 1),
            "peak_percent": round(peak_ram_usage, 1),
            "used_gb": round(used_gb, 2),
            "available_gb": round(available_gb, 2),
            "total_gb": round(total_gb, 2),
            "threshold_crossed": highest_threshold,
            "primary_process": primary_process,
        },
        "high_memory_processes": top_memory_procs,
        "high_memory_services": high_memory_services,
        "memory_utilization_analysis": memory_analysis,
        "total_records_analyzed": len(latest_5),
        "data_source": "VM live /api/metrics (latest 5 recordings)",
        "records": latest_5,
        "usage_percent": round(current_usage, 1),
        "peak_usage_percent": round(peak_ram_usage, 1),
        "current_usage_percent": round(current_usage, 1),
        "highest_threshold_crossed": highest_threshold,
        "remediation_plans": remediation_plans,
        "remediation_points": [plan["action_required"] for plan in remediation_plans],
        "remediation_steps": remediation_steps,
        "detection": detection,
        "diagnosis": diagnosis,
        "remediation": remediation,
        "email_alerts": email_alerts,
        "llm_powered": llm_result.get("llm_powered", False),
        "model_used": llm_result.get("model_used"),
        "timestamp": timestamp,
        "top_processes": top_5_procs,
        "service_logs": services_logs_5,
    }
