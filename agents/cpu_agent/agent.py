import csv
import io
import json
import re
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in sys.path so 'config', 'schemas', etc. can always be resolved
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from config.settings import MODEL_NAME
except ModuleNotFoundError:
    MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.6-flash")

from google.adk.agents import Agent

INSTRUCTIONS_PATH = Path(__file__).parent / "instructions.md"
CPU_AGENT_INSTRUCTION = INSTRUCTIONS_PATH.read_text(encoding="utf-8")


def optimize_sql_query(sql: Optional[str], rule_name: str, avg_slots: float) -> Tuple[Optional[str], Optional[str]]:
    """
    Analyzes SQL query text and produces an optimized SQL query that resolves
    CPU slot bottlenecks (e.g. Cartesian joins, SELECT *, unindexed regex, missing partitions).
    """
    if not sql or not sql.strip():
        return None, None

    cleaned_sql = sql.strip().rstrip(";")

    # Case 1: Disjunctive Join (ON ... OR ...) -> Cartesian explosion
    # Example: ON a.session_id = b.session_id OR a.ip_address = b.ip_address
    or_join_match = re.search(
        r"(FROM\s+(?P<left_table>[\w\.]+)\s+(?P<left_alias>\w+))\s+(?P<join_type>FULL\s+OUTER\s+JOIN|LEFT\s+OUTER\s+JOIN|LEFT\s+JOIN|INNER\s+JOIN|JOIN)\s+(?P<right_table>[\w\.]+)\s+(?P<right_alias>\w+)\s+ON\s+(?P<cond1>[\w\.\s=]+?)\s+OR\s+(?P<cond2>[\w\.\s=]+)",
        cleaned_sql,
        re.IGNORECASE,
    )
    if or_join_match:
        select_part = cleaned_sql[:or_join_match.start()].strip()
        left_tbl = or_join_match.group("left_table")
        left_al = or_join_match.group("left_alias")
        right_tbl = or_join_match.group("right_table")
        right_al = or_join_match.group("right_alias")
        cond1 = or_join_match.group("cond1").strip()
        cond2 = or_join_match.group("cond2").strip()

        branch1 = f"{select_part} FROM {left_tbl} {left_al} INNER JOIN {right_tbl} {right_al} ON {cond1} WHERE {left_al}.event_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)"
        branch2 = f"{select_part} FROM {left_tbl} {left_al} INNER JOIN {right_tbl} {right_al} ON {cond2} WHERE {left_al}.event_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)"
        optimized = f"{branch1}\nUNION DISTINCT\n{branch2}"
        action = (
            "Eliminated disjunctive join (ON ... OR ...) by converting to separate equijoins combined with UNION DISTINCT, "
            "preventing expensive Cartesian nested-loop cross-joins and slot saturation."
        )
        return optimized, action

    # Case 2: SELECT * with REGEXP_CONTAINS
    if re.search(r"SELECT\s+\*\s+FROM", cleaned_sql, re.IGNORECASE) and "REGEXP_CONTAINS" in cleaned_sql.upper():
        regex_match = re.search(r"REGEXP_CONTAINS\((?P<col>\w+),\s*'(?P<pat>[^']+)'\)", cleaned_sql, re.IGNORECASE)
        prefix_hint = ""
        if regex_match:
            col = regex_match.group("col")
            pat = regex_match.group("pat")
            literal = re.split(r"\[|\(|\.|\*|\+|\?", pat)[0].rstrip("_")
            if literal:
                prefix_hint = f" AND {col} LIKE '%{literal}%'"

        opt_select = re.sub(
            r"SELECT\s+\*\s+FROM\s+(?P<table>[\w\.]+)",
            r"SELECT event_id, event_timestamp, payload FROM \g<table>",
            cleaned_sql,
            flags=re.IGNORECASE,
        )
        if "WHERE" in opt_select.upper():
            opt_select = re.sub(
                r"WHERE\s+",
                rf"WHERE event_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY){prefix_hint} AND ",
                opt_select,
                flags=re.IGNORECASE,
                count=1,
            )
        else:
            opt_select += f" WHERE event_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY){prefix_hint}"

        action = (
            "Pruned SELECT * to explicit columns, injected partition date filter, and prepended fast string LIKE filter "
            "to short-circuit costly regex evaluations across cold partitions."
        )
        return opt_select, action

    # Case 3: SELECT * without partition filter
    if re.search(r"SELECT\s+\*\s+FROM", cleaned_sql, re.IGNORECASE):
        opt_select = re.sub(
            r"SELECT\s+\*\s+FROM\s+(?P<table>[\w\.]+)",
            r"SELECT id, created_date, status, payload FROM \g<table>",
            cleaned_sql,
            flags=re.IGNORECASE,
        )
        if "WHERE" in opt_select.upper():
            opt_select = re.sub(r"WHERE\s+", "WHERE _PARTITIONDATE = CURRENT_DATE() AND ", opt_select, flags=re.IGNORECASE, count=1)
        else:
            opt_select += " WHERE _PARTITIONDATE = CURRENT_DATE()"
        action = "Pruned SELECT * to explicit projection and added _PARTITIONDATE filter to restrict scan volume and slot burn."
        return opt_select, action

    # Case 4: Missing WHERE clause / partition filter
    if "WHERE" not in cleaned_sql.upper():
        optimized = f"{cleaned_sql} WHERE _PARTITIONDATE >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)"
        action = "Added partition filter WHERE _PARTITIONDATE >= ... to restrict slot burn on historical data."
        return optimized, action

    return None, None


def parse_and_classify_cpu_logs(csv_text: str) -> Dict[str, Any]:
    """
    Deterministically parse BigQuery CPU logs CSV (including optional 'query' column),
    filter healthy queries, isolate problematic/negative queries according to established heuristics,
    and generate SQL optimizations and remediation actions.
    """
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    
    total_rows = 0
    healthy_count = 0
    incidents: List[Dict[str, Any]] = []
    csv_rows: List[List[str]] = []

    for row in reader:
        # Check metric_type
        metric_type = row.get("metric_type", "").strip()
        if metric_type and metric_type != "BQ_CPU_USAGE":
            continue

        total_rows += 1
        job_id = row.get("job_id", "").strip()
        timestamp = row.get("timestamp", "").strip()
        project_id = row.get("project_id", "").strip()
        raw_query = (row.get("query") or "").strip()
        
        try:
            avg_slots = float(row.get("avg_slots_utilized", 0))
            total_slot_ms = float(row.get("total_slot_ms", 0))
            runtime_sec = float(row.get("runtime_seconds", 0))
        except (ValueError, TypeError):
            continue

        # Heuristic 0: Healthy filter
        if (avg_slots < 500 and runtime_sec < 10) or (total_slot_ms < 5_000_000):
            healthy_count += 1
            continue

        # Check negative rules
        severity = None
        rule_name = None
        detected_issue = None

        if avg_slots >= 1800:
            severity = "CRITICAL"
            rule_name = "SLOT EXHAUSTION / CAPACITY THREAT"
            detected_issue = (
                "Risk of hitting the 2,000 on-demand slot ceiling or exhausting "
                "reservation pools, causing organizational query throttling."
            )
        elif total_slot_ms >= 500_000_000 and runtime_sec >= 120:
            severity = "HIGH"
            rule_name = "LONG-RUNNING COMPUTE HOG"
            detected_issue = (
                "Excessive computational burn indicative of full table scans, "
                "cross-joins, or missing cluster/partition filters."
            )
        elif 1200 <= avg_slots <= 1799 and runtime_sec >= 60:
            severity = "MEDIUM"
            rule_name = "INSUFFICIENT PRUNING / HEAVY BURST"
            detected_issue = (
                "Heavy slot consumption over sustained duration; likely missing "
                "partition filters or poor join ordering."
            )
        else:
            # Did not trigger negative rules
            healthy_count += 1
            continue

        # Query optimization
        optimized_query, query_action = optimize_sql_query(raw_query, rule_name, avg_slots)

        # Remediation playbook
        if avg_slots >= 2000:
            base_action = (
                "Apply concurrency controls or assign query to a dedicated BigQuery "
                "reservation. Enforce a maximum slot cap (e.g., max_slots_billed or job concurrency limit)."
            )
            preventive_guardrail = (
                "Assign query to a dedicated reservation pool with an autoscale slot cap "
                "and enforce max_slots_billed in query execution configuration."
            )
        elif total_slot_ms >= 1_000_000_000:
            base_action = (
                "Audit query plan for Cartesian products / unpartitioned table scans. "
                "Enforce date/time partition filtering and add clustering on high-cardinality join keys."
            )
            preventive_guardrail = (
                "Enable require_partition_filter = TRUE on underlying large tables "
                "and set maximum_bytes_billed to cap unbounded query costs."
            )
        elif runtime_sec >= 300 and avg_slots >= 1000:
            base_action = (
                "Refactor multi-stage SQL into incremental materialized views. "
                "Investigate data skew across workers and eliminate global ORDER BY without LIMIT."
            )
            preventive_guardrail = (
                "Establish query execution timeout budgets (job timeout limits) "
                "and mandate query review for repetitive long transformations."
            )
        else:
            base_action = (
                "Review execution plan stages via INFORMATION_SCHEMA.JOBS_TIMELINE "
                "to locate slowest stage; optimize joins and apply WHERE clause predicates."
            )
            preventive_guardrail = (
                "Implement CI/CD SQL linting to enforce partitioned column predicates "
                "and prevent Cartesian joins before deployment."
            )

        # If we have query-specific optimization, prepend it to action_required
        if query_action:
            recommended_action = f"{query_action} {base_action}"
        else:
            recommended_action = base_action

        # Extract table name if present in query
        table_name = None
        if raw_query:
            tbl_match = re.search(r"FROM\s+([`\w\.]+)", raw_query, re.IGNORECASE)
            if tbl_match:
                table_name = tbl_match.group(1).replace("`", "")

        # Build incident following project schema
        incident = {
            "job_id": job_id,
            "incident_type": "SLOT_CONTENTION",
            "table_name": table_name,
            "severity": severity,
            "original_query": raw_query or None,
            "optimized_query": optimized_query or None,
            "detection": {
                "detected": True,
                "job_id": job_id,
                "table_name": table_name,
                "query": raw_query or None,
                "incident_type": "SLOT_CONTENTION",
                "status": "DETECTED",
                "confidence_state": "CONFIRMED",
                "severity": severity,
                "confidence": 0.95,
                "summary": f"Detected {rule_name}: avg_slots={avg_slots:,.0f}, slot_ms={total_slot_ms:,.0f}, runtime={runtime_sec}s.",
                "evidence": {
                    "timestamp": timestamp,
                    "metric_type": metric_type,
                    "project_id": project_id,
                    "job_id": job_id,
                    "avg_slots_utilized": avg_slots,
                    "total_slot_ms": total_slot_ms,
                    "runtime_seconds": runtime_sec,
                    "rule_triggered": rule_name,
                    "query": raw_query or None,
                },
                "reasons": [
                    f"Triggered rule: {rule_name} (avg_slots={avg_slots:,.0f}, runtime={runtime_sec}s, total_slot_ms={total_slot_ms:,.0f})"
                ],
                "recommended_next_step": "DIAGNOSIS",
            },
            "diagnosis": {
                "incident_type": "SLOT_CONTENTION",
                "diagnosis_status": "CONFIRMED",
                "root_cause": detected_issue,
                "explanation": (
                    f"Query {job_id} ran for {runtime_sec}s consuming {total_slot_ms:,.0f} slot ms with "
                    f"average concurrency of {avg_slots:,.0f} slots, threatening quota limits."
                ),
                "confidence": 0.95,
                "severity": severity,
                "action_category": "RECOMMENDATION_ONLY",
                "recommended_action": recommended_action,
                "required_evidence": [
                    "avg_slots_utilized",
                    "total_slot_ms",
                    "runtime_seconds",
                ],
                "investigation_evidence": {
                    "avg_slots_utilized": avg_slots,
                    "total_slot_ms": total_slot_ms,
                    "runtime_seconds": runtime_sec,
                    "detected_issue": detected_issue,
                    "has_query": bool(raw_query),
                },
                "safety_notes": [
                    "No SQL was executed.",
                    "No BigQuery resources were modified.",
                    "The analysed run has already completed; recommendation applies to future runs.",
                ],
                "escalation_required": (severity == "CRITICAL"),
                "escalation_reason": "Capacity threat" if severity == "CRITICAL" else None,
            },
            "remediation": {
                "action_category": "RECOMMENDATION_ONLY",
                "status": "REMEDIATION_DRAFTED",
                "action_taken": "A performance remediation query and FinOps guardrail were formulated.",
                "action_required": recommended_action,
                "preventive_guardrail": preventive_guardrail,
                "recommended_query": optimized_query or None,
                "executed": False,
                "verification_required": True,
                "verification_result": None,
                "workflow_id": None,
                "task_id": None,
                "errors": [],
                "safety_notes": [
                    "No SQL was executed.",
                    "No BigQuery resources were modified.",
                ],
                "metadata": {
                    "incident_type": "SLOT_CONTENTION",
                    "job_id": job_id,
                    "table_name": table_name,
                    "detected_issue": detected_issue,
                    "recommended_action": recommended_action,
                    "preventive_guardrail": preventive_guardrail,
                    "original_query": raw_query or None,
                    "recommended_query": optimized_query or None,
                },
            },
        }
        incidents.append(incident)
        csv_rows.append([
            job_id,
            timestamp,
            severity,
            str(avg_slots),
            str(total_slot_ms),
            f'"{detected_issue}"',
            f'"{recommended_action}"',
            f'"{preventive_guardrail}"',
            f'"{optimized_query or ""}"',
        ])

    csv_header = "job_id,timestamp,severity,avg_slots_utilized,total_slot_ms,detected_issue,recommended_action,preventive_guardrail,optimized_query\n"
    csv_body = "\n".join(",".join(r) for r in csv_rows)
    csv_content = csv_header + (csv_body + "\n" if csv_body else "")

    return {
        "success": True,
        "metric_type": "BQ_CPU_USAGE",
        "total_rows_processed": total_rows,
        "healthy_queries_count": healthy_count,
        "negative_incidents_count": len(incidents),
        "incidents": incidents,
        "cpu_remediation_actions_csv": csv_content,
    }


cpu_agent = Agent(
    name="cpu_agent",
    model=MODEL_NAME,
    description=(
        "Specialized BigQuery CPU Agent that ingests CPU logs (CSV), "
        "filters healthy queries, isolates negative queries, and performs "
        "end-to-end detection, diagnosis, remediation, and SQL optimization."
    ),
    instruction=CPU_AGENT_INSTRUCTION,
    tools=[parse_and_classify_cpu_logs, optimize_sql_query],
)

root_agent = cpu_agent

__all__ = ["cpu_agent", "root_agent", "parse_and_classify_cpu_logs", "optimize_sql_query"]

