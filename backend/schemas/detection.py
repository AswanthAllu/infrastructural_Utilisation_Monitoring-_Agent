from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .incident import (
    IncidentConfidence,
    IncidentStatus,
    IncidentType,
    JoinFailureMode,
    Severity,
)


class JoinKeyStats(BaseModel):
    """Distribution facts about one side of a join key."""

    table: Optional[str] = None
    column: Optional[str] = None
    row_count: Optional[int] = None
    is_declared_primary_key: bool = False


class JoinStageEvidence(BaseModel):
    """Measured execution-plan metrics for a job's join stages.

    Everything here is measured rather than estimated: the job has
    already run, so these come from INFORMATION_SCHEMA.JOBS.job_stages.
    """

    join_stage_count: int = 0
    join_slot_ms: Optional[float] = None
    join_dominance: Optional[float] = None
    max_skew_ratio: Optional[float] = None
    max_fanout_ratio: Optional[float] = None
    total_shuffle_bytes: Optional[float] = None
    max_spilled_bytes: Optional[float] = None


class JoinEvidence(BaseModel):
    """Evidence for a HIGH_CARDINALITY_JOIN incident.

    Kept separate from DetectionEvidence, which stays specific to
    MISSING_PARTITION_FILTER.
    """

    job_id: Optional[str] = None
    query: Optional[str] = None
    tables: List[str] = Field(default_factory=list)

    failure_mode: Optional[JoinFailureMode] = None
    join_type: Optional[str] = None
    predicate_kind: Optional[str] = None
    key_pairs: List[Dict[str, Any]] = Field(default_factory=list)

    left_stats: Optional[JoinKeyStats] = None
    right_stats: Optional[JoinKeyStats] = None
    stages: Optional[JoinStageEvidence] = None

    total_bytes_processed: Optional[int] = None
    total_slot_ms: Optional[int] = None
    resources_exceeded: bool = False
    constraint_contradicted: bool = False

    evidence_tier: int = 0
    missing_evidence: List[str] = Field(default_factory=list)

    expected_future_runs: Optional[float] = None
    recoverable_slot_ms_upper_bound: Optional[float] = None
    savings_currency: Optional[str] = None
    routed: bool = False
    routing_reason: Optional[str] = None


class DetectionEvidence(BaseModel):
    job_id: Optional[str] = None
    table_name: Optional[str] = None
    query: Optional[str] = None

    is_partitioned: Optional[bool] = None
    partition_column: Optional[str] = None
    partition_type: Optional[str] = None
    require_partition_filter: Optional[bool] = None

    total_bytes_processed: Optional[int] = None
    total_slot_ms: Optional[int] = None

    sql_has_partition_filter: Optional[bool] = None

    additional_evidence: Dict[str, Any] = Field(default_factory=dict)


class DetectionResult(BaseModel):
    detected: bool
    incident_type: IncidentType
    status: IncidentStatus

    confidence_state: Optional[IncidentConfidence] = None

    severity: Severity = Severity.MEDIUM

    confidence: float = Field(
        ge=0.0,
        le=1.0
    )

    summary: str

    evidence: DetectionEvidence

    reasons: List[str] = Field(
        default_factory=list
    )

    recommended_next_step: Optional[str] = None


class DetectionRequest(BaseModel):
    candidate: bool
    incident_type: IncidentType
    job_id: Optional[str] = None
    table_name: Optional[str] = None
    query: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)