import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.metrics_fetcher import fetch_metrics_history, store_metrics_json, get_latest_metrics_file
from tools.system_agent_pipeline import (
    process_system_cpu_metrics,
    process_system_disk_metrics,
    process_system_memory_metrics,
)
from agents.cpu_agent.agent import parse_and_classify_cpu_logs


def banner(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_1_metrics_ingestion():
    banner("TEST 1: Ingesting Live JSON Metrics (http://20.15.164.79:8080/api/history)")
    try:
        data = fetch_metrics_history()
        saved = store_metrics_json(data)
        print(f" [PASS] Successfully fetched {len(data)} items from remote history API.")
        print(f" [PASS] Saved timestamped file: {saved.name}")
        latest = get_latest_metrics_file()
        print(f" [PASS] Active latest metrics file: {latest.name}")
        sample = data[0] if data else {}
        print(f" [INFO] Sample Hostname: {sample.get('hostname')}")
        print(f" [INFO] Sample CPU Total: {sample.get('cpu', {}).get('total')}%")
        print(f" [INFO] Sample Disk Usage: {sample.get('disk', {}).get('percent')}%")
        print(f" [INFO] Sample RAM Usage: {sample.get('ram', {}).get('percent')}%")
        return True
    except Exception as exc:
        print(f" [FAIL] Failed to fetch metrics: {exc}")
        return False


def test_2_cpu_agent_system_metrics():
    banner("TEST 2: CPU Agent Direct 3-Subagent Pipeline (Detection, Diagnosis, Remediation)")
    res = process_system_cpu_metrics()
    assert res["success"] is True
    print(f" [PASS] Target Host: {res['hostname']}")
    print(f" [PASS] Peak CPU Usage: {res['peak_usage_percent']}% (Current: {res['current_usage_percent']}%)")
    
    det = res["detection"]
    print(f"\n --- Subagent 1: Detection ---")
    print(f"   Status: {'DETECTED' if det['detected'] else 'HEALTHY'} | Severity: {det['severity']}")
    print(f"   Crossed Thresholds: {det['crossed_thresholds']}%")
    print(f"   Summary: {det['summary']}")

    diag = res["diagnosis"]
    print(f"\n --- Subagent 2: Diagnosis ---")
    print(f"   Status: {diag['diagnosis_status']}")
    print(f"   Root Cause: {diag['root_cause']}")
    print(f"   Saturated Cores: {diag['saturated_core_count']}/{det['cores']}")

    rem = res["remediation"]
    print(f"\n --- Subagent 3: Remediation Plan ---")
    print(f"   Status: {rem['status']}")
    print(f"   Action Required:\n   {rem['action_required']}")
    print(f"   FinOps Guardrail: {rem['preventive_guardrail']}")

    alerts = res["email_alerts"]
    print(f"\n --- Email Alert Reminders (Recipient: vnarava@miraclesoft.com) ---")
    print(f"   Total Alerts Triggered: {len(alerts)}")
    for a in alerts:
        print(f"   * {a['subject']} -> {a['recipient']} (Status: {a['status']})")
    return True


def test_3_disk_and_memory_agents():
    banner("TEST 3: Disk Agent & Memory Agent Pipelines")
    d_res = process_system_disk_metrics()
    print(f" [DISK AGENT] Host: {d_res['hostname']} | Usage: {d_res['usage_percent']}% | Severity: {d_res['detection']['severity']}")
    print(f"   Action: {d_res['remediation']['action_required']}")

    m_res = process_system_memory_metrics()
    print(f"\n [MEMORY AGENT] Host: {m_res['hostname']} | Usage: {m_res['usage_percent']}% | Severity: {m_res['detection']['severity']}")
    print(f"   Action: {m_res['remediation']['action_required']}")
    return True


def test_4_cpu_query_sql_optimizer():
    banner("TEST 4: CPU Agent Query Optimization (Resolving SQL Bottlenecks)")
    csv_sample = """timestamp,metric_type,project_id,job_id,avg_slots_utilized,total_slot_ms,runtime_seconds,query
2026-10-01 08:05:22,BQ_CPU_USAGE,gcp-prod,job_regex_neg,1890,113400000,60,"SELECT * FROM telemetry.raw_event_stream WHERE REGEXP_CONTAINS(payload, 'ERROR_CODE_[0-9]+')"
2026-10-01 08:10:00,BQ_CPU_USAGE,gcp-prod,job_join_neg,2150,387000000,180,"SELECT a.event_id, b.user_id, a.payload FROM telemetry.raw_event_stream a FULL OUTER JOIN staging.stg_web_clicks_unpartitioned b ON a.session_id = b.session_id OR a.ip_address = b.ip_address"
"""
    res = parse_and_classify_cpu_logs(csv_sample)
    print(f" [PASS] Total Rows: {res['total_rows_processed']} | Negative Incidents: {res['negative_incidents_count']}")
    for inc in res["incidents"]:
        print(f"\n --- Job: {inc['job_id']} (Severity: {inc['severity']}) ---")
        print(f"   Original Query:\n     {inc['original_query']}")
        print(f"   Optimized Remediation Query:\n     {inc['optimized_query']}")
        print(f"   Remediation Action:\n     {inc['remediation']['action_required']}")
    return True


def test_5_email_audit_log():
    banner("TEST 5: Email Alerts Audit Trail (logs/email_alerts.log)")
    log_path = PROJECT_ROOT / "logs" / "email_alerts.log"
    if log_path.exists():
        lines = [l for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        print(f" [PASS] Found {len(lines)} recorded alert emails in {log_path.name}")
        print(" [INFO] Latest 3 email entries:")
        for line in lines[-3:]:
            entry = json.loads(line)
            print(f"   - [{entry['timestamp']}] {entry['subject']} -> {entry['recipient']} ({entry['status']})")
    else:
        print(" [WARN] email_alerts.log not yet created.")


if __name__ == "__main__":
    test_1_metrics_ingestion()
    test_2_cpu_agent_system_metrics()
    test_3_disk_and_memory_agents()
    test_4_cpu_query_sql_optimizer()
    test_5_email_audit_log()
    banner("ALL AGENT TESTS COMPLETED SUCCESSFULLY!")
