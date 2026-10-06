import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.system_agent_pipeline import process_system_cpu_metrics
print("Starting...")
res = process_system_cpu_metrics()
print("Success:", res["success"])
print("Peak Usage:", res["peak_usage_percent"])
print("Detection Summary:", res["detection"]["summary"])
print("Diagnosis Root Cause:", res["diagnosis"]["root_cause"])
print("Email Alerts:", len(res["email_alerts"]))
for alert in res["email_alerts"]:
    print(f"  Alert: {alert['subject']} -> {alert['recipient']} (Status: {alert['status']})")
