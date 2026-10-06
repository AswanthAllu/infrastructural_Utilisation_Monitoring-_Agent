"""
Standalone Python Preprocessing Script:
1. Fetches system history metrics from http://20.15.164.79:8080/api/history (or local cache).
2. Segregates CPU-only data (stripping disk, ram, etc.).
3. Formulates individualized remediation plans for EVERY problematic CPU record.
4. Saves segregated data to logs/cpu_metrics_segregated.json.
5. Invokes CPU agent evaluation pipeline and outputs results.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.metrics_fetcher import fetch_metrics_history, get_latest_metrics_file
from tools.cpu_preprocessor import (
    segregate_cpu_data,
    generate_all_cpu_remediation_plans,
    save_segregated_cpu_data,
)
from tools.system_agent_pipeline import process_system_cpu_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("segregate_cpu_data")


def run_cpu_segregation_pipeline(
    url: str = "http://20.15.164.79:8080/api/history",
    output_path: str = None,
    save_segregated: bool = True,
):
    print("=" * 80)
    print(f"STEP 1: Fetching system history telemetry from: {url}")
    print("=" * 80)
    try:
        raw_telemetry = fetch_metrics_history(url)
        print(f"--> Successfully retrieved {len(raw_telemetry)} raw metric telemetry entries.")
    except Exception as exc:
        print(f"[!] Warning: Remote fetch failed ({exc}). Falling back to latest local cached JSON.")
        cached_file = get_latest_metrics_file()
        if not cached_file or not cached_file.exists():
            print("[x] Error: No local cache available.")
            sys.exit(1)
        raw_telemetry = json.loads(cached_file.read_text(encoding="utf-8"))
        print(f"--> Loaded {len(raw_telemetry)} entries from {cached_file.name}.")

    print("\n" + "=" * 80)
    print("STEP 2: Executing Python script to segregate CPU-related data only")
    print("        (Stripping out all Disk, RAM, and non-CPU metrics)")
    print("=" * 80)
    segregated_cpu = segregate_cpu_data(raw_telemetry)
    print(f"--> Segregated {len(segregated_cpu)} CPU metric records.")
    if segregated_cpu:
        sample = segregated_cpu[0]
        print(f"--> Sample Segregated CPU Record: {json.dumps(sample, indent=2)}")

    if save_segregated:
        saved_file = save_segregated_cpu_data(segregated_cpu)
        print(f"--> Saved segregated CPU dataset to: {saved_file}")

    print("\n" + "=" * 80)
    print("STEP 3: Passing segregated CPU data to CPU Agent Pipeline")
    print("        (Detection -> Diagnosis -> Multi-Plan Remediation)")
    print("=" * 80)
    result = process_system_cpu_metrics(source=raw_telemetry)

    remediation_plans = result.get("remediation_plans", [])
    print(f"\n--> TOTAL REMEDIATION PLANS GENERATED: {len(remediation_plans)}")
    print("-" * 80)
    for idx, plan in enumerate(remediation_plans, 1):
        print(f"[{idx}] Plan ID: {plan['plan_id']} | Severity: {plan['severity']} | Timestamp: {plan['timestamp']}")
        print(f"    Usage: {plan['total_usage_percent']}% across {plan['cores']} cores | Per Core: {plan['per_core']}")
        print(f"    Root Cause: {plan['root_cause']}")
        print(f"    Action Required:\n    {plan['action_required']}")
        print(f"    Guardrail: {plan['preventive_guardrail']}")
        print("-" * 80)

    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"--> Full analysis and remediation plans exported to: {out_file}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Segregate CPU telemetry and generate multi-incident remediation plans.")
    parser.add_argument("--url", default="http://20.15.164.79:8080/api/history", help="Remote telemetry URL")
    parser.add_argument("--output", default=None, help="Optional output JSON path for the results")
    args = parser.parse_args()

    run_cpu_segregation_pipeline(url=args.url, output_path=args.output)
