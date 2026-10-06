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
DEFAULT_LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


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
