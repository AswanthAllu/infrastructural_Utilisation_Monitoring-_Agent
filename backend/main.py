import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backend")

from routers.incident_router import router as incident_router
from routers.cpu_router import router as cpu_router
from routers.disk_router import router as disk_router
from routers.memory_router import router as memory_router
from routers.metrics_router import router as metrics_router
from routers.orchestrator_router import router as orchestrator_router
from routers.remediation_router import router as remediation_router
from tools.metrics_fetcher import fetch_current_metrics, fetch_metrics_history, store_metrics_json
from services.email_service import (
    get_highest_crossed_threshold,
    send_threshold_alert_email,
)


async def periodic_metrics_poller(interval_seconds: int = 60):
    """Fetch VM telemetry and send one alert when a resource crosses above 70%."""
    previously_above_70 = {"CPU": False, "RAM": False, "Disk": False}
    while True:
        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, fetch_metrics_history)

            current = await loop.run_in_executor(None, fetch_current_metrics)
            cpu = current.get("cpu") or {}
            ram = current.get("ram") or {}
            disk = current.get("disk") or {}
            # Use both the live snapshot and the newest history sample so a
            # short CPU spike is not missed between polling cycles.
            latest = data[-1] if data else {}
            latest_cpu = latest.get("cpu") or {}
            latest_ram = latest.get("ram") or {}
            latest_disk = latest.get("disk") or {}
            metrics = {
                "CPU": max(float(cpu.get("total", 0) or 0), float(latest_cpu.get("total", 0) or 0)),
                "RAM": max(float(ram.get("percent", 0) or 0), float(latest_ram.get("percent", 0) or 0)),
                "Disk": max(float(disk.get("percent", 0) or 0), float(latest_disk.get("percent", 0) or 0)),
            }
            recipient = os.getenv("DEFAULT_ALERT_EMAIL", "").strip()
            for resource, usage in metrics.items():
                cores_list = cpu.get("per_core") if resource == "CPU" else None
                matched_th = get_highest_crossed_threshold(
                    usage, per_core=cores_list, resource_name=resource
                )
                if matched_th is not None and previously_above_70.get(resource) != matched_th and recipient:
                    await loop.run_in_executor(
                        None,
                        send_threshold_alert_email,
                        resource,
                        usage,
                        matched_th,
                        current.get("hostname", "system-host"),
                        current.get("timestamp", ""),
                        {"current_usage": f"{usage:.1f}%", "source": "background_vm_poller", "highest_threshold_crossed": matched_th},
                        None,
                        recipient,
                    )
                    logger.info(f"Automatic {resource} alert (tier {matched_th}%) sent to {recipient}")
                    previously_above_70[resource] = matched_th
                elif matched_th is None:
                    previously_above_70[resource] = None
        except Exception as exc:
            logger.warning(f"Background metrics poller encountered error: {exc}")
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: launch background poller
    poller_task = asyncio.create_task(periodic_metrics_poller(interval_seconds=60))
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


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"🚀 [HTTP {request.method}] {request.url.path}")
    response = await call_next(request)
    logger.info(f"✅ [HTTP {request.method}] {request.url.path} -> Status {response.status_code}")
    return response


@app.get("/health", tags=["Health"])
async def health_check():
    """Lightweight liveness endpoint for deployment and development probes."""
    return {"status": "healthy", "service": "reliability-agent-backend"}

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
app.include_router(remediation_router)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        reload=True,
    )
