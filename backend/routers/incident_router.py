from fastapi import APIRouter, HTTPException
from services.agent_service import run_support_agent


router = APIRouter()


@router.get("/api/review")
async def review_incidents(
    region: str = "US",
    lookback_hours: int = 24,
    jobs_limit: int = 5,
):
    try:
        return await run_support_agent(
            region=region,
            lookback_hours=lookback_hours,
            jobs_limit=jobs_limit,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )