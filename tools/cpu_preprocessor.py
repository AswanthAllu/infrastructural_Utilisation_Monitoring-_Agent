"""
CPU Telemetry Preprocessor & Segregation Script
Segregates CPU-only metrics from raw multi-resource system telemetry (e.g. from http://20.15.164.79:8080/api/history)
and formulates individual remediation plans for each detected CPU anomaly/bottleneck.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

DEFAULT_LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


def segregate_cpu_data(raw_telemetry: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Python preprocessing script step:
    Filters out disk, ram, and other non-CPU telemetry fields.
    Extracts strictly CPU-related data into a clean, normalized structure.
    """
    segregated_records: List[Dict[str, Any]] = []

    for idx, entry in enumerate(raw_telemetry):
        if not isinstance(entry, dict):
            continue

        cpu_info = entry.get("cpu") or {}
        timestamp = entry.get("timestamp", "")
        hostname = entry.get("hostname", "cpu-utilization-vm")
        service_name = entry.get("service_name") or entry.get("service") or entry.get("application") or entry.get("process_name") or hostname
        uptime = entry.get("uptime", "")

        cores = int(cpu_info.get("cores", 1))
        reported_total = float(cpu_info.get("total", 0.0) or 0.0)
        per_core_raw = cpu_info.get("per_core", [])
        per_core = [float(c) for c in per_core_raw] if per_core_raw else [reported_total]
        # Some VM snapshots report cpu.total as 0 while per_core contains the
        # actual utilization. Use the average core utilization in that case so
        # threshold detection reflects the real VM state.
        total_usage = (sum(per_core) / len(per_core)) if per_core and reported_total <= 0 else reported_total

        saturated_cores = [i for i, c in enumerate(per_core) if c >= 99.0]
        hot_cores = [i for i, c in enumerate(per_core) if c >= 70.0 and i not in saturated_cores]

        breached_thresholds = []
        if total_usage >= 100.0 or len(saturated_cores) == cores:
            breached_thresholds.extend([100, 70, 50])
        elif total_usage >= 70.0 or len(saturated_cores) > 0:
            breached_thresholds.extend([70, 50])
        elif total_usage >= 50.0:
            breached_thresholds.append(50)

        record = {
            "record_id": f"cpu_rec_{idx+1:04d}",
            "timestamp": timestamp,
            "hostname": hostname,
            "service_name": service_name,
            "uptime": uptime,
            "metric_type": "SYSTEM_CPU_USAGE",
            "cpu": {
                "cores": cores,
                "per_core": per_core,
                "total": total_usage,
            },
            "usage_percent": total_usage,
            "cores": cores,
            "per_core": per_core,
            "saturated_cores": saturated_cores,
            "hot_cores": hot_cores,
            "breached_thresholds": list(sorted(set(breached_thresholds), reverse=True)),
            "is_anomaly": len(breached_thresholds) > 0 or len(saturated_cores) > 0,
        }
        segregated_records.append(record)

    return segregated_records


def build_single_cpu_remediation_plan(
    record: Dict[str, Any],
    plan_index: int,
) -> Dict[str, Any]:
    """
    Formulates a distinct, tailored remediation plan for a single CPU record/incident.
    """
    rec_id = record.get("record_id", f"cpu_rec_{plan_index:04d}")
    timestamp = record.get("timestamp", "")
    hostname = record.get("hostname", "cpu-utilization-vm")
    service_name = record.get("service_name") or record.get("service") or record.get("application") or hostname
    usage = float(record.get("usage_percent", 0.0))
    cores = int(record.get("cores", 1))
    per_core = record.get("per_core", [])
    saturated_cores = record.get("saturated_cores", [])
    breached_thresholds = record.get("breached_thresholds", [])

    # Classify severity and root cause
    if usage >= 99.0 or (len(saturated_cores) == cores and cores > 0):
        severity = "CRITICAL"
        priority = 1
        root_cause = f"All {cores} cores 100% saturated. System thread queues blocked."
        diagnosis = (
            f"Sustained full compute exhaustion on {hostname}. All cores ({per_core}) "
            f"are locked at maximum capacity, causing task starvation and severe latency."
        )
        action_required = (
            f"1. Emergency scale host '{hostname}' from {cores} to at least {cores * 2} vCPUs.\n"
            f"2. Inspect highest CPU threads via `top -b -n 1 -H` or `pidstat -u 1 3` and renice or throttle PID.\n"
            f"3. Enable CPU core pinning / cgroups CPU quotas to isolate runaway workers."
        )
        preventive_guardrail = (
            "Establish auto-scaling trigger when average CPU > 85% for 2 minutes and enforce cgroup cpu.max."
        )
    elif len(saturated_cores) > 0 and usage < 99.0:
        severity = "CRITICAL" if len(saturated_cores) >= cores / 2 else "HIGH"
        priority = 1 if severity == "CRITICAL" else 2
        sat_str = ", ".join(f"Core {c}" for c in saturated_cores)
        root_cause = f"Single/multi-thread CPU core pin: {sat_str} saturated at 100% while total usage is {usage:.1f}%."
        diagnosis = (
            f"Workload imbalance detected on {hostname}. {sat_str} is pegged at 100.0%, "
            f"suggesting unvectorized loop, synchronous socket polling, or un-parallelized code."
        )
        action_required = (
            f"1. Profile process thread affinity on {sat_str} using `taskset -p <PID>`.\n"
            f"2. Rebalance worker threads across available idle cores (per_core={per_core}).\n"
            f"3. Refactor synchronous loop into asynchronous worker pool or multi-processing."
        )
        preventive_guardrail = (
            "Implement thread pool executor with thread-affinity rotation and set per-core alert at 95%."
        )
    elif usage >= 70.0:
        severity = "HIGH"
        priority = 2
        root_cause = f"High CPU utilization: Peak reached {usage:.1f}% (Tier 70% threshold crossed)."
        diagnosis = (
            f"Host {hostname} is running in the high-utilization band ({usage:.1f}%). "
            f"Headroom is constrained; sudden batch jobs will cause request degradation."
        )
        action_required = (
            "1. Identify top 5 CPU consumers and audit background cron schedules.\n"
            "2. Reschedule compute-heavy tasks away from peak operational windows.\n"
            "3. Optimize database connection pools and caching layers to minimize CPU wait states."
        )
        preventive_guardrail = (
            "Deploy automated alert at 70% CPU with automated runbook diagnostics triggered on threshold breach."
        )
    elif usage >= 50.0:
        severity = "MEDIUM"
        priority = 3
        root_cause = f"Moderate CPU utilization: Reached {usage:.1f}% (Tier 50% baseline crossed)."
        diagnosis = (
            f"Host {hostname} exceeded baseline 50% threshold ({usage:.1f}%). Operating within safe boundaries "
            f"but trending upward."
        )
        action_required = (
            "1. Monitor thread pool queue depth and garbage collection pauses.\n"
            "2. Verify application resource quotas and log retention rates."
        )
        preventive_guardrail = (
            "Ensure baseline telemetry reporting is active with 5-minute anomaly detection."
        )
    else:
        severity = "LOW"
        priority = 4
        root_cause = f"Nominal CPU operating parameters ({usage:.1f}%)."
        diagnosis = f"Host {hostname} CPU is healthy ({usage:.1f}% utilization)."
        action_required = "No immediate remediation needed. Continue continuous telemetry polling."
        preventive_guardrail = "Maintain standard health monitors."

    return {
        "plan_id": f"REMED-CPU-{plan_index:04d}",
        "record_id": rec_id,
        "timestamp": timestamp,
        "hostname": hostname,
        "service_name": service_name,
        "total_usage_percent": usage,
        "cores": cores,
        "per_core": per_core,
        "saturated_cores": saturated_cores,
        "breached_thresholds": breached_thresholds,
        "severity": severity,
        "priority": priority,
        "status": "REMEDIATION_DRAFTED" if severity != "LOW" else "HEALTHY",
        "root_cause": root_cause,
        "diagnosis": diagnosis,
        "action_required": action_required,
        "preventive_guardrail": preventive_guardrail,
    }


def generate_all_cpu_remediation_plans(
    segregated_cpu_records: List[Dict[str, Any]],
    only_problematic: bool = True,
) -> List[Dict[str, Any]]:
    """
    Iterates through segregated CPU records and produces an individualized remediation plan
    for every problematic CPU record (or all records if only_problematic=False).
    Ensures that if there are multiple problematic records, ALL remediation plans
    are returned in the API response.
    """
    plans: List[Dict[str, Any]] = []
    plan_counter = 1

    for record in segregated_cpu_records:
        is_problematic = record.get("is_anomaly", False) or float(record.get("usage_percent", 0.0)) >= 50.0
        if only_problematic and not is_problematic:
            continue

        plan = build_single_cpu_remediation_plan(record, plan_counter)
        plans.append(plan)
        plan_counter += 1

    return plans


def save_segregated_cpu_data(
    segregated_records: List[Dict[str, Any]],
    logs_dir: Optional[Path] = None,
) -> Path:
    """Saves segregated CPU records into logs/cpu_metrics_segregated.json."""
    target_dir = logs_dir or DEFAULT_LOGS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "cpu_metrics_segregated.json"
    target_file.write_text(json.dumps(segregated_records, indent=2), encoding="utf-8")
    return target_file
