import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from main import app

def main():
    """Run the manual endpoint smoke test without executing during pytest collection."""
    client = TestClient(app)
    csv_path = Path(__file__).resolve().parent.parent / "mock_data" / "bigquery_cpu_logs.csv"
    csv_text = csv_path.read_text(encoding="utf-8")

    response = client.post("/api/orchestrator/analyze", data={"text": csv_text})
    print("STATUS:", response.status_code)
    data = response.json()
    print("DESIGNATED AGENT:", data["designated_agent"])
    print("TOTAL ROWS:", data["total_rows_processed"])
    print("HEALTHY:", data["healthy_queries_count"])
    print("NEGATIVE:", data["negative_incidents_count"])
    for rem in data.get("remediation_summary", []):
        print(f"\n--- {rem['job_id']} ({rem['severity']}) ---")
        print("ORIGINAL:\n ", rem["original_query"])
        print("OPTIMIZED:\n ", rem["optimized_query"])
        print("ACTION:\n ", rem["recommended_action"])
        print("GUARDRAIL:\n ", rem["preventive_guardrail"])


if __name__ == "__main__":
    main()
