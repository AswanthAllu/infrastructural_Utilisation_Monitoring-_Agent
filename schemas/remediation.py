from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .incident import (
    ActionCategory,
    IncidentStatus,
)


class RemediationResult(BaseModel):
    action_category: ActionCategory

    status: IncidentStatus

    action_taken: Optional[str] = None

    action_required: Optional[str] = None

    executed: bool = False

    verification_required: bool = True

    verification_result: Optional[str] = None

    workflow_id: Optional[str] = None

    task_id: Optional[str] = None

    errors: List[str] = Field(
        default_factory=list
    )

    safety_notes: List[str] = Field(
        default_factory=list
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict
    )