from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ...domains.value.detector import ValueDetector
from ...domains.value.models import MarketOdds, ValueOpportunity, ValueGrade
from ..cache import cache_get_or_compute
from ..log_config import get_logger
from ..monitoring.metrics import value_opportunities_total, record_http
from ..plan_limiter import require_plan

router = APIRouter(prefix="/api/v1/value", tags=["value"])
logger = get_logger(__name__)

_detector = ValueDetector()


def _market_odds_to_domain(m: dict) -> MarketOdds:
    return MarketOdds(
        event_id=m["event_id"],
        sport=m["sport"],
        home_team=m["home_team"],
        away_team=m["away_team"],
        market=m.get("market", "h2h"),
        home_odd=Decimal(str(m["home_odd"])),
        away_odd=Decimal(str(m["away_odd"])),
        draw_odd=Decimal(str(m["draw_odd"])) if m.get("draw_odd") else None,
        home_prob=Decimal(str(m["home_prob"])) if m.get("home_prob") else None,
        away_prob=Decimal(str(m["away_prob"])) if m.get("away_prob") else None,
        draw_prob=Decimal(str(m["draw_prob"])) if m.get("draw_prob") else None,
    )


@router.post("/scan")
async def scan_opportunities(
    markets: list[dict],
    min_ev: float = Query(0.0, ge=0),
    min_confidence: float = Query(0.0, ge=0, le=1),
    min_grade: Optional[str] = Query(None),
    _=Depends(require_plan("paid")),
):
    """Scan market odds for value betting opportunities."""
    domain_markets = [_market_odds_to_domain(m) for m in markets]
    opportunities = _detector.scan(domain_markets)

    if min_ev > 0:
        opportunities = [o for o in opportunities if o.expected_value >= Decimal(str(min_ev))]
    if min_confidence > 0:
        opportunities = [o for o in opportunities if o.confidence_score >= Decimal(str(min_confidence))]
    if min_grade:
        opportunities = [o for o in opportunities if o.value_grade.value == min_grade.upper()]

    for o in opportunities:
        value_opportunities_total.labels(
            sport=o.sport, grade=o.value_grade.value,
        ).inc()

    return {
        "count": len(opportunities),
        "opportunities": [_serialize_value(o) for o in opportunities],
    }


@router.get("/opportunities/{event_id}")
async def get_opportunity(event_id: str):
    """Get a specific value opportunity by event ID (from cache)."""
    data = await cache_get_or_compute(
        f"value:{event_id}",
        lambda: None,
        ttl=15,
    )
    if data is None:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=404,
            content={"error": "opportunity_not_found", "event_id": event_id},
        )
    return data


def _serialize_value(o: ValueOpportunity) -> dict:
    return {
        "event_id": o.event_id,
        "sport": o.sport,
        "home_team": o.home_team,
        "away_team": o.away_team,
        "market": o.market,
        "outcome": o.outcome,
        "odd": float(o.odd),
        "fair_odd": float(o.fair_odd),
        "expected_value": float(o.expected_value),
        "edge_pct": float(o.edge_pct),
        "value_grade": o.value_grade.value,
        "kelly_stake": float(o.kelly_stake),
        "kelly_fraction": float(o.kelly_fraction),
        "confidence_score": float(o.confidence_score),
        "risk_level": o.risk_level.value if hasattr(o.risk_level, "value") else str(o.risk_level),
        "detected_at": o.detected_at.isoformat() if hasattr(o.detected_at, "isoformat") else str(o.detected_at),
        "expires_at": o.expires_at.isoformat() if o.expires_at and hasattr(o.expires_at, "isoformat") else str(o.expires_at),
    }
