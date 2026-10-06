
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class IncidentType(str, Enum):
    MISSING_PARTITION_FILTER = "MISSING_PARTITION_FILTER"
    HIGH_CARDINALITY_JOIN = "HIGH_CARDINALITY_JOIN"
    SLOT_CONTENTION = "SLOT_CONTENTION"


class JoinFailureMode(str, Enum):
    """Which join pathology a HIGH_CARDINALITY_JOIN incident is.

    Each maps to a different remediation, which is why classification is
    worth the effort: salting is useless against shuffle volume, and
    pruning columns is useless against a hot key.
    """

    KEY_SKEW = "KEY_SKEW"
    FAN_OUT = "FAN_OUT"
    SHUFFLE_VOLUME = "SHUFFLE_VOLUME"
    UNCONSTRAINED_JOIN = "UNCONSTRAINED_JOIN"


class IncidentConfidence(str, Enum):
    """How well the evidence supports the incident.

    Orthogonal to IncidentStatus, which tracks where a finding is in the
    detect/diagnose/remediate workflow. A CONFIRMED incident on a query
    that will never run again is still not worth routing to a person.
    """

    PATTERN_ONLY = "PATTERN_ONLY"
    PROBABLE = "PROBABLE"
    CONFIRMED = "CONFIRMED"
    NOT_CONFIRMED = "NOT_CONFIRMED"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class IncidentStatus(str, Enum):
    DETECTED = "DETECTED"
    NOT_DETECTED = "NOT_DETECTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    DIAGNOSING = "DIAGNOSING"
    DIAGNOSED = "DIAGNOSED"
    REMEDIATING = "REMEDIATING"
    REMEDIATION_DRAFTED = "REMEDIATION_DRAFTED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionCategory(str, Enum):
    RECOMMENDATION_ONLY = "RECOMMENDATION_ONLY"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    AUTO_FIX = "AUTO_FIX"


class Incident(BaseModel):
    incident_id: str = Field(
        description="Unique identifier for the incident."
    )

    incident_type: IncidentType

    status: IncidentStatus = IncidentStatus.DETECTED

    severity: Severity = Severity.MEDIUM

    source: Optional[str] = None

    job_id: Optional[str] = None

    table_name: Optional[str] = None

    query: Optional[str] = None

    summary: Optional[str] = None

    evidence: Dict[str, Any] = Field(
        default_factory=dict
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict
    )