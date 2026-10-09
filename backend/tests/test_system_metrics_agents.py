import io
import json
import pytest
from fastapi.testclient import TestClient
from main import app
from tools.system_agent_pipeline import (
    process_system_cpu_metrics,
    process_system_disk_metrics,
    process_system_memory_metrics,
)
from tools.metrics_fetcher import extract_metric_series

client = TestClient(app)

SAMPLE_HISTORY_ENTRY = [
    {
        "cpu": {
            "cores": 2,
            "per_core": [100.0, 100.0],
            "total": 100.0
        },
        "disk": {
            "free_gb": 120.76,
            "percent": 1.8,
            "total_gb": 122.95,
            "used_gb": 2.17
        },
        "hostname": "cpu-utilization-vm",
        "ram": {
            "available_gb": 6.93,
            "percent": 10.1,
            "total_gb": 7.7,
            "used_gb": 0.78
        },
        "timestamp": "2026-10-02T10:54:17.897240+00:00",
        "uptime": "2026-10-02 10:18:43"
    }
]


def test_cpu_agent_system_metrics_pipeline():
    res = process_system_cpu_metrics(source=SAMPLE_HISTORY_ENTRY)
    assert res["success"] is True
    assert res["resource"] == "CPU"
    assert res["peak_usage_percent"] == 100.0
    
    # 3 subagents check
    assert res["detection"]["subagent"] == "detection_agent"
    assert res["detection"]["detected"] is True
    assert 100 in res["detection"]["crossed_thresholds"]
    assert 70 in res["detection"]["crossed_thresholds"]
    assert 50 in res["detection"]["crossed_thresholds"]

    assert res["diagnosis"]["subagent"] == "diagnosis_agent"
    assert "Full CPU saturation" in res["diagnosis"]["root_cause"]
    assert res["diagnosis"]["severity"] == "CRITICAL"

    assert res["remediation"]["subagent"] == "remediation_agent"
    assert "scale host" in res["remediation"]["action_required"].lower()

    # Email alerts check: single highest limit crossed (100% when usage is 100%) to sirivennelanarava@gmail.com
    assert len(res["email_alerts"]) == 1
    alert = res["email_alerts"][0]
    assert alert["threshold"] == 100
    assert "Limit crossed 100% CPU usage" in alert["subject"]
    assert alert["recipient"] == "sirivennelanarava@gmail.com"


def test_disk_agent_system_metrics_pipeline():
    res = process_system_disk_metrics(source=SAMPLE_HISTORY_ENTRY)
    assert res["success"] is True
    assert res["resource"] == "Disk"
    assert res["detection"]["subagent"] == "detection_agent"
    assert res["diagnosis"]["subagent"] == "diagnosis_agent"
    assert res["remediation"]["subagent"] == "remediation_agent"


def test_memory_agent_system_metrics_pipeline():
    res = process_system_memory_metrics(source=SAMPLE_HISTORY_ENTRY)
    assert res["success"] is True
    assert res["resource"] == "RAM"
    assert res["detection"]["subagent"] == "detection_agent"
    assert res["diagnosis"]["subagent"] == "diagnosis_agent"
    assert res["remediation"]["subagent"] == "remediation_agent"


def test_api_cpu_analyze_direct_get():
    # Hitting GET /api/cpu/analyze directly consumes latest JSON and runs 3 subagents
    response = client.get("/api/cpu/analyze")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True
    assert data["resource"] == "CPU"
    assert "detection" in data
    assert "diagnosis" in data
    assert "remediation" in data


def test_api_disk_analyze_direct_get():
    response = client.get("/api/disk/analyze")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["resource"] == "Disk"


def test_api_memory_analyze_direct_get():
    response = client.get("/api/memory/analyze")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["resource"] == "RAM"


def test_api_metrics_alerts_endpoint():
    response = client.get("/api/metrics/alerts")
    assert response.status_code == 200
    data = response.json()
    assert "alerts" in data
