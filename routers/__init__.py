from .cpu_router import router as cpu_router
from .disk_router import router as disk_router
from .incident_router import router as incident_router
from .memory_router import router as memory_router
from .metrics_router import router as metrics_router
from .orchestrator_router import router as orchestrator_router

router = incident_router

__all__ = [
    "router",
    "incident_router",
    "cpu_router",
    "disk_router",
    "memory_router",
    "metrics_router",
    "orchestrator_router",
]
