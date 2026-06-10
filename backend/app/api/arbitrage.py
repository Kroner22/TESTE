from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Query

from ...domains.arbitrage.models import (
    BookmakerOdds, ArbFilter, ArbGrade, StakeMethod,
)
from ...domains.arbitrage.engine import ArbitrageEngine, EngineConfig
from ..cache import cache_get_or_compute
from ..log_config import get_logger
from ..monitoring.metrics import arb_opportunities_total

router = APIRouter(prefix="/api/v1/arbitrage", tags=["arbitrage"])
logger = get_logger(__name__)

_engine = ArbitrageEngine(
    config=EngineConfig(
        filter_config=ArbFilter(),
        min_grade=ArbGrade.MARGINAL,
    )
)


def _bookmaker_odds_from_dict(d: dict) -> BookmakerOdds:
    return BookmakerOdds(
        bookmaker=d["bookmaker"],
        outcome=d["outcome"],
        odd=Decimal(str(d["odd"])),
        max_stake=Decimal(str(d["max_stake"])) if d.get("max_stake") else None,
        commission=Decimal(str(d.get("commission", "0"))),
        liquidity=Decimal(str(d.get("liquidity", "0"))),
    )


@router.post("/scan")
async def scan_arbitrage(
    markets: dict[str, dict[str, list[dict]]],
    total_stake: float = Query(100.0, gt=0),
    min_profit_pct: float = Query(0.005, ge=0),
):
    """Scan cross-bookmaker odds for arbitrage opportunities."""
    parsed = {}
    for key, outcomes in markets.items():
        parsed[key] = {
            outcome: [_bookmaker_odds_from_dict(b) for b in odds_list]
            for outcome, odds_list in outcomes.items()
        }

    result = _engine.scan(parsed)

    for opp in result.opportunities:
        arb_opportunities_total.labels(
            sport=opp.sport,
            arb_type=opp.arb_type.value,
            grade=opp.grade.value,
        ).inc()

    return {
        "count": result.n_opportunities,
        "opportunities": [_serialize_arb(o) for o in result.opportunities],
    }


@router.get("/opportunities")
async def list_opportunities(
    min_grade: Optional[str] = Query(None),
    sport: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """List current arbitrage opportunities (from engine state)."""
    snapshot = _engine.snapshot()
    opportunities = snapshot.opportunities

    if min_grade:
        try:
            grade = ArbGrade[min_grade.upper()]
            opportunities = [o for o in opportunities if o.grade.value >= grade.value]
        except (KeyError, ValueError):
            pass

    if sport:
        opportunities = [o for o in opportunities if o.sport == sport]

    return {
        "count": len(opportunities[:limit]),
        "total_available": snapshot.filtered_count,
        "opportunities": [_serialize_arb(o) for o in opportunities[:limit]],
    }


@router.get("/engine/status")
async def engine_status():
    """Get arbitrage engine status and statistics."""
    snapshot = _engine.snapshot()
    return {
        "status": "running",
        "filtered_opportunities": snapshot.filtered_count,
        "total_scanned": snapshot.total_count,
        "n_elite": snapshot.n_elite,
        "n_strong": snapshot.n_strong,
        "n_solid": snapshot.n_solid,
        "n_marginal": snapshot.n_marginal,
        "best_profit_pct": float(snapshot.best_opportunity.profit_pct) if snapshot.best_opportunity else 0,
        "avg_profit_pct": float(snapshot.total_profit_pct),
    }


def _serialize_arb(o) -> dict:
    return {
        "event_id": o.event_id,
        "sport": o.sport,
        "home_team": o.home_team,
        "away_team": o.away_team,
        "market": o.market,
        "arb_type": o.arb_type.value,
        "total_stake": float(o.total_stake),
        "guaranteed_return": float(o.guaranteed_return),
        "profit": float(o.profit),
        "profit_pct": float(o.profit_pct),
        "grade": o.grade.value,
        "is_actionable": o.is_actionable,
        "legs": [
            {
                "bookmaker": l.bookmaker,
                "outcome": l.outcome,
                "odd": float(l.odd),
                "stake": float(l.stake),
                "return_amount": float(l.return_amount),
                "commission": float(l.commission),
            }
            for l in o.legs
        ],
        "detected_at": o.detected_at.isoformat(),
    }
