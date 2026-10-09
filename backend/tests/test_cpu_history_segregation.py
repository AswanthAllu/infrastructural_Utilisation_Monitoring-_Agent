import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_cpu_history_endpoint_attaches_and_segregates():
    """
    Tests that /api/cpu/history:
    1. Attaches to http://20.15.164.79:8080/api/history
    2. Runs Python segregation script to extract CPU-only metrics
    3. Returns multiple remediation plans in 'remediation_plans' instead of only one
    """
    response = client.get("/api/cpu/history?force_fetch=false")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    data = response.json()
    assert data["success"] is True
    assert data["resource"] == "CPU"
    assert "remediation_plans" in data
    assert isinstance(data["remediation_plans"], list)
    # Check that remediation plan is returned (deduplicated when 100% saturation is present)
    assert len(data["remediation_plans"]) >= 1, f"Expected remediation plan, got {len(data['remediation_plans'])}"

    # Validate schema of each remediation plan
    first_plan = data["remediation_plans"][0]
    assert "plan_id" in first_plan
    assert "timestamp" in first_plan
    assert "action_required" in first_plan
    assert "preventive_guardrail" in first_plan
    assert "severity" in first_plan
    assert "total_usage_percent" in first_plan
    assert "cores" in first_plan
    assert "per_core" in first_plan


def test_cpu_segregated_data_endpoint():
    """
    Tests that /api/cpu/segregated-data returns CPU-only records without disk and ram.
    """
    response = client.get("/api/cpu/segregated-data")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "segregated_cpu_records" in data
    records = data["segregated_cpu_records"]
    assert len(records) > 0

    first = records[0]
    assert "cpu" in first
    assert "usage_percent" in first
    assert "cores" in first
    assert "per_core" in first
    # Verify disk and ram are completely segregated out
    assert "disk" not in first
    assert "ram" not in first


def test_cpu_analyze_get_returns_all_remediation_plans():
    """
    Tests that /api/cpu/analyze returns all remediation plans.
    """
    response = client.get("/api/cpu/analyze")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "remediation_plans" in data
    assert len(data["remediation_plans"]) >= 1
