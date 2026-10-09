from pathlib import Path
from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from agents.orchestrator_agent.agent import orchestrate_log_analysis

router = APIRouter(prefix="/api/orchestrator", tags=["Orchestrator Agent"])


@router.post("/analyze")
async def analyze_workload_orchestrator(
    request: Request,
    file: Optional[UploadFile] = File(None, description="Log file upload (.csv)"),
    text: Optional[str] = Form(None, description="Log text / CSV content"),
):
    """
    Master Orchestrator Endpoint:
    Accepts a log file OR raw text as input, inspects the workload characteristics,
    redirects to the appropriate subagent (CPU Agent or Disk Agent), and returns
    the remediation actions and FinOps guardrails in the project schema.
    """
    content: Optional[str] = None
    filename: Optional[str] = None

    if file is not None and file.filename:
        filename = file.filename
        try:
            content_bytes = await file.read()
            content = content_bytes.decode("utf-8", errors="replace").strip()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {str(exc)}")
    elif text and text.strip():
        content = text.strip()
    else:
        try:
            body = await request.json()
            if isinstance(body, dict):
                content = body.get("text") or body.get("csv_text") or body.get("content")
                filename = body.get("filename")
            elif isinstance(body, str):
                content = body
        except Exception:
            raw_body = (await request.body()).decode("utf-8", errors="replace").strip()
            if raw_body:
                content = raw_body

    if not content:
        raise HTTPException(
            status_code=400,
            detail="No input provided. Please provide either a 'file' upload or 'text' content.",
        )

    try:
        return orchestrate_log_analysis(input_data=content, filename=filename)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Orchestration failure: {str(exc)}",
        )
