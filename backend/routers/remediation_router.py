import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.ssh_remediation_service import AUDIT_LOG_FILE, ssh_remediation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/remediation", tags=["Human-in-the-Loop Remediation"])


class RemediationDecisionRequest(BaseModel):
    action_id: str = Field(..., description="Unique action identifier from the agent proposal")
    decision: str = Field(..., description="'APPROVE' to execute, 'REJECT' to cancel")
    action_type: Optional[str] = Field(default="COMMAND", description="'KILL_PROCESS', 'RESTART_SERVICE', or 'COMMAND'")
    target_identifier: Optional[str] = Field(default="", description="PID number or service name")
    process_name: Optional[str] = Field(default="", description="Name of the process being acted on")
    signal: Optional[int] = Field(default=15, description="Linux signal (15 for SIGTERM, 9 for SIGKILL)")
    command: Optional[str] = Field(default="", description="Exact whitespace-separated command decided by LLM")
    operator_email: Optional[str] = Field(default="operator@local", description="Email or ID of operator")
    operator_note: Optional[str] = Field(default="", description="Optional human note or justification")


@router.post("/decision")
def handle_remediation_decision(payload: RemediationDecisionRequest) -> Dict[str, Any]:
    """
    Submits a Human-in-the-Loop (HITL) approval decision.
    If 'APPROVE', executes the remediation command decided by the LLM via SSH.
    If 'REJECT', cancels execution and records the audit record.
    """
    logger.info(
        f"🛡️ [HITL] Remediation request received: action_id={payload.action_id}, "
        f"decision={payload.decision}, action_type={payload.action_type}, "
        f"command={payload.command}, target={payload.target_identifier}"
    )
    decision = payload.decision.strip().upper()
    action_type = (payload.action_type or "COMMAND").strip().upper()

    if decision != "APPROVE":
        # Record cancellation in audit log
        ssh_remediation._record_audit_log(
            action_id=payload.action_id,
            operator=payload.operator_email or "operator",
            action_type=action_type,
            target=payload.target_identifier or payload.process_name or "remediation",
            command=payload.command or "N/A (REJECTED_BY_OPERATOR)",
            success=False,
            output=payload.operator_note or "Action declined by human operator.",
            decision="REJECTED",
            status="REJECTED",
            operator_note=payload.operator_note or "Action declined by human operator."
        )
        return {
            "success": True,
            "status": "REJECTED",
            "action_id": payload.action_id,
            "message": f"Remediation action {payload.action_id} was rejected by operator."
        }

    # Execute approved action via unified execute_approved_command
    try:
        cmd = (payload.command or "").strip()

        # If explicit command wasn't passed by frontend, construct it from legacy fields
        if not cmd:
            if action_type == "KILL_PROCESS" and payload.target_identifier:
                sig = payload.signal or 15
                cmd = f"sudo kill -{sig} {payload.target_identifier}"
            elif action_type == "RESTART_SERVICE" and payload.target_identifier:
                cmd = f"sudo systemctl restart {payload.target_identifier}"
            elif action_type == "RENICE_PROCESS" and payload.target_identifier:
                cmd = f"sudo renice -n 19 -p {payload.target_identifier}"
            else:
                raise HTTPException(status_code=400, detail="Missing executable command or target identifier.")

        result = ssh_remediation.execute_approved_command(
            command=cmd,
            operator=payload.operator_email or "operator",
            action_id=payload.action_id,
            operator_note=payload.operator_note or ""
        )

        return {
            "success": result["success"],
            "status": "EXECUTED" if result["success"] else "FAILED",
            "action_id": payload.action_id,
            "action_type": action_type,
            "command": result.get("command"),
            "details": result,
            "message": (
                f"Command '{result.get('command')}' executed successfully on VM (Exit Code: {result.get('exit_code')})."
                if result["success"]
                else f"Execution failed on VM: {result.get('stderr')}"
            )
        }

    except ValueError as ve:
        logger.warning(f"⛔ [HITL Guardrail Blocked]: {ve}")
        raise HTTPException(status_code=403, detail=str(ve))
    except Exception as exc:
        logger.error(f"❌ [HITL Execution Failed]: {exc}")
        raise HTTPException(status_code=500, detail=f"Execution failed on VM: {str(exc)}")


@router.get("/test-connection")
def test_vm_ssh_connection() -> Dict[str, Any]:
    """Tests SSH connectivity and credentials to the VM."""
    return ssh_remediation.test_connection()


@router.get("/audit-logs")
def get_remediation_audit_logs(limit: int = 100) -> Dict[str, Any]:
    """Returns past remediation audit entries with full info."""
    if not AUDIT_LOG_FILE.exists():
        return {"total_records": 0, "logs": []}

    try:
        lines = AUDIT_LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
        records = []
        for line in lines:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                cmd = rec.get("command", "")
                raw_status = str(rec.get("status", "")).upper()
                raw_output = rec.get("output", "")

                is_rejection = (
                    "REJECT" in cmd.upper()
                    or "REJECT" in raw_status
                    or "DECLINED" in str(raw_output).upper()
                    or rec.get("decision") == "REJECTED"
                )

                if is_rejection:
                    rec["decision"] = "REJECTED"
                    rec["status"] = "REJECTED"
                else:
                    rec["decision"] = "APPROVED"
                    if raw_status in ("SUCCESS", "EXECUTED"):
                        rec["status"] = "EXECUTED"
                    else:
                        rec["status"] = "FAILED"

                rec.setdefault("operator_note", raw_output if is_rejection else "")
                records.append(rec)
            except Exception:
                pass

        return {
            "total_records": len(records),
            "logs": records[-limit:][::-1]  # Most recent first
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read audit log: {exc}")


@router.delete("/audit-logs")
def clear_remediation_audit_logs() -> Dict[str, Any]:
    """Clears past remediation audit entries."""
    try:
        if AUDIT_LOG_FILE.exists():
            AUDIT_LOG_FILE.write_text("", encoding="utf-8")
        return {"success": True, "message": "Remediation audit history cleared successfully."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to clear audit log: {exc}")
