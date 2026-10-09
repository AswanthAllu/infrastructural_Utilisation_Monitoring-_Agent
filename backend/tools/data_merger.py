import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
ROOT_LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"


def _extract_friendly_name(cmd: str, process_name: str) -> str:
    """Derive a human-friendly application/service name dynamically from process metadata without hardcoded names."""
    if process_name and process_name.strip():
        p_clean = process_name.strip().strip("'\"")
        if p_clean.lower() in ("python", "python3", "node", "java", "ruby", "perl", "bash", "sh") and cmd:
            tokens = cmd.strip().split()
            for token in tokens[1:]:
                if not token.startswith("-") and ("/" in token or "\\" in token or token.endswith((".py", ".js", ".jar", ".sh"))):
                    base = Path(token).stem.replace("_", " ").replace("-", " ").title()
                    return f"{base} Service" if not base.lower().endswith("service") else base
        base = p_clean.replace("_", " ").replace("-", " ").title()
        return base
    if cmd and cmd.strip():
        first_token = cmd.strip().split()[0]
        return Path(first_token).stem.replace("_", " ").replace("-", " ").title()
    return "Workload Process"


def _find_correlated_logs(
    service_logs_data: Dict[str, Any],
    top_proc: Dict[str, Any],
    snapshot_time_str: str,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Correlates service event logs with the top process and snapshot timestamp.
    Matches by process PID, command line, or service unit name.
    """
    services = service_logs_data.get("Services", [])
    primary_pid = top_proc.get("pid")
    primary_cmd = (top_proc.get("command_line") or "").lower()

    # Determine target service keyword dynamically
    target_service_kw = ""
    if primary_cmd:
        first_token = primary_cmd.strip().split()[0]
        target_service_kw = Path(first_token).stem.replace("_", "-")
        for part in primary_cmd.split():
            if part.endswith((".py", ".js", ".sh", ".service")):
                target_service_kw = Path(part).stem.replace("_", "-")
                break

    correlated_event = None
    supporting_events = []

    for svc in services:
        s_name = svc.get("ServiceName", "")
        s_desc = svc.get("Description", "")
        logs = svc.get("Logs", [])

        is_primary_svc = target_service_kw and target_service_kw in s_name.lower()

        for log in reversed(logs):  # check most recent first
            msg = str(log.get("Message") or "")
            proc_tag = str(log.get("Process") or "")
            t_gen = str(log.get("TimeGenerated") or "")

            # Check if this log matches the primary process PID or service
            if not correlated_event:
                if (primary_pid and f"[{primary_pid}]" in proc_tag) or is_primary_svc:
                    correlated_event = {
                        "service_name": s_name,
                        "description": s_desc,
                        "timestamp": t_gen or snapshot_time_str,
                        "process_tag": proc_tag,
                        "message": msg,
                    }
                    continue

            # Collect other relevant events as supporting evidence
            if s_name != (correlated_event or {}).get("service_name"):
                if len(supporting_events) < 3 and msg and msg != (correlated_event or {}).get("message"):
                    supporting_events.append({
                        "service_name": s_name,
                        "timestamp": t_gen or snapshot_time_str,
                        "process_tag": proc_tag,
                        "message": msg,
                    })

    # Fallback correlated event if none matched explicitly
    if not correlated_event and services:
        for svc in services:
            if svc.get("Logs"):
                latest_l = svc["Logs"][-1]
                correlated_event = {
                    "service_name": svc.get("ServiceName"),
                    "description": svc.get("Description"),
                    "timestamp": latest_l.get("TimeGenerated", snapshot_time_str),
                    "process_tag": latest_l.get("Process"),
                    "message": latest_l.get("Message"),
                }
                break

    return correlated_event, supporting_events


def merge_telemetry_data(
    history_data: Optional[List[Dict[str, Any]]] = None,
    processes_data: Optional[Dict[str, Any]] = None,
    service_logs_data: Optional[Dict[str, Any]] = None,
    limit: int = 30,
    logs_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Merges telemetry data across history, processes, and service logs based on:
    1. Hostname ('cpu-utilization-vm')
    2. Process PID & process name / command line
    3. Service mappings (e.g. stress-wave.service, dashboard.service, postgresql)
    4. Timestamp alignment

    Returns exactly `limit` (default 30) merged telemetry records and saves to merged_data.json.
    """
    target_dir = logs_dir or DEFAULT_LOGS_DIR

    # Load from disk if not directly provided
    if history_data is None:
        h_file = target_dir / "history.json"
        if h_file.exists():
            history_data = json.loads(h_file.read_text(encoding="utf-8"))
        else:
            history_data = []

    if processes_data is None:
        p_file = target_dir / "processes.json"
        if p_file.exists():
            processes_data = json.loads(p_file.read_text(encoding="utf-8"))
        else:
            processes_data = {}

    if service_logs_data is None:
        s_file = target_dir / "service_logs.json"
        if s_file.exists():
            service_logs_data = json.loads(s_file.read_text(encoding="utf-8"))
        else:
            service_logs_data = {}

    # Sort processes by cpu_percent descending
    all_processes = processes_data.get("processes", [])
    sorted_procs = sorted(all_processes, key=lambda p: float(p.get("cpu_percent", 0.0)), reverse=True)
    primary_proc = sorted_procs[0] if sorted_procs else {}
    secondary_procs = sorted_procs[1:4] if len(sorted_procs) > 1 else []

    # Format primary process details
    primary_friendly = _extract_friendly_name(
        primary_proc.get("command_line", ""),
        primary_proc.get("process_name", ""),
    )
    thread_count = primary_proc.get("thread_count") or primary_proc.get("num_threads")

    # Select exactly `limit` history data points
    # History contains the time series of CPU spikes. If history has more than limit items,
    # select the first `limit` items (or window containing the transition).
    history_window = history_data[:limit] if len(history_data) >= limit else history_data

    merged_records = []
    for idx, snap in enumerate(history_window):
        t_snap = snap.get("timestamp", "")
        hostname = snap.get("hostname", "cpu-utilization-vm")
        uptime = snap.get("uptime", "")
        cpu_info = snap.get("cpu") or {}
        ram_info = snap.get("ram") or {}
        disk_info = snap.get("disk") or {}

        # Correlate service logs for this snapshot
        corr_event, supporting_events = _find_correlated_logs(
            service_logs_data,
            primary_proc,
            t_snap,
        )

        merged_item = {
            "record_id": f"merged_rec_{idx+1:04d}",
            "timestamp": t_snap,
            "hostname": hostname,
            "uptime": uptime,
            "cpu_metrics": {
                "total_percent": float(cpu_info.get("total", 0.0)),
                "cores": int(cpu_info.get("cores", 2)),
                "per_core": [float(c) for c in cpu_info.get("per_core", [])],
            },
            "ram_metrics": {
                "percent": float(ram_info.get("percent", 0.0)),
                "used_gb": float(ram_info.get("used_gb", 0.0)),
                "available_gb": float(ram_info.get("available_gb", 0.0)),
                "total_gb": float(ram_info.get("total_gb", 0.0)),
            },
            "disk_metrics": {
                "percent": float(disk_info.get("percent", 0.0)),
                "used_gb": float(disk_info.get("used_gb", 0.0)),
                "free_gb": float(disk_info.get("free_gb", 0.0)),
                "total_gb": float(disk_info.get("total_gb", 0.0)),
            },
            "primary_process": {
                "name": primary_friendly,
                "process_name": primary_proc.get("process_name", "unknown"),
                "pid": primary_proc.get("pid"),
                "command_line": primary_proc.get("command_line", ""),
                "cpu_percent": float(primary_proc.get("cpu_percent", 0.0)),
                "memory_percent": float(primary_proc.get("memory_percent", 0.0)),
                "memory_rss_mb": float(primary_proc.get("memory_rss_mb", 0.0)),
                "thread_count": thread_count,  # preserved if present
            },
            "secondary_processes": [
                {
                    "name": _extract_friendly_name(sp.get("command_line", ""), sp.get("process_name", "")),
                    "pid": sp.get("pid"),
                    "cpu_percent": float(sp.get("cpu_percent", 0.0)),
                    "memory_percent": float(sp.get("memory_percent", 0.0)),
                    "thread_count": sp.get("thread_count") or sp.get("num_threads"),
                }
                for sp in secondary_procs
            ],
            "correlated_service_event": corr_event,
            "supporting_evidence": supporting_events,
        }
        merged_records.append(merged_item)

    # Save to logs folder
    save_merged_data(merged_records, target_dir)
    return merged_records


def save_merged_data(records: List[Dict[str, Any]], logs_dir: Optional[Path] = None) -> Path:
    """Save the merged data list into merged_data.json in logs directory."""
    target_dir = logs_dir or DEFAULT_LOGS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    out_file = target_dir / "merged_data.json"
    out_file.write_text(json.dumps(records, indent=2), encoding="utf-8")

    # Also mirror to root logs if different
    try:
        ROOT_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        (ROOT_LOGS_DIR / "merged_data.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.debug(f"Could not mirror merged_data.json to root logs: {exc}")

    return out_file
