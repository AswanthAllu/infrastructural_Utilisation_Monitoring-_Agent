from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .incident import ActionCategory, IncidentStatus, IncidentType, Severity


class CPULogRecord(BaseModel):
    """Schema for individual row parsed from bq_cpu_logs.csv."""
    timestamp: str = Field(description="Execution timestamp (YYYY-MM-DD HH:MM:SS)")
    metric_type: str = Field(default="BQ_CPU_USAGE", description="Must be BQ_CPU_USAGE")
    project_id: str = Field(description="Target GCP project")
    job_id: str = Field(description="Unique query execution ID")
    avg_slots_utilized: float = Field(description="Average concurrent slots (CPUs) active")
    total_slot_ms: float = Field(description="Total compute time consumed in milliseconds")
    runtime_seconds: float = Field(description="Query duration in seconds")
    query: Optional[str] = Field(default=None, description="Original SQL query executed by the job")


class CPUDetectionBlock(BaseModel):
    """
    Detection & Diagnosis stage output handled by the detection subagent.
    Combines anomaly detection with root cause analysis and issue diagnosis.
    """
    detected: bool
    incident_type: IncidentType = IncidentType.SLOT_CONTENTION
    status: IncidentStatus = IncidentStatus.DETECTED
    diagnosis_status: str = "CONFIRMED"
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0, default=0.95)
    summary: str
    root_cause: str
    explanation: str
    detected_issue: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)
    reasons: List[str] = Field(default_factory=list)
    safety_notes: List[str] = Field(default_factory=list)
    escalation_required: bool = False
    escalation_reason: Optional[str] = None
    recommended_next_step: Optional[str] = "REMEDIATION"


class CPURemediationBlock(BaseModel):
    """
    Remediation plan stage output handled by the remediation subagent.
    Formulates remediation actions, SQL query optimizations, and preventive guardrails.
    """
    action_category: ActionCategory = ActionCategory.RECOMMENDATION_ONLY
    status: IncidentStatus = IncidentStatus.REMEDIATION_DRAFTED
    action_taken: str = "A performance remediation plan and FinOps guardrail were formulated."
    action_required: str
    preventive_guardrail: Optional[str] = None
    recommended_query: Optional[str] = Field(
        default=None,
        description="Optimized SQL query rewritten to alleviate CPU slot burn and bottlenecks"
    )
    executed: bool = False
    verification_required: bool = True
    verification_result: Optional[str] = None
    workflow_id: Optional[str] = None
    task_id: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    safety_notes: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CPUIncident(BaseModel):
    """
    Unified incident representation containing only the 2 designated subagents:
    1. detection: Handles anomaly detection and root cause / issue diagnosis
    2. remediation: Formulates the remediation plan, optimized query, and guardrails
    """
    job_id: str
    incident_type: IncidentType = IncidentType.SLOT_CONTENTION
    table_name: Optional[str] = None
    severity: Severity
    original_query: Optional[str] = None
    optimized_query: Optional[str] = None
    detection: CPUDetectionBlock
    remediation: CPURemediationBlock


class CPUBatchAnalysisResult(BaseModel):
    """Complete response returned by the parent CPU agent for a log analysis run."""
    success: bool = True
    parent_agent: str = "cpu_agent"
    sub_agents: List[str] = Field(default_factory=lambda: ["detection_agent", "remediation_agent"])
    metric_type: str = "BQ_CPU_USAGE"
    total_rows_processed: int = 0
    healthy_queries_count: int = 0
    negative_incidents_count: int = 0
    incidents: List[CPUIncident] = Field(default_factory=list)
    remediation_csv_preview: Optional[str] = None
