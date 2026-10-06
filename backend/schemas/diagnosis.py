from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .incident import (
    ActionCategory,
    IncidentType,
    JoinFailureMode,
    Severity,
)


class DiagnosisResult(BaseModel):
    incident_type: IncidentType

    failure_mode: Optional[JoinFailureMode] = None

    root_cause: str

    explanation: str

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    severity: Severity

    action_category: ActionCategory

    recommended_action: Optional[str] = None

    required_evidence: List[str] = Field(
        default_factory=list
    )

    knowledge_base_references: List[str] = Field(
        default_factory=list
    )

    investigation_evidence: Dict[str, Any] = Field(
        default_factory=dict
    )

    safety_notes: List[str] = Field(
        default_factory=list
    )

    escalation_required: bool = False

    escalation_reason: Optional[str] = None