"""FastAPI application entrypoint for the merged Lingjing services."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import setup_websocket_logging
from app.core.responses import install_exception_handlers, json_success
from app.db.session import create_all_for_local_dev
from app.modules.agents.router import router as agents_router
from app.modules.envs.router import router as envs_router
from app.modules.ai.router import router as ai_router
from app.modules.engine_control.router import router as engine_control_router
from app.modules.realtime.router import router as realtime_router
from app.modules.simulation.router import router as simulation_router
from app.modules.sse.router import router as sse_router
from app.modules.uav.router import router as uav_router
from app.modules.udp.router import router as udp_router
from app.modules.weather.router import router as weather_router


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize local SQLite tables during development startup."""

    setup_websocket_logging()
    create_all_for_local_dev()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
install_exception_handlers(app)

app.include_router(simulation_router)
app.include_router(agents_router)
app.include_router(envs_router)
app.include_router(ai_router)
app.include_router(engine_control_router)
app.include_router(uav_router)
app.include_router(realtime_router)
app.include_router(weather_router)
app.include_router(sse_router)
app.include_router(udp_router)


@app.get("/health")
def health():
    """Lightweight health check using the Java-compatible response envelope."""

    return json_success({"status": "ok"})
