from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request

# Load .env into os.environ so providers can find API keys via os.getenv
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    try:
        import dotenv
        dotenv.load_dotenv(str(_env_path), override=True)
    except ImportError:
        pass
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .api.health import router as health_router
from .api.value import router as value_router
from .api.arbitrage import router as arbitrage_router
from .api.mvp import router as mvp_router
from .api.clv import router as clv_router
from .api.auth import router as auth_router
from .api.predictions import router as predictions_router
from .api.performance import router as performance_router
from .ws.live import router as ws_router
from .log_config import configure_logging, get_logger
from .middleware.logging import RateLimitMiddleware, RequestLoggingMiddleware
from .monitoring.metrics import metrics_exporter, record_http
from .monitoring.tracing import setup_tracing
from .settings import Settings, get_settings
from .cache import close_redis
from .middleware.rate_limit import close_rate_limiter
from .tasks.scanner import start_scanner, stop_scanner
from .database import init_db
from backend.services.ingestion import OddsIngestionService

ingestion_service = OddsIngestionService()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup/shutdown lifecycle."""
    settings = get_settings()

    # Startup
    configure_logging(settings)
    logger = get_logger("sports-quant")
    logger.info("starting", environment=settings.environment.value)

    init_db()
    logger.info("database_initialized")

    setup_tracing(settings)

    from .ws.live import manager
    async def _broadcast(msg: dict):
        await manager.broadcast("live", msg)
    ingestion_service.set_broadcast_callback(_broadcast)

    await ingestion_service.start()
    logger.info("ingestion_service_started")

    if settings.scan_enabled:
        await start_scanner(
            interval=settings.scan_interval_seconds,
            total_stake=__import__("decimal").Decimal(str(settings.scan_total_stake)),
            min_profit_pct=settings.scan_min_profit_pct,
        )

    yield

    # Shutdown
    logger.info("shutting_down")
    await ingestion_service.stop()
    await stop_scanner()
    await close_redis()
    await close_rate_limiter()
    logger.info("shutdown_complete")


app = FastAPI(
    title=get_settings().project_name,
    version=get_settings().version,
    lifespan=lifespan,
    docs_url="/docs" if get_settings().is_development else None,
    redoc_url="/redoc" if get_settings().is_development else None,
)


# ── CORS ─────────────────────────────────────────────────────────
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Middleware (order matters: outermost first) ──────────────────
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)


# ── Metrics middleware ───────────────────────────────────────────
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    import time
    start = time.monotonic()
    response = await call_next(request)
    duration = time.monotonic() - start
    record_http(request.method, request.url.path, response.status_code, duration)
    return response


# ── Global error handler ─────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger = get_logger("error")
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": str(exc) if settings.debug else "An unexpected error occurred",
        },
    )


# ── Routes ───────────────────────────────────────────────────────
app.include_router(health_router)
app.include_router(value_router)
app.include_router(arbitrage_router)
app.include_router(mvp_router)
app.include_router(clv_router)
app.include_router(auth_router)
app.include_router(predictions_router)
app.include_router(performance_router)
app.include_router(ws_router)


@app.get("/metrics")
async def metrics():
    return metrics_exporter(Request)


@app.get("/")
async def root():
    return {
        "name": settings.project_name,
        "version": settings.version,
        "docs": "/docs",
        "health": "/health/live",
    }
