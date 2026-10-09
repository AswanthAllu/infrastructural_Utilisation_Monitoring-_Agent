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

    latest_item = items[-1] if items else {}
    latest_5 = items[-5:] if len(items) >= 5 else items
    return {
        "current_metrics": latest_item,
        "latest_5_recordings": latest_5,
        "top_5_processes": [],
        "services_logs_5": [],
        "timestamp": latest_item.get("timestamp", ""),
        "hostname": latest_item.get("hostname", "cpu-utilization-vm"),
    }


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
    recipient_email: str = DEFAULT_ALERT_EMAIL,
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
        detection.setdefault("severity", "CRITICAL" if highest_threshold == 100 else ("HIGH" if highest_threshold == 70 else "MEDIUM"))
        diagnosis.setdefault("subagent", "diagnosis_agent")
        diagnosis.setdefault("severity", detection.get("severity"))
        diagnosis.setdefault("diagnosis_status", "CONFIRMED")
        remediation.setdefault("subagent", "remediation_agent")
        remediation.setdefault("status", "REMEDIATION_DRAFTED")

    # Remediation plans based on latest recording:
    # 1. Only show for CPU utilization data having values > 90%.
    # 2. If 100% saturation is present, emit only 1 plan.
    remediation_plans = []
    if current_usage > 90.0 or peak_usage > 90.0:
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
        remediation_plans.append(plan)

    # Email alert if threshold crossed
    email_alerts_dispatched = []
    if highest_threshold is not None:
        reported_cpu_usage = max(current_usage, peak_usage)
        alert_info = send_threshold_alert_email(
            resource_name="CPU",
            usage_percent=reported_cpu_usage,
            threshold=highest_threshold,
            hostname=hostname,
            timestamp=timestamp,
            details={
                "current_usage": f"{current_usage:.1f}%",
                "peak_usage": f"{peak_usage:.1f}%",
                "cores": cores,
                "per_core": per_core,
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
    recipient_email: str = DEFAULT_ALERT_EMAIL,
) -> Dict[str, Any]:
    """
    Direct Disk Agent tool:
    1. Fetches live unmerged telemetry (/api/metrics for current Disk, 5 recordings from /api/history,
       top 5 processes from /api/processes, 5 services from /api/service-logs).
    2. Predicts & analyzes based on the latest recording (current_metrics).
    3. Invokes LLM (Gemini) with unmerged payload (no merge).
    4. Evaluates single highest crossed threshold (50%, 70%, 100%) and sends alert email via Nodemailer.
    """
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
        diagnosis.setdefault("severity", disk_severity)
        diagnosis.setdefault("diagnosis_status", "CONFIRMED")
        remediation.setdefault("subagent", "remediation_agent")
        remediation.setdefault("status", "REMEDIATION_DRAFTED")

    remediation_plans = []
    if highest_threshold:
        remediation_plans.append({
            "plan_id": "REMED-DISK-001",
            "service_name": top_5_procs[0].get("process_name") if top_5_procs else hostname,
            "severity": disk_severity,
            "root_cause": diagnosis.get("root_cause") or f"Disk utilization reached {max_d:.1f}%",
            "action_required": remediation.get("action_required") or diagnosis.get("recommended_action") or "Monitor disk space.",
            "preventive_guardrail": remediation.get("preventive_guardrail") or "Set alert threshold at 70% disk capacity.",
        })

    email_alerts = []
    if highest_threshold is not None:
        reported_disk_usage = max(current_usage, peak_disk_usage)
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
        "service_name": top_5_procs[0].get("process_name") if top_5_procs else hostname,
        "disk_utilization_analysis": disk_analysis,
        "total_records_analyzed": len(latest_5),
        "data_source": "VM live /api/metrics (latest 5 recordings)",
        "records": latest_5,
        "usage_percent": round(current_usage, 1),
        "peak_usage_percent": round(peak_disk_usage, 1),
        "current_usage_percent": round(current_usage, 1),
        "highest_threshold_crossed": highest_threshold,
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
    recipient_email: str = DEFAULT_ALERT_EMAIL,
) -> Dict[str, Any]:
    """
    Direct Memory Agent tool:
    1. Fetches live unmerged telemetry (/api/metrics for current RAM, 5 recordings from /api/history,
       top 5 processes from /api/processes, 5 services from /api/service-logs).
    2. Predicts & analyzes based on the latest recording (current_metrics).
    3. Invokes LLM (Gemini) with unmerged payload (no merge).
    4. Evaluates single highest crossed threshold (50%, 70%, 100%) and sends alert email via Nodemailer.
    """
    bundle = _resolve_telemetry_bundle(source)
    current_metrics = bundle.get("current_metrics") or {}
    latest_5 = bundle.get("latest_5_recordings") or []
    top_5_procs = bundle.get("top_5_processes") or []
    services_logs_5 = bundle.get("services_logs_5") or []

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

    highest_threshold = None
    max_ram = max(current_usage, peak_ram_usage)
    if max_ram >= 100.0:
        highest_threshold = 100
    elif max_ram >= 70.0:
        highest_threshold = 70
    elif max_ram >= 50.0:
        highest_threshold = 50

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
        detection.setdefault("crossed_thresholds", [th for th in [100, 70, 50] if highest_threshold >= th])
        detection.setdefault("severity", mem_severity)
        diagnosis.setdefault("subagent", "diagnosis_agent")
        diagnosis.setdefault("severity", mem_severity)
        diagnosis.setdefault("diagnosis_status", "CONFIRMED")
        remediation.setdefault("subagent", "remediation_agent")
        remediation.setdefault("status", "REMEDIATION_DRAFTED")

    remediation_plans = []
    if highest_threshold:
        primary_svc_name = top_5_procs[0].get("process_name") if top_5_procs else hostname
        remediation_plans.append({
            "plan_id": "REMED-RAM-0001",
            "service_name": primary_svc_name,
            "severity": mem_severity,
            "memory_usage_percent": max_ram,
            "root_cause": diagnosis.get("root_cause") or f"Memory usage reached {max_ram:.1f}%",
            "action_required": remediation.get("action_required") or "Monitor memory allocation and inspect working sets.",
            "preventive_guardrail": remediation.get("preventive_guardrail") or "Set proactive memory alert at 70%.",
        })

    email_alerts = []
    if highest_threshold is not None:
        reported_ram_usage = max(current_usage, peak_ram_usage)
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
        "service_name": top_5_procs[0].get("process_name") if top_5_procs else hostname,
        "memory_utilization_analysis": memory_analysis,
        "total_records_analyzed": len(latest_5),
        "data_source": "VM live /api/metrics (latest 5 recordings)",
        "records": latest_5,
        "usage_percent": round(current_usage, 1),
        "peak_usage_percent": round(peak_ram_usage, 1),
        "current_usage_percent": round(current_usage, 1),
        "highest_threshold_crossed": highest_threshold,
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
