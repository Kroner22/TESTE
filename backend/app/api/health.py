from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter

from ..cache import cache_heatlbeat
from ..log_config import get_logger
from ..settings import get_settings

router = APIRouter(tags=["health"])
logger = get_logger(__name__)

_start_time = time.monotonic()


@router.get("/health/live")
async def liveness():
    """Kubernetes liveness probe — always responds if process is alive."""
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": round(time.monotonic() - _start_time, 1),
    }


@router.get("/health/ready")
async def readiness():
    """Kubernetes readiness probe — checks Redis, domain engine."""
    checks = {
        "app": "ok",
        "uptime_seconds": round(time.monotonic() - _start_time, 1),
    }

    redis_status = await cache_heatlbeat()
    checks["redis"] = redis_status["status"]

    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503

    from fastapi.responses import JSONResponse
    return JSONResponse(
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
        status_code=status_code,
    )


@router.get("/health/startup")
async def startup():
    """Kubernetes startup probe — quick check."""
    return {"status": "started"}


@router.get("/health/info")
async def info():
    """Application info endpoint."""
    settings = get_settings()
    return {
        "name": settings.project_name,
        "version": settings.version,
        "environment": settings.environment.value,
        "debug": settings.debug,
    }


@router.get("/health/mode")
async def runtime_mode():
    """Runtime mode and provider status."""
    from backend.services.mode import get_mode_manager
    from backend.services.providers.real.provider_registry import get_registry
    from backend.services.providers.real.provider_health_monitor import get_health_monitor

    mode = get_mode_manager()
    registry = get_registry()
    health = get_health_monitor()

    return {
        "mode": mode.get_summary(),
        "providers": registry.get_summary(),
        "health": health.get_global_health(),
    }


@router.get("/health/real-market")
async def real_market_status():
    """Real-market operational dashboard."""
    from backend.services.mode import get_mode_manager
    from backend.services.providers.real.provider_registry import get_registry
    from backend.services.providers.real.provider_health_monitor import get_health_monitor
    from backend.app.database import SessionLocal
    from backend.app.models.real_market import RealMarketEvent, RealMarketOdds, RealMarketPaperTrade, RealMarketClvRecord
    from datetime import datetime, timezone
    import time as time_mod

    mode = get_mode_manager()
    registry = get_registry()
    health = get_health_monitor()

    # Real-market DB counts
    try:
        db = SessionLocal()
        events = db.query(RealMarketEvent).count()
        odds = db.query(RealMarketOdds).count()
        trades = db.query(RealMarketPaperTrade).count()
        clv = db.query(RealMarketClvRecord).count()
        db.close()
    except Exception:
        events = odds = trades = clv = 0

    active_providers = []
    failed_providers = []
    for name, info in registry.get_summary().get("providers", {}).items():
        if info.get("healthy"):
            active_providers.append(name)
        else:
            failed_providers.append(name)

    ranking = health.get_global_health().get("ranking", [])

    return {
        "mode": mode.mode.value,
        "market_type": mode.market_type,
        "providers_active": active_providers,
        "providers_failed": failed_providers,
        "provider_ranking": ranking[:5],
        "events_collected": events,
        "odds_collected": odds,
        "real_paper_trades": trades,
        "real_clv_records": clv,
        "latency_ms": round(ranking[0].get("avg_latency_ms", 0), 1) if ranking else 0,
        "uptime_seconds": round(time_mod.monotonic(), 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/real-market/stats")
async def real_market_stats():
    """Real-market telemetry — counts, sports, bookmakers, providers."""
    from backend.services.mode import get_mode_manager
    from backend.services.providers.real.provider_registry import get_registry
    from backend.app.database import SessionLocal
    from backend.app.models.real_market import RealMarketEvent, RealMarketOdds
    from sqlalchemy import func
    import time as time_mod

    mode = get_mode_manager()
    registry = get_registry()

    db = SessionLocal()
    try:
        events = db.query(RealMarketEvent).count()
        odds = db.query(RealMarketOdds).count()
        sports = [r[0] for r in db.query(RealMarketEvent.sport).distinct().order_by(RealMarketEvent.sport).all()]
        bookmakers = [r[0] for r in db.query(RealMarketOdds.bookmaker).distinct().order_by(RealMarketOdds.bookmaker).all()]
        latency_subq = (
            db.query(RealMarketOdds.latency_ms)
            .filter(RealMarketOdds.latency_ms.isnot(None))
            .subquery()
        )
        avg_latency = db.query(func.avg(latency_subq.c.latency_ms)).scalar() or 0
    finally:
        db.close()

    prov_summary = registry.get_summary().get("providers", {})
    providers_live = [n for n, i in prov_summary.items() if i.get("healthy")]
    providers_failed = [n for n, i in prov_summary.items() if not i.get("healthy")]

    return {
        "mode": mode.mode.value,
        "events": events,
        "odds": odds,
        "sports": sports,
        "bookmakers": bookmakers,
        "avg_latency_ms": round(float(avg_latency), 1),
        "providers_live": providers_live,
        "providers_failed": providers_failed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
