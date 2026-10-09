import pytest
from pathlib import Path
from agents.cpu_agent.agent import cpu_agent, parse_and_classify_cpu_logs
from agents.disk_agent.agent import disk_agent
from agents.orchestrator_agent.agent import orchestrator_agent, route_incident_workload
from tools.bigquery.results_writer import _flatten_agent_response


SAMPLE_CSV = """timestamp,metric_type,project_id,job_id,avg_slots_utilized,total_slot_ms,runtime_seconds
2026-10-01 10:00:00,BQ_CPU_USAGE,test-proj,healthy_job,100.0,1000000.0,5.0
2026-10-01 10:05:00,BQ_CPU_USAGE,test-proj,critical_job,1900.0,50000000.0,90.0
2026-10-01 10:10:00,BQ_CPU_USAGE,test-proj,burst_job,2100.0,80000000.0,95.0
2026-10-01 10:15:00,BQ_CPU_USAGE,test-proj,hog_job,900.0,600000000.0,150.0
2026-10-01 10:20:00,BQ_CPU_USAGE,test-proj,burst_prune_job,1400.0,80000000.0,70.0
"""


def test_agent_instances_load():
    assert cpu_agent is not None
    assert cpu_agent.instruction
    assert disk_agent is not None
    assert disk_agent.instruction
    assert orchestrator_agent is not None
    # The orchestrator routes CPU, disk, and memory workloads.
    assert len(orchestrator_agent.sub_agents) == 3


def test_orchestrator_routing():
    assert route_incident_workload("bq_cpu_logs.csv") == "cpu_agent"
    assert route_incident_workload("CPU_UTILIZATION") == "cpu_agent"
    assert route_incident_workload("bq_disk_logs.csv") == "disk_agent"
    assert route_incident_workload("storage_bytes_scanned") == "disk_agent"


def test_cpu_log_filtering_and_classification():
    result = parse_and_classify_cpu_logs(SAMPLE_CSV)
    assert result["success"] is True
    assert result["total_rows_processed"] == 5
    assert result["healthy_queries_count"] == 1
    assert result["negative_incidents_count"] == 4

    incident_map = {inc["job_id"]: inc for inc in result["incidents"]}
    
    # Critical slot exhaustion
    crit = incident_map["critical_job"]
    assert crit["severity"] == "CRITICAL"
    assert crit["detection"]["detected"] is True
    assert crit["diagnosis"]["diagnosis_status"] == "CONFIRMED"
    assert "Risk of hitting the 2,000 on-demand slot ceiling" in crit["diagnosis"]["root_cause"]

    # Burst throttling remediation
    burst = incident_map["burst_job"]
    assert burst["severity"] == "CRITICAL"
    assert "concurrency controls" in burst["remediation"]["action_required"].lower()

    # Long running compute hog
    hog = incident_map["hog_job"]
    assert hog["severity"] == "HIGH"
    assert "Excessive computational burn" in hog["diagnosis"]["root_cause"]

    # Insufficient pruning
    prune = incident_map["burst_prune_job"]
    assert prune["severity"] == "MEDIUM"


def test_project_schema_compatibility():
    result = parse_and_classify_cpu_logs(SAMPLE_CSV)
    for inc in result["incidents"]:
        flattened = _flatten_agent_response(inc["job_id"], inc)
        assert flattened["job_id"] == inc["job_id"]
        assert flattened["detection_status"] == "DETECTED"
        assert flattened["diagnosis_status"] == "CONFIRMED"
        assert flattened["remediation_status"] == "REMEDIATION_DRAFTED"
        assert flattened["remediation_recommendation"] == inc["remediation"]["action_required"]
