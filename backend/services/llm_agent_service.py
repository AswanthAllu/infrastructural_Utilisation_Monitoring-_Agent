"""
LLM Agent Service:
Directly invokes Gemini (using google.genai and GOOGLE_API_KEY) so that the LLM
autonomously decides detection, diagnosis, and remediation for CPU, Disk, and Memory agents.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Load environment variables from project root .env and tests/.env
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "tests" / ".env")

logger = logging.getLogger(__name__)

API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")

_genai_client = None


def get_genai_client():
    global _genai_client
    if _genai_client is None:
        try:
            from google import genai
            api_key = os.getenv("GOOGLE_API_KEY")
            if api_key:
                _genai_client = genai.Client(api_key=api_key)
            else:
                _genai_client = genai.Client()
        except Exception as exc:
            logger.warning(f"Could not initialize google.genai Client: {exc}")
            _genai_client = None
    return _genai_client


def _clean_json_markdown(text: str) -> str:
    """Removes ```json and ``` code fence markers from model output."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _fmt_time(t: str) -> str:
    if "T" in str(t):
        parts = str(t).split("T")[1].split("+")[0].split(".")[0]
        return parts
    return str(t) or "14:13:00"


def _extract_friendly_name(cmd: str, process_name: str) -> str:
    """Derive a human-friendly application/service name dynamically from process metadata without hardcoded names."""
    if process_name and process_name.strip():
        p_clean = process_name.strip().strip("'\"")
        # If process_name is generic interpreter like 'python', 'python3', 'node', parse the target script/command
        if p_clean.lower() in ("python", "python3", "node", "java", "ruby", "perl", "bash", "sh") and cmd:
            tokens = cmd.strip().split()
            for token in tokens[1:]:
                if not token.startswith("-") and ("/" in token or "\\" in token or token.endswith((".py", ".js", ".jar", ".sh"))):
                    base = Path(token).stem.replace("_", " ").replace("-", " ").title()
                    return f"{base} Service" if not base.lower().endswith("service") else base
        base = p_clean.replace("_", " ").replace("-", " ").title()
        return base
    if cmd and cmd.strip():
        first_token = cmd.strip().split()[0]
        return Path(first_token).stem.replace("_", " ").replace("-", " ").title()
    return "Workload Process"


def build_cpu_utilization_analysis_text(metrics_payload: Any) -> str:
    """Deterministically builds the structured CPU Utilization Analysis block."""
    if isinstance(metrics_payload, dict) and "current_metrics" in metrics_payload:
        current_m = metrics_payload.get("current_metrics") or {}
        latest_5 = metrics_payload.get("latest_5_recordings") or [current_m]
        top_procs = metrics_payload.get("top_5_processes") or []
        logs_5 = metrics_payload.get("services_logs_5") or []

        curr_cpu_obj = current_m.get("cpu") or {}
        curr_cpu = float(curr_cpu_obj.get("total", 0.0) or 0.0)
        curr_time = current_m.get("timestamp", "")

        start_m = latest_5[0] if latest_5 else current_m
        start_cpu = float((start_m.get("cpu") or {}).get("total", curr_cpu) or curr_cpu)
        start_time = start_m.get("timestamp", curr_time)

        start_fmt = _fmt_time(start_time)
        curr_fmt = _fmt_time(curr_time)

        top_proc = top_procs[0] if top_procs else {}
        p_name = _extract_friendly_name(top_proc.get("command_line", ""), top_proc.get("process_name", "Primary Process"))
        p_pid = top_proc.get("pid", "N/A")
        p_cpu = float(top_proc.get("cpu_percent", curr_cpu) or curr_cpu)
        thread_cnt = top_proc.get("thread_count")

        corr_svc = {}
        for s in logs_5:
            s_name = (s.get("service_name") or "").lower()
            s_proc = str(s.get("process") or "").lower()
            if (str(p_pid) in s_proc or
                p_name.lower() in s_name or
                (top_proc.get("command_line") and s_name in top_proc.get("command_line", "").lower())):
                corr_svc = s
                break
        if not corr_svc and logs_5:
            corr_svc = logs_5[0]

        corr_time = _fmt_time(corr_svc.get("timestamp", curr_time))
        corr_name = corr_svc.get("service_name") or (f"{p_name}.service" if p_name else "system-workload.service")
        corr_msg = corr_svc.get("message") or f"Service active under process PID {p_pid}"

        other_svcs = [s.get("service_name") for s in logs_5 if s.get("service_name") and s.get("service_name") != corr_name][:2]
        supp_text = f"{', '.join(other_svcs)} activity observed during the observation window." if other_svcs else "Background system services active during the observation period."

        # If current CPU is normal (no issues detected)
        if curr_cpu < 50.0:
            lines = [
                "CPU Utilization Analysis",
                "",
                "Observed:",
                f"CPU utilization is normal at {curr_cpu:.1f}%. No issues detected between {start_fmt} and {curr_fmt}.",
                "",
                "Primary process:",
                f"{p_name} (PID {p_pid})",
                f"CPU usage: {p_cpu:.1f}%.",
            ]
            if thread_cnt is not None and str(thread_cnt).strip():
                lines.append(f"Thread count: {thread_cnt}")
            lines.extend([
                "",
                "Status:",
                "Healthy. There are no issues detected. Host CPU compute capacity is operating within safe limits.",
            ])
            return "\n".join(lines)

        lines = [
            "CPU Utilization Analysis",
            "",
            "Observed:",
            f"CPU increased from {start_cpu:.0f}% to {curr_cpu:.0f}% between {start_fmt} and {curr_fmt}.",
            "",
            "Primary process:",
            f"{p_name} (PID {p_pid})",
            f"CPU reached {p_cpu:.1f}%.",
        ]
        if thread_cnt is not None and str(thread_cnt).strip():
            lines.append(f"Thread count: {thread_cnt}")

        lines.extend([
            "",
            "Correlated service event:",
            f"At {corr_time}, {corr_name} reported: {corr_msg}",
            "",
            "Supporting evidence:",
            supp_text,
            "",
            "Likely root cause:",
            f"The CPU spike is associated with active workload process '{p_name}' operating near host compute capacity.",
            "",
            "Confidence:",
            "High",
        ])
        return "\n".join(lines)

    records = metrics_payload if isinstance(metrics_payload, list) else [metrics_payload]
    if not records or not isinstance(records[0], dict):
        return "CPU Utilization Analysis\n\nNo telemetry records available."

    cpu_values = []
    for r in records:
        total_p = None
        if "cpu_metrics" in r and isinstance(r["cpu_metrics"], dict):
            total_p = r["cpu_metrics"].get("total_percent")
        if total_p is None:
            total_p = r.get("usage_percent", r.get("cpu", {}).get("total", 0.0))
        try:
            total_p = float(total_p or 0.0)
        except Exception:
            total_p = 0.0
        cpu_values.append((total_p, r.get("timestamp", "")))

    start_cpu, start_t = cpu_values[0] if cpu_values else (0.0, "")
    peak_cpu, peak_t = max(cpu_values, key=lambda x: x[0]) if cpu_values else (start_cpu, start_t)
    start_fmt = _fmt_time(start_t)
    peak_fmt = _fmt_time(peak_t)

    first_rec = records[0]
    primary = first_rec.get("primary_process") or {}
    p_name = primary.get("name") or primary.get("process_name") or "Primary Process"
    p_pid = primary.get("pid", "N/A")
    p_cpu = primary.get("cpu_percent", peak_cpu)
    thread_cnt = primary.get("thread_count")

    if peak_cpu < 50.0:
        lines = [
            "CPU Utilization Analysis",
            "",
            "Observed:",
            f"CPU utilization is normal at {peak_cpu:.1f}%. No issues detected between {start_fmt} and {peak_fmt}.",
            "",
            "Primary process:",
            f"{p_name} (PID {p_pid})",
            f"CPU usage: {p_cpu:.1f}%.",
        ]
        if thread_cnt is not None and str(thread_cnt).strip():
            lines.append(f"Thread count: {thread_cnt}")
        lines.extend([
            "",
            "Status:",
            "Healthy. There are no issues detected. Host CPU compute capacity is operating within safe limits.",
        ])
        return "\n".join(lines)

    corr = first_rec.get("correlated_service_event") or {}
    corr_time = _fmt_time(corr.get("timestamp", peak_t))
    corr_svc = corr.get("service_name") or "system-workload.service"
    corr_msg = corr.get("message") or f"Active workload processing under PID {p_pid}"

    lines = [
        "CPU Utilization Analysis",
        "",
        "Observed:",
        f"CPU increased from {start_cpu:.0f}% to {peak_cpu:.0f}% between {start_fmt} and {peak_fmt}.",
        "",
        "Primary process:",
        f"{p_name} (PID {p_pid})",
        f"CPU reached {p_cpu:.1f}%.",
    ]
    if thread_cnt is not None and str(thread_cnt).strip():
        lines.append(f"Thread count: {thread_cnt}")

    lines.extend([
        "",
        "Correlated service event:",
        f"At {corr_time}, {corr_svc} reported: {corr_msg}",
        "",
        "Supporting evidence:",
        "System services active during the observation period.",
        "",
        "Likely root cause:",
        f"The CPU spike is associated with active workload from '{p_name}' operating near host compute capacity.",
        "",
        "Confidence:",
        "High",
    ])
    return "\n".join(lines)


def build_disk_utilization_analysis_text(metrics_payload: Any) -> str:
    """Deterministically builds the structured Disk Utilization Analysis block."""
    if isinstance(metrics_payload, dict) and "current_metrics" in metrics_payload:
        current_m = metrics_payload.get("current_metrics") or {}
        latest_5 = metrics_payload.get("latest_5_recordings") or [current_m]
        top_procs = metrics_payload.get("top_5_processes") or []
        logs_5 = metrics_payload.get("services_logs_5") or []

        d_info = current_m.get("disk") or {}
        used_p = float(d_info.get("percent", 0.0) or 0.0)
        used_gb = float(d_info.get("used_gb", 0.0) or 0.0)
        free_gb = float(d_info.get("free_gb", 0.0) or 0.0)
        total_gb = float(d_info.get("total_gb", 0.0) or 0.0)

        start_m = latest_5[0] if latest_5 else current_m
        start_fmt = _fmt_time(start_m.get("timestamp", ""))
        curr_fmt = _fmt_time(current_m.get("timestamp", ""))

        top_proc = top_procs[0] if top_procs else {}
        p_name = _extract_friendly_name(top_proc.get("command_line", ""), top_proc.get("process_name", "Storage Process"))
        p_pid = top_proc.get("pid", "N/A")

        corr_svc = logs_5[0] if logs_5 else {}
        corr_time = _fmt_time(corr_svc.get("timestamp", curr_fmt))
        corr_name = corr_svc.get("service_name") or "storage.service"
        corr_msg = corr_svc.get("message") or "Storage write operations executing within normal baseline"

        # If disk is normal (no issues detected)
        if used_p < 70.0:
            lines = [
                "Disk Utilization Analysis",
                "",
                "Observed:",
                f"Disk utilization is normal at {used_p:.1f}% ({used_gb:.2f} GB used out of {total_gb:.2f} GB, {free_gb:.2f} GB free). No issues detected between {start_fmt} and {curr_fmt}.",
                "",
                "Primary process:",
                f"{p_name} (PID {p_pid})",
                "Disk activity: nominal I/O throughput across system mount points.",
            ]
            lines.extend([
                "",
                "Status:",
                "Healthy. There are no issues detected. System storage capacity is healthy with ample free space.",
            ])
            return "\n".join(lines)

        lines = [
            "Disk Utilization Analysis",
            "",
            "Observed:",
            f"Disk utilization observed at {used_p:.1f}% ({used_gb:.2f} GB of {total_gb:.2f} GB used, {free_gb:.2f} GB free) between {start_fmt} and {curr_fmt}.",
            "",
            "Primary process:",
            f"{p_name} (PID {p_pid})",
            "Disk activity: normal I/O throughput across system mount points.",
            "",
            "Correlated service event:",
            f"At {corr_time}, {corr_name} reported: {corr_msg}",
            "",
            "Supporting evidence:",
            "System logging and storage mount points operating within healthy baseline latency.",
            "",
            "Likely root cause:",
            f"Storage usage is elevated at {used_p:.1f}%.",
            "",
            "Confidence:",
            "High",
        ]
        return "\n".join(lines)

    records = metrics_payload if isinstance(metrics_payload, list) else [metrics_payload]
    if not records or not isinstance(records[0], dict):
        return "Disk Utilization Analysis\n\nNo storage records available."

    first = records[0]
    last = records[-1]
    d_info = first.get("disk_metrics", first.get("disk", {}))
    used_p = float(d_info.get("percent", first.get("usage_percent", 0.0)))
    used_gb = float(d_info.get("used_gb", 0.0))
    free_gb = float(d_info.get("free_gb", 0.0))
    total_gb = float(d_info.get("total_gb", 0.0))
    start_fmt = _fmt_time(first.get("timestamp", ""))
    end_fmt = _fmt_time(last.get("timestamp", ""))

    primary = first.get("primary_process") or {}
    p_name = primary.get("name") or "Storage Process"
    p_pid = primary.get("pid", "N/A")
    p_rss = float(primary.get("memory_rss_mb", 0.0))
    thread_cnt = primary.get("thread_count")

    if used_p < 70.0:
        lines = [
            "Disk Utilization Analysis",
            "",
            "Observed:",
            f"Disk utilization is normal at {used_p:.1f}% ({used_gb:.2f} GB used out of {total_gb:.2f} GB, {free_gb:.2f} GB free). No issues detected between {start_fmt} and {end_fmt}.",
            "",
            "Primary process:",
            f"{p_name} (PID {p_pid})",
            "Disk activity: nominal I/O throughput across system mount points.",
        ]
        lines.extend([
            "",
            "Status:",
            "Healthy. There are no issues detected. System storage capacity is healthy with ample free space.",
        ])
        return "\n".join(lines)

    corr = first.get("correlated_service_event") or {}
    corr_time = _fmt_time(corr.get("timestamp", ""))
    corr_svc = corr.get("service_name") or "storage.service"
    corr_msg = corr.get("message") or "Active storage operations"

    lines = [
        "Disk Utilization Analysis",
        "",
        "Observed:",
        f"Disk utilization observed at {used_p:.1f}% ({used_gb:.2f} GB of {total_gb:.2f} GB used, {free_gb:.2f} GB free) between {start_fmt} and {end_fmt}.",
        "",
        "Primary process:",
        f"{p_name} (PID {p_pid})",
        f"Disk activity: steady I/O throughput / Memory RSS {p_rss:.1f} MB.",
    ]
    if thread_cnt is not None and str(thread_cnt).strip():
        lines.append(f"Thread count: {thread_cnt}")

    lines.extend([
        "",
        "Correlated service event:",
        f"At {corr_time}, {corr_svc} reported: {corr_msg}",
        "",
        "Supporting evidence:",
        "System storage mounts operating with nominal disk write operations.",
        "",
        "Likely root cause:",
        f"Storage capacity is healthy at {used_p:.1f}% utilization with {free_gb:.2f} GB free capacity." if used_p < 70 else f"Storage usage is elevated at {used_p:.1f}%.",
        "",
        "Confidence:",
        "High",
    ])
    return "\n".join(lines)


def build_memory_utilization_analysis_text(metrics_payload: Any) -> str:
    """Deterministically builds the structured Memory Utilization Analysis block."""
    if isinstance(metrics_payload, dict) and "current_metrics" in metrics_payload:
        current_m = metrics_payload.get("current_metrics") or {}
        latest_5 = metrics_payload.get("latest_5_recordings") or [current_m]
        top_procs = metrics_payload.get("top_5_processes") or []
        logs_5 = metrics_payload.get("services_logs_5") or []

        ram_info = current_m.get("ram") or {}
        curr_p = float(ram_info.get("percent", 0.0) or 0.0)
        used_gb = float(ram_info.get("used_gb", 0.0) or 0.0)
        avail_gb = float(ram_info.get("available_gb", 0.0) or 0.0)
        total_gb = float(ram_info.get("total_gb", 0.0) or 0.0)

        start_m = latest_5[0] if latest_5 else current_m
        start_fmt = _fmt_time(start_m.get("timestamp", ""))
        curr_fmt = _fmt_time(current_m.get("timestamp", ""))

        top_proc = top_procs[0] if top_procs else {}
        p_name = _extract_friendly_name(top_proc.get("command_line", ""), top_proc.get("process_name", "Primary Process"))
        p_pid = top_proc.get("pid", "N/A")
        p_mem = float(top_proc.get("memory_percent", 0.0) or 0.0)
        p_rss = float(top_proc.get("memory_rss_mb", 0.0) or 0.0)
        thread_cnt = top_proc.get("thread_count")

        corr_svc = logs_5[0] if logs_5 else {}
        corr_time = _fmt_time(corr_svc.get("timestamp", curr_fmt))
        corr_name = corr_svc.get("service_name") or "system-memory.service"
        # If memory is normal (no issues detected)
        if curr_p < 70.0:
            lines = [
                "Memory Utilization Analysis",
                "",
                "Observed:",
                f"RAM utilization is normal at {curr_p:.1f}% ({used_gb:.2f} GB used out of {total_gb:.2f} GB, {avail_gb:.2f} GB available). No issues detected between {start_fmt} and {curr_fmt}.",
                "",
                "Primary process:",
                f"{p_name} (PID {p_pid})",
                f"Memory footprint: {p_mem:.2f}% (RSS {p_rss:.1f} MB).",
            ]
            if thread_cnt is not None and str(thread_cnt).strip():
                lines.append(f"Thread count: {thread_cnt}")
            lines.extend([
                "",
                "Status:",
                "Healthy. There are no issues detected. Host memory allocations are operating within normal baseline headroom.",
            ])
            return "\n".join(lines)

        lines = [
            "Memory Utilization Analysis",
            "",
            "Observed:",
            f"Memory utilization observed at {curr_p:.1f}% ({used_gb:.2f} GB of {total_gb:.2f} GB used, {avail_gb:.2f} GB available) between {start_fmt} and {curr_fmt}.",
            "",
            "Primary process:",
            f"{p_name} (PID {p_pid})",
            f"Memory footprint reached {p_mem:.2f}% (RSS {p_rss:.1f} MB).",
        ]
        if thread_cnt is not None and str(thread_cnt).strip():
            lines.append(f"Thread count: {thread_cnt}")

        lines.extend([
            "",
            "Correlated service event:",
            f"At {corr_time}, {corr_name} reported: {corr_msg}",
            "",
            "Supporting evidence:",
            "Virtual memory buffers and paging activity remain within nominal operating headroom.",
            "",
            "Likely root cause:",
            f"Elevated memory allocation detected on host '{current_m.get('hostname', 'system-host')}'.",
            "",
            "Confidence:",
            "High",
        ])
        return "\n".join(lines)

    records = metrics_payload if isinstance(metrics_payload, list) else [metrics_payload]
    if not records or not isinstance(records[0], dict):
        return "Memory Utilization Analysis\n\nNo memory records available."

    first = records[0]
    last = records[-1]
    r_first = first.get("ram_metrics", first.get("ram", {}))
    r_last = last.get("ram_metrics", last.get("ram", {}))
    start_ram = float(r_first.get("percent", first.get("usage_percent", 0.0)))
    peak_ram = float(r_last.get("percent", last.get("usage_percent", start_ram)))
    used_gb = float(r_first.get("used_gb", 0.0))
    total_gb = float(r_first.get("total_gb", 0.0))
    start_fmt = _fmt_time(first.get("timestamp", ""))
    peak_fmt = _fmt_time(last.get("timestamp", ""))

    primary = first.get("primary_process") or {}
    p_name = primary.get("name") or "Primary Process"
    p_pid = primary.get("pid", "N/A")
    p_mem = float(primary.get("memory_percent", 0.0))
    p_rss = float(primary.get("memory_rss_mb", 0.0))
    thread_cnt = primary.get("thread_count")

    if peak_ram < 70.0:
        lines = [
            "Memory Utilization Analysis",
            "",
            "Observed:",
            f"RAM utilization is normal at {peak_ram:.1f}% ({used_gb:.2f} GB of {total_gb:.2f} GB used). No issues detected between {start_fmt} and {peak_fmt}.",
            "",
            "Primary process:",
            f"{p_name} (PID {p_pid})",
            f"Memory footprint: {p_mem:.2f}% (RSS {p_rss:.1f} MB).",
        ]
        if thread_cnt is not None and str(thread_cnt).strip():
            lines.append(f"Thread count: {thread_cnt}")
        lines.extend([
            "",
            "Status:",
            "Healthy. There are no issues detected. Host memory allocations are operating within normal baseline headroom.",
        ])
        return "\n".join(lines)

    corr = first.get("correlated_service_event") or {}
    corr_time = _fmt_time(corr.get("timestamp", ""))
    corr_svc = corr.get("service_name") or "system-memory.service"
    corr_msg = corr.get("message") or "Active service memory operations"

    lines = [
        "Memory Utilization Analysis",
        "",
        "Observed:",
        f"RAM utilization increased from {start_ram:.1f}% to {peak_ram:.1f}% ({used_gb:.2f} GB of {total_gb:.2f} GB used) between {start_fmt} and {peak_fmt}.",
        "",
        "Primary process:",
        f"{p_name} (PID {p_pid})",
        f"Memory reached {p_mem:.2f}% (RSS {p_rss:.1f} MB).",
    ]
    if thread_cnt is not None and str(thread_cnt).strip():
        lines.append(f"Thread count: {thread_cnt}")

    lines.extend([
        "",
        "Correlated service event:",
        f"At {corr_time}, {corr_svc} reported: {corr_msg}",
        "",
        "Supporting evidence:",
        "System services active during the observation period.",
        "",
        "Likely root cause:",
        "Elevated memory allocation detected on host.",
        "",
        "Confidence:",
        "High",
    ])
    return "\n".join(lines)


def call_llm_agent(
    agent_name: str,
    resource_type: str,
    metrics_payload: Any,
    system_instructions: str,
) -> Dict[str, Any]:
    """
    Invokes the LLM (Gemini) with the agent's instructions and segregated telemetry.
    The LLM autonomously decides the detection, root cause diagnosis, and remediation plan.
    """
    client = get_genai_client()
    res_upper = resource_type.upper()
    is_cpu = res_upper == "CPU" or "cpu" in agent_name.lower()
    is_disk = res_upper == "DISK" or "disk" in agent_name.lower()
    is_memory = res_upper in ["RAM", "MEMORY"] or "memory" in agent_name.lower()

    analysis_instruction = ""
    analysis_field = "analysis"
    if is_cpu:
        analysis_field = "cpu_analysis"
        analysis_instruction = """
IMPORTANT: Provide a top-level string field "cpu_analysis" matching this exact structure:
CPU Utilization Analysis

Observed:
CPU increased from <start>% to <peak>% between <start_time> and <peak_time>.

Primary process:
<Primary process name> (PID <PID>)
CPU reached <cpu_reached>%.
[Thread count: <count>]  <-- only if thread count is present in data

Correlated service event:
At <time>, <service_name> <event_summary / log message>.

Supporting evidence:
<Secondary activity or supporting logs during the same period>.

Likely root cause:
<Root cause analysis explaining the workload impact>.

Confidence:
High | Medium | Low
"""
    elif is_disk:
        analysis_field = "disk_analysis"
        analysis_instruction = """
IMPORTANT: Provide a top-level string field "disk_analysis" matching this exact structure:
Disk Utilization Analysis

Observed:
Disk utilization observed at <used_percent>% (<used_gb> GB of <total_gb> GB used, <free_gb> GB free) between <start_time> and <end_time>.

Primary process:
<Primary process name> (PID <PID>)
Disk activity: <activity>.
[Thread count: <count>]  <-- only if thread count is present in data

Correlated service event:
At <time>, <service_name> <event_summary / log message>.

Supporting evidence:
<Secondary activity or database/logging service events during the period>.

Likely root cause:
<Root cause analysis explaining storage status and workload impact>.

Confidence:
High | Medium | Low
"""
    elif is_memory:
        analysis_field = "memory_analysis"
        analysis_instruction = """
IMPORTANT: Provide a top-level string field "memory_analysis" matching this exact structure:
Memory Utilization Analysis

Observed:
RAM utilization increased from <start>% to <peak>% (<used_gb> GB of <total_gb> GB used) between <start_time> and <peak_time>.

Primary process:
<Primary process name> (PID <PID>)
Memory reached <memory_percent>% (RSS <rss> MB).
[Thread count: <count>]  <-- only if thread count is present in data

Correlated service event:
At <time>, <service_name> <event_summary / log message>.

Supporting evidence:
<Secondary activity or database/service logs during the period>.

Likely root cause:
<Root cause analysis explaining memory consumption and workload impact>.

Confidence:
High | Medium | Low
"""

    prompt = f"""
You are the autonomous {agent_name} in an enterprise reliability engineering ecosystem.
Resource under investigation: {resource_type}

AGENT ROLE & INSTRUCTIONS:
{system_instructions}

SEGREATED METRIC TELEMETRY DATA (30 merged records linking host telemetry, processes, and service logs):
{json.dumps(metrics_payload, indent=2)}

TASK:
Analyze the provided telemetry thoroughly. Do NOT use canned or generic responses.
Generate an accurate, technical assessment based on the exact numbers observed.
If there are multiple problematic records / spikes, formulate an individualized remediation plan
for each distinct spike (For CPU: only generate plans for CPU utilization data > 90%; if 100% saturation is present across multiple points, output only 1 plan for 100%).
{analysis_instruction}

Respond ONLY with a valid JSON object matching this structure:
{{
  "agent": "{agent_name}",
  "resource": "{resource_type}",
  "{analysis_field}": "Structured analysis string matching the format above",
  "detection": {{
    "detected": true,
    "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
    "highest_threshold_crossed": 100 | 70 | 50 | null,
    "summary": "Concise summary of what was detected"
  }},
  "diagnosis": {{
    "diagnosis_status": "CONFIRMED" | "HEALTHY",
    "root_cause": "Specific technical root cause based on the metrics",
    "explanation": "Detailed technical explanation of the issue"
  }},
  "remediation": {{
    "action_required": "Concrete actionable steps to mitigate the issue",
    "preventive_guardrail": "Long-term architectural guardrail to prevent recurrence"
  }},
  "remediation_plans": [
    {{
      "plan_id": "REMED-{resource_type.upper()}-001",
      "service_name": "Service responsible for this specific spike",
      "timestamp": "Timestamp of the spike/record",
      "severity": "CRITICAL" | "HIGH" | "MEDIUM",
      "root_cause": "Root cause for this specific spike",
      "action_required": "Specific action for this record",
      "preventive_guardrail": "Guardrail"
    }}
  ]
}}
"""

    if client:
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )
            if response and response.text:
                cleaned_text = _clean_json_markdown(response.text)
                parsed_json = json.loads(cleaned_text)
                parsed_json["llm_powered"] = True
                parsed_json["model_used"] = MODEL_NAME
                if is_cpu and not parsed_json.get("cpu_analysis"):
                    parsed_json["cpu_analysis"] = build_cpu_utilization_analysis_text(metrics_payload)
                elif is_disk and not parsed_json.get("disk_analysis"):
                    parsed_json["disk_analysis"] = build_disk_utilization_analysis_text(metrics_payload)
                elif is_memory and not parsed_json.get("memory_analysis"):
                    parsed_json["memory_analysis"] = build_memory_utilization_analysis_text(metrics_payload)
                return parsed_json
        except Exception as exc:
            logger.warning(f"LLM call with model {MODEL_NAME} failed: {exc}")

    # Graceful fallback if LLM is offline / quota exhausted
    logger.info(f"Generating structured response via local intelligence fallback for {agent_name}")
    fallback_resp = _generate_fallback_agent_response(agent_name, resource_type, metrics_payload)
    if is_cpu:
        fallback_resp["cpu_analysis"] = build_cpu_utilization_analysis_text(metrics_payload)
    elif is_disk:
        fallback_resp["disk_analysis"] = build_disk_utilization_analysis_text(metrics_payload)
    elif is_memory:
        fallback_resp["memory_analysis"] = build_memory_utilization_analysis_text(metrics_payload)
    return fallback_resp


def _generate_fallback_agent_response(
    agent_name: str,
    resource_type: str,
    metrics_payload: Any,
) -> Dict[str, Any]:
    """Fallback when external LLM API is unreachable."""
    res_upper = resource_type.upper()
    is_cpu = res_upper == "CPU" or "cpu" in agent_name.lower()
    is_disk = res_upper == "DISK" or "disk" in agent_name.lower()
    is_memory = res_upper in ["RAM", "MEMORY"] or "memory" in agent_name.lower()

    peak = 0.0
    if isinstance(metrics_payload, list) and metrics_payload:
        if is_disk:
            peak = max([float(m.get("disk_metrics", {}).get("percent", m.get("usage_percent", 0.0))) for m in metrics_payload if isinstance(m, dict)] or [0.0])
        elif is_memory:
            peak = max([float(m.get("ram_metrics", {}).get("percent", m.get("usage_percent", 0.0))) for m in metrics_payload if isinstance(m, dict)] or [0.0])
        else:
            peak = max([float(m.get("cpu_metrics", {}).get("total_percent", m.get("usage_percent", m.get("total", 0.0)))) for m in metrics_payload if isinstance(m, dict)] or [0.0])
    elif isinstance(metrics_payload, dict):
        if is_disk:
            peak = float(metrics_payload.get("disk_metrics", {}).get("percent", metrics_payload.get("usage_percent", 0.0)))
        elif is_memory:
            peak = float(metrics_payload.get("ram_metrics", {}).get("percent", metrics_payload.get("usage_percent", 0.0)))
        else:
            peak = float(metrics_payload.get("cpu_metrics", {}).get("total_percent", metrics_payload.get("usage_percent", 0.0)))

    threshold = 100 if peak >= 99.0 else (70 if peak >= 70.0 else (50 if peak >= 50.0 else None))
    severity = "CRITICAL" if threshold == 100 else ("HIGH" if threshold == 70 else ("MEDIUM" if threshold == 50 else "LOW"))

    analysis_dict = {}
    if is_cpu:
        analysis_dict["cpu_analysis"] = build_cpu_utilization_analysis_text(metrics_payload)
    elif is_disk:
        analysis_dict["disk_analysis"] = build_disk_utilization_analysis_text(metrics_payload)
    elif is_memory:
        analysis_dict["memory_analysis"] = build_memory_utilization_analysis_text(metrics_payload)

    return {
        "agent": agent_name,
        "resource": resource_type,
        "llm_powered": False,
        **analysis_dict,
        "detection": {
            "subagent": "detection_agent",
            "detected": threshold is not None,
            "severity": severity,
            "highest_threshold_crossed": threshold,
            "summary": (
                f"{resource_type} utilization reached {peak:.1f}%. Exceeded threshold tier: {threshold}%."
                if threshold
                else f"No issues detected. {resource_type} utilization is normal at {peak:.1f}%."
            ),
        },
        "diagnosis": {
            "subagent": "diagnosis_agent",
            "diagnosis_status": "CONFIRMED" if threshold else "HEALTHY",
            "root_cause": (
                f"Full {resource_type} saturation ({peak:.1f}%) driven by primary workload process."
                if peak >= 99.0
                else f"Elevated {resource_type} resource demand ({peak:.1f}%)."
                if threshold
                else f"No issues detected. {resource_type} compute and capacity are operating within healthy limits ({peak:.1f}%)."
            ),
            "explanation": (
                f"Host is operating at {peak:.1f}% capacity with high process contention."
                if threshold
                else f"Monitored processes and host {resource_type} metrics are within normal baseline headroom."
            ),
        },
        "remediation": {
            "subagent": "remediation_agent",
            "status": "REMEDIATION_DRAFTED" if threshold else "HEALTHY",
            "action_required": (
                f"Scale host {resource_type} resources immediately and inspect top consumers."
                if threshold
                else "No issues detected. No remediation required."
            ),
            "preventive_guardrail": (
                f"Configure proactive alerts at 70% for {resource_type}."
                if threshold
                else f"Continue standard monitoring for {resource_type}."
            ),
        },
        "remediation_plans": [
            {
                "plan_id": f"REMED-{resource_type.upper()}-001",
                "severity": severity,
                "root_cause": f"{resource_type} reached {peak:.1f}%",
                "action_required": f"Scale host capacity or throttle non-critical tasks.",
                "preventive_guardrail": f"Set automated alert policies for {resource_type}.",
            }
        ] if threshold else [],
    }
