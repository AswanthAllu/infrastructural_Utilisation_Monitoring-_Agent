import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from routers.incident_router import router as incident_router
from routers.cpu_router import router as cpu_router
from routers.disk_router import router as disk_router
from routers.memory_router import router as memory_router
from routers.metrics_router import router as metrics_router
from routers.orchestrator_router import router as orchestrator_router
from tools.metrics_fetcher import fetch_metrics_history, store_metrics_json

logger = logging.getLogger(__name__)


async def periodic_metrics_poller(interval_seconds: int = 300):
    """Periodically fetches http://20.15.164.79:8080/api/history every 5 minutes and saves to logs/."""
    while True:
        try:
            # Run blocking urllib in executor so it doesn't block event loop
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, fetch_metrics_history)
            saved = await loop.run_in_executor(None, store_metrics_json, data)
            logger.info(f"Background metrics poller saved: {saved}")
        except Exception as exc:
            logger.warning(f"Background metrics poller encountered error: {exc}")
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: launch background poller
    poller_task = asyncio.create_task(periodic_metrics_poller(interval_seconds=300))
    yield
    # Shutdown
    poller_task.cancel()


app = FastAPI(
    title="System & BigQuery Support Agent Ecosystem",
    description=(
        "Autonomous multi-agent system for CPU, Disk, and Memory monitoring, "
        "detection, diagnosis, remediation planning, and threshold email alerting."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# The Vite development server runs on a different origin during local development.
# Keep this permissive for the local dashboard; production deployments should replace
# it with the deployed frontend origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cpu_router)
app.include_router(disk_router)
app.include_router(memory_router)
app.include_router(metrics_router)
app.include_router(orchestrator_router)
app.include_router(incident_router)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        reload=True,
    )
