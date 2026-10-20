import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from main import app

client = TestClient(app)


def test_remediation_decision_reject():
    """Validates that a rejection records cancellation and returns REJECTED status."""
    payload = {
        "action_id": "ACT-TEST-001",
        "decision": "REJECT",
        "action_type": "KILL_PROCESS",
        "target_identifier": "4125",
        "operator_email": "sre@example.com",
        "operator_note": "False positive, process is expected."
    }
    response = client.post("/api/remediation/decision", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "REJECTED"
    assert "rejected" in data["message"].lower()


def test_remediation_guardrail_blocks_system_pids():
    """Validates that killing system PIDs (<= 100) is strictly blocked by guardrails."""
    payload = {
        "action_id": "ACT-TEST-002",
        "decision": "APPROVE",
        "action_type": "KILL_PROCESS",
        "target_identifier": "1",  # init / systemd
        "process_name": "systemd",
        "operator_email": "sre@example.com"
    }
    response = client.post("/api/remediation/decision", json=payload)
    assert response.status_code == 403
    assert "Security Guardrail" in response.json()["detail"]


def test_remediation_guardrail_blocks_protected_daemons():
    """Validates that protected daemons like sshd cannot be terminated."""
    payload = {
        "action_id": "ACT-TEST-003",
        "decision": "APPROVE",
        "action_type": "KILL_PROCESS",
        "target_identifier": "1420",
        "process_name": "sshd",
        "operator_email": "sre@example.com"
    }
    response = client.post("/api/remediation/decision", json=payload)
    assert response.status_code == 403
    assert "protected core system daemon" in response.json()["detail"]


def test_remediation_approved_kill_success():
    """Validates approved kill execution when SSH succeeds."""
    payload = {
        "action_id": "ACT-TEST-004",
        "decision": "APPROVE",
        "action_type": "KILL_PROCESS",
        "target_identifier": "4125",
        "process_name": "python worker.py",
        "signal": 15,
        "operator_email": "sre@example.com"
    }
    mock_result = {
        "success": True,
        "action": "KILL_PROCESS",
        "pid": 4125,
        "process_name": "python worker.py",
        "signal": 15,
        "command": "sudo kill -15 4125",
        "stdout": "",
        "stderr": "",
        "exit_code": 0
    }
    with patch("routers.remediation_router.ssh_remediation.execute_approved_kill", return_value=mock_result):
        response = client.post("/api/remediation/decision", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "EXECUTED"
        assert data["success"] is True


def test_remediation_approved_service_restart_success():
    """Validates approved service restart execution when SSH succeeds."""
    payload = {
        "action_id": "ACT-TEST-005",
        "decision": "APPROVE",
        "action_type": "RESTART_SERVICE",
        "target_identifier": "nginx",
        "operator_email": "sre@example.com"
    }
    mock_result = {
        "success": True,
        "action": "RESTART_SERVICE",
        "service_name": "nginx",
        "command": "sudo systemctl restart nginx",
        "stdout": "ACTIVE",
        "stderr": "",
        "exit_code": 0
    }
    with patch("routers.remediation_router.ssh_remediation.execute_approved_service_restart", return_value=mock_result):
        response = client.post("/api/remediation/decision", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "EXECUTED"
        assert data["success"] is True
