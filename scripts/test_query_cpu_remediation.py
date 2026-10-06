import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.orchestrator_agent.agent import orchestrate_log_analysis

csv_path = Path("mock_data/bigquery_cpu_logs.csv")
csv_text = csv_path.read_text(encoding="utf-8")

result = orchestrate_log_analysis(csv_text, filename="bigquery_cpu_logs.csv")

print(f"Total Rows: {result['total_rows_processed']}")
print(f"Healthy Queries: {result['healthy_queries_count']}")
print(f"Negative Incidents: {result['negative_incidents_count']}")
print()

for inc in result["incidents"]:
    print(f"=== JOB ID: {inc['job_id']} (Severity: {inc['severity']}) ===")
    print(f"Original Query:\n  {inc['original_query']}")
    print(f"Optimized Query:\n  {inc['optimized_query']}")
    print(f"Remediation Action:\n  {inc['remediation']['action_required']}")
    print(f"Preventive Guardrail:\n  {inc['remediation']['preventive_guardrail']}")
    print()

from tools.bigquery.results_writer import _flatten_agent_response
for inc in result["incidents"]:
    flat = _flatten_agent_response(inc["job_id"], inc)
    assert flat["job_id"] == inc["job_id"]
    assert flat["remediation_query"] == inc["optimized_query"]
    assert flat["original_query"] == inc["original_query"]

print("ALL PROJECT STORAGE CHECKS PASSED!")
