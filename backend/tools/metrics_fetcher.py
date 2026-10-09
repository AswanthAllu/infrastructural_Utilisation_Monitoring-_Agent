import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

METRICS_API_BASE_URL = os.getenv("METRICS_API_BASE_URL", "http://20.15.164.79:8080").rstrip("/")
HISTORY_API_URL = f"{METRICS_API_BASE_URL}/api/history"
CURRENT_METRICS_API_URL = f"{METRICS_API_BASE_URL}/api/metrics"
PROCESSES_API_URL = f"{METRICS_API_BASE_URL}/api/processes"
SERVICE_LOGS_API_URL = f"{METRICS_API_BASE_URL}/api/service-logs"
DEFAULT_LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def fetch_live_telemetry_unmerged(
    base_url: str = METRICS_API_BASE_URL,
    timeout: int = 10,
    logs_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Fetches raw unmerged live telemetry directly from the 3 endpoints:
    1. /api/metrics - Live current VM-level CPU, Disk, and RAM utilization (replaces /history as current reading).
       Also captures the latest 5 recordings from /api/history.
    2. /api/processes - Top 5 processes by CPU utilization.
    3. /api/service-logs - 1 log each from 5 distinct active services.
    Saves raw files to logs/ without merging.
    """
    target_dir = logs_dir or DEFAULT_LOGS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Fetch current metrics from /api/metrics
    try:
        current_metrics = fetch_current_metrics(f"{base_url}/api/metrics", timeout=timeout)
    except Exception as exc:
        logger.warning(f"Could not fetch /api/metrics: {exc}")
        current_metrics = {}

    # Fetch latest 5 recordings from /api/history
    try:
        history_list = fetch_metrics_history(f"{base_url}/api/history", timeout=timeout)
        latest_5_recordings = history_list[-5:] if len(history_list) >= 5 else history_list
    except Exception as exc:
        logger.warning(f"Could not fetch /api/history: {exc}")
        latest_5_recordings = [current_metrics] if current_metrics else []

    if not current_metrics and latest_5_recordings:
        current_metrics = latest_5_recordings[-1]

    # 2. Fetch processes from /api/processes -> top 5 processes
    try:
        proc_data = fetch_current_metrics(f"{base_url}/api/processes", timeout=timeout)
        all_procs = proc_data.get("processes", [])
        sorted_procs = sorted(all_procs, key=lambda p: float(p.get("cpu_percent", 0.0)), reverse=True)
        top_5_processes = sorted_procs[:5]
    except Exception as exc:
        logger.warning(f"Could not fetch /api/processes: {exc}")
        top_5_processes = []

    # 3. Fetch service logs from /api/service-logs -> 5 logs from ALL distinct services (VM-independent)
    distinct_services_logs = {}
    all_distinct_service_logs = []
    try:
        logs_data = fetch_current_metrics(f"{base_url}/api/service-logs", timeout=timeout)
        services = logs_data.get("Services", [])
        for s in services:
            s_name = s.get("ServiceName", "unknown")
            desc = s.get("Description", "")
            active_st = s.get("ActiveState", "active")
            raw_logs = s.get("Logs", [])
            recent_5 = raw_logs[-5:] if len(raw_logs) >= 5 else raw_logs
            if not recent_5:
                continue

            svc_entries = []
            for l in recent_5:
                entry = {
                    "service_name": s_name,
                    "description": desc,
                    "active_state": active_st,
                    "timestamp": l.get("TimeGenerated", ""),
                    "process": l.get("Process", ""),
                    "message": l.get("Message", ""),
                }
                svc_entries.append(entry)
                all_distinct_service_logs.append(entry)

            distinct_services_logs[s_name] = {
                "service_name": s_name,
                "description": desc,
                "active_state": active_st,
                "logs_count": len(svc_entries),
                "logs": svc_entries,
            }
    except Exception as exc:
        logger.warning(f"Could not fetch /api/service-logs: {exc}")
        distinct_services_logs = {}
        all_distinct_service_logs = []

    bundle = {
        "current_metrics": current_metrics,
        "latest_5_recordings": latest_5_recordings,
        "top_5_processes": top_5_processes,
        "distinct_services_logs": distinct_services_logs,
        "all_services_logs": all_distinct_service_logs,
        "services_logs_5": all_distinct_service_logs,
        "distinct_services_count": len(distinct_services_logs),
        "timestamp": current_metrics.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "hostname": current_metrics.get("hostname", "system-host"),
    }

    try:
        (target_dir / "latest_metrics.json").write_text(json.dumps(current_metrics, indent=2), encoding="utf-8")
        (target_dir / "latest_5_recordings.json").write_text(json.dumps(latest_5_recordings, indent=2), encoding="utf-8")
        (target_dir / "latest_processes_5.json").write_text(json.dumps(top_5_processes, indent=2), encoding="utf-8")
        (target_dir / "latest_distinct_services_logs.json").write_text(json.dumps(distinct_services_logs, indent=2), encoding="utf-8")
        (target_dir / "latest_service_logs_5.json").write_text(json.dumps(all_distinct_service_logs, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.debug(f"Could not save unmerged telemetry cache: {exc}")

    return bundle


def fetch_metrics_history(url: str = HISTORY_API_URL, timeout: int = 10) -> List[Dict[str, Any]]:
    """Fetch metrics history JSON array from the remote monitoring endpoint."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AgentEcosystem/1.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content = response.read().decode("utf-8")
        data = json.loads(content)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return [data]
        return []


def load_configured_metrics(url: str = HISTORY_API_URL) -> tuple[List[Dict[str, Any]], str]:
    """Load the configured mock file or fetch live VM telemetry."""
    if os.getenv("DATA_SOURCE", "vm").strip().lower() == "mock":
        configured_path = Path(os.getenv("MOCK_METRICS_FILE", "mock_data/windows_services_metrics.json"))
        mock_path = configured_path if configured_path.is_absolute() else PROJECT_ROOT / configured_path
        if not mock_path.exists():
            raise FileNotFoundError(f"Configured mock metrics file does not exist: {mock_path}")
        data = json.loads(mock_path.read_text(encoding="utf-8"))
        return (data if isinstance(data, list) else [data]), f"Mock data: {mock_path.name}"
    return fetch_metrics_history(url), "VM telemetry API"


def fetch_current_metrics(url: str = CURRENT_METRICS_API_URL, timeout: int = 10) -> Dict[str, Any]:
    """Fetch live single-snapshot current metrics from http://20.15.164.79:8080/api/metrics."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AgentEcosystem/1.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content = response.read().decode("utf-8")
        data = json.loads(content)
        return data if isinstance(data, dict) else (data[0] if data else {})


def store_metrics_json(data: List[Dict[str, Any]], logs_dir: Optional[Path] = None) -> Path:
    """Store fetched metrics JSON into the logs folder with timestamp and update latest.json."""
    target_dir = logs_dir or DEFAULT_LOGS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    timestamped_file = target_dir / f"system_metrics_{timestamp_str}.json"
    latest_file = target_dir / "system_metrics_latest.json"

    json_content = json.dumps(data, indent=2)
    timestamped_file.write_text(json_content, encoding="utf-8")
    latest_file.write_text(json_content, encoding="utf-8")

    return timestamped_file


def get_latest_metrics_file(logs_dir: Optional[Path] = None, max_age_seconds: int = 300) -> Optional[Path]:
    """
    Retrieve the latest metrics JSON file from logs directory.
    If latest.json is newer than max_age_seconds (default 5 min), returns it immediately.
    Otherwise fetches fresh from remote history endpoint.
    """
    target_dir = logs_dir or DEFAULT_LOGS_DIR
    latest_file = target_dir / "system_metrics_latest.json"

    if latest_file.exists():
        import time
        file_age = time.time() - latest_file.stat().st_mtime
        if file_age <= max_age_seconds:
            return latest_file

    # Try fetching fresh
    try:
        data = fetch_metrics_history()
        return store_metrics_json(data, target_dir)
    except Exception as exc:
        logger.warning(f"Failed to fetch fresh metrics, falling back to existing file: {exc}")
        if latest_file.exists():
            return latest_file
        json_files = sorted(target_dir.glob("system_metrics_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return json_files[0] if json_files else None



def extract_metric_series(raw_history: List[Dict[str, Any]], metric_type: str = "cpu") -> List[Dict[str, Any]]:
    """
    Extracts structured records for a specific resource type:
    - 'cpu': cpu.total, cpu.cores, cpu.per_core
    - 'disk': disk.percent, disk.used_gb, disk.total_gb, disk.free_gb
    - 'ram'/'memory': ram.percent, ram.used_gb, ram.total_gb, ram.available_gb
    """
    metric_type = metric_type.lower()
    records = []

    for idx, entry in enumerate(raw_history):
        timestamp = entry.get("timestamp", "")
        hostname = _first_value(entry, "hostname", "host", "vm_name", "instance_name", default="unknown-host")
        service_name = _first_value(
            entry,
            "service_name",
            "service",
            "application",
            "app",
            "application_name",
            "process_name",
            "process",
            default=hostname if hostname != "unknown-host" else "vm-host",
        )
        uptime = entry.get("uptime", "")

        if metric_type == "cpu":
            cpu_info = entry.get("cpu") or {}
            per_core = [float(c) for c in cpu_info.get("per_core", [])]
            reported_total = float(cpu_info.get("total", 0.0) or 0.0)
            total_usage = (sum(per_core) / len(per_core)) if per_core and reported_total <= 0 else reported_total
            records.append({
                "record_id": f"cpu_rec_{idx+1:04d}",
                "timestamp": timestamp,
                "hostname": hostname,
                "service_name": service_name,
                "process_name": entry.get("process_name") or entry.get("process"),
                "status": entry.get("status", "unknown"),
                "uptime": uptime,
                "metric_type": "SYSTEM_CPU_USAGE",
                "usage_percent": total_usage,
                "cores": int(cpu_info.get("cores", 1)),
                "per_core": per_core,
            })
        elif metric_type in ["disk", "storage"]:
            disk_info = entry.get("disk") or {}
            records.append({
                "record_id": f"disk_rec_{idx+1:04d}",
                "timestamp": timestamp,
                "hostname": hostname,
                "service_name": service_name,
                "process_name": entry.get("process_name") or entry.get("process"),
                "status": entry.get("status", "unknown"),
                "uptime": uptime,
                "metric_type": "SYSTEM_DISK_USAGE",
                "usage_percent": float(disk_info.get("percent", 0.0)),
                "used_gb": float(disk_info.get("used_gb", 0.0)),
                "free_gb": float(disk_info.get("free_gb", 0.0)),
                "total_gb": float(disk_info.get("total_gb", 0.0)),
            })
        elif metric_type in ["ram", "memory"]:
            ram_info = entry.get("ram") or {}
            records.append({
                "record_id": f"ram_rec_{idx+1:04d}",
                "timestamp": timestamp,
                "hostname": hostname,
                "service_name": service_name,
                "process_name": entry.get("process_name") or entry.get("process"),
                "status": entry.get("status", "unknown"),
                "uptime": uptime,
                "metric_type": "SYSTEM_RAM_USAGE",
                "usage_percent": float(ram_info.get("percent", 0.0)),
                "used_gb": float(ram_info.get("used_gb", 0.0)),
                "available_gb": float(ram_info.get("available_gb", 0.0)),
                "total_gb": float(ram_info.get("total_gb", 0.0)),
            })

    return records


def _first_value(record: Dict[str, Any], *keys: str, default: str = "") -> str:
    """Return the first non-empty metadata value from a VM telemetry record."""
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default
