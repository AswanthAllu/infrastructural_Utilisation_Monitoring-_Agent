import io
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

SAMPLE_CPU_CSV = """timestamp,metric_type,project_id,job_id,avg_slots_utilized,total_slot_ms,runtime_seconds
2026-10-01 10:15:00,BQ_CPU_USAGE,prod-01,job_healthy_001,120.0,250000.0,5.0
2026-10-01 11:20:10,BQ_CPU_USAGE,prod-01,job_slot_exhaust_002,1950.0,85000000.0,80.0
2026-10-01 11:55:00,BQ_CPU_USAGE,prod-01,job_burst_throttle_003,2250.0,120000000.0,95.0
"""

SAMPLE_DISK_CSV = """timestamp,metric_type,project_id,job_id,table_name,total_bytes_processed,total_bytes_billed,is_partitioned,partition_column
2026-10-01 10:00:00,BQ_DISK_USAGE,prod-01,job_disk_001,analytics.events,50000000000,50000000000,true,event_date
"""


def test_analyze_with_file_upload_cpu():
    file_bytes = io.BytesIO(SAMPLE_CPU_CSV.encode("utf-8"))
    response = client.post(
        "/api/orchestrator/analyze",
        files={"file": ("bq_cpu_logs.csv", file_bytes, "text/csv")},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True
    assert data["designated_agent"] == "cpu_agent"
    assert data["total_rows_processed"] == 3
    assert data["healthy_queries_count"] == 1
    assert data["negative_incidents_count"] == 2
    assert len(data["remediation_summary"]) == 2
    for rem in data["remediation_summary"]:
        assert rem["job_id"] in ["job_slot_exhaust_002", "job_burst_throttle_003"]
        assert rem["recommended_action"]


def test_analyze_with_text_form_cpu():
    response = client.post(
        "/api/cpu/analyze",
        data={"text": SAMPLE_CPU_CSV},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True
    assert data["designated_agent"] == "cpu_agent"
    assert data["negative_incidents_count"] == 2


def test_analyze_with_json_body_cpu():
    response = client.post(
        "/api/orchestrator/analyze",
        json={"text": SAMPLE_CPU_CSV, "filename": "bq_cpu_logs.csv"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["designated_agent"] == "cpu_agent"
    assert data["negative_incidents_count"] == 2


def test_analyze_routes_to_disk_agent():
    file_bytes = io.BytesIO(SAMPLE_DISK_CSV.encode("utf-8"))
    response = client.post(
        "/api/orchestrator/analyze",
        files={"file": ("bq_disk_logs.csv", file_bytes, "text/csv")},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["designated_agent"] == "disk_agent"
    assert data["negative_incidents_count"] == 1
    rem = data["remediation_summary"][0]
    assert "require_partition_filter" in rem["preventive_guardrail"]


def test_missing_input_returns_400():
    response = client.post("/api/orchestrator/analyze")
    assert response.status_code == 400
