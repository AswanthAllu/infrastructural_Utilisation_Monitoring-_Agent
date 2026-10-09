import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.cpu_agent.agent import parse_and_classify_cpu_logs, cpu_agent
from agents.disk_agent.agent import disk_agent
from agents.orchestrator_agent.agent import orchestrator_agent

print("1. Testing agent loading...")
assert cpu_agent is not None, "cpu_agent failed to load"
assert disk_agent is not None, "disk_agent failed to load"
assert orchestrator_agent is not None, "orchestrator_agent failed to load"
print("   All agents loaded successfully.")

print("\n2. Testing parse_and_classify_cpu_logs with mock_data/bigquery_cpu_logs.csv...")
csv_path = Path("mock_data/bigquery_cpu_logs.csv")
if not csv_path.exists():
    print("   mock_data/bigquery_cpu_logs.csv does not exist!")
else:
    csv_text = csv_path.read_text(encoding="utf-8")
    result = parse_and_classify_cpu_logs(csv_text)
    print(f"   Total rows: {result['total_rows_processed']}")
    print(f"   Healthy count: {result['healthy_queries_count']}")
    print(f"   Negative incidents count: {result['negative_incidents_count']}")
    for inc in result["incidents"]:
        print(f"   - Job: {inc['job_id']} | Severity: {inc['severity']} | Rule: {inc['detection']['evidence']['rule_triggered']}")
        print(f"     Diagnosis Root Cause: {inc['diagnosis']['root_cause'][:60]}...")
        print(f"     Remediation Action: {inc['remediation']['action_required'][:60]}...")
        print(f"     Preventive Guardrail: {inc['remediation']['preventive_guardrail'][:60]}...")
        print()

    print("3. Validating project schema compatibility...")
    from tools.bigquery.results_writer import _flatten_agent_response
    for inc in result["incidents"]:
        flattened = _flatten_agent_response(inc["job_id"], inc)
        assert flattened["job_id"] == inc["job_id"]
        assert flattened["severity"] == inc["severity"]
        assert flattened["detection_status"] == "DETECTED"
        assert flattened["diagnosis_status"] == "CONFIRMED"
        assert flattened["remediation_status"] == "REMEDIATION_DRAFTED"
    print("   All incidents cleanly match project storage schema!")
    print("\nSUCCESS!")
