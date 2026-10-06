import sys
from pathlib import Path

# Ensure project root is in sys.path so config/schemas are always importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from .cpu_agent import cpu_agent
from .detection_agent import detection_agent
from .diagnosis_agent import diagnosis_agent
from .disk_agent import disk_agent
from .memory_agent import memory_agent
from .orchestrator_agent import orchestrator_agent, route_incident_workload, orchestrate_log_analysis
from .remediation_agent import remediation_agent


__all__ = [
    "cpu_agent",
    "detection_agent",
    "diagnosis_agent",
    "disk_agent",
    "memory_agent",
    "orchestrator_agent",
    "remediation_agent",
    "route_incident_workload",
    "orchestrate_log_analysis",
]
