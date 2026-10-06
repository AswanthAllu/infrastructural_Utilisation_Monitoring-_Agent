import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
csv_text = Path("mock_data/bigquery_cpu_logs.csv").read_text(encoding="utf-8")

response = client.post("/api/orchestrator/analyze", data={"text": csv_text})
print("STATUS:", response.status_code)
data = response.json()
print("DESIGNATED AGENT:", data["designated_agent"])
print("TOTAL ROWS:", data["total_rows_processed"])
print("HEALTHY:", data["healthy_queries_count"])
print("NEGATIVE:", data["negative_incidents_count"])
for rem in data["remediation_summary"]:
    print(f"\n--- {rem['job_id']} ({rem['severity']}) ---")
    print("ORIGINAL:\n ", rem["original_query"])
    print("OPTIMIZED:\n ", rem["optimized_query"])
    print("ACTION:\n ", rem["recommended_action"])
    print("GUARDRAIL:\n ", rem["preventive_guardrail"])
