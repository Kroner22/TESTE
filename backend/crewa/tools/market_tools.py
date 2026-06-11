"""Market tools for CrewAI agents — scan odds, detect opportunities, track movements."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional

# ── Inline imports to avoid circular deps at module level ──

class ScanMarketsInput(BaseModel):
    sport: Optional[str] = Field(None, description="Filter by sport (soccer, basketball, etc.)")
    min_ev: float = Field(0.01, description="Minimum expected value (1% = 0.01)")
    min_confidence: float = Field(0.3, description="Minimum confidence score (0-1)")
    limit: int = Field(20, description="Max results to return")


class ScanMarketsTool(BaseTool):
    name: str = "scan_markets"
    description: str = "Scan all available markets for value betting opportunities. Returns EV, grade, confidence, risk."
    args_schema: type = ScanMarketsInput

    def _run(self, sport: Optional[str] = None, min_ev: float = 0.01,
             min_confidence: float = 0.3, limit: int = 20) -> list[dict]:
        from backend.app.database import SessionLocal, OpportunityRecord, Event
        db = SessionLocal()
        q = db.query(OpportunityRecord, Event).join(
            Event, OpportunityRecord.event_id == Event.event_id
        ).filter(OpportunityRecord.is_active == True)
        if sport:
            q = q.filter(Event.sport == sport)
        q = q.order_by(OpportunityRecord.ev.desc()).limit(limit)
        results = []
        for opp, evt in q:
            if opp.ev and float(opp.ev) < min_ev:
                continue
            if opp.confidence_score and float(opp.confidence_score) < min_confidence:
                continue
            results.append({
                "event_id": opp.event_id,
                "sport": evt.sport,
                "home_team": evt.home_team,
                "away_team": evt.away_team,
                "outcome": opp.outcome,
                "odd": float(opp.odd) if opp.odd else None,
                "ev_pct": round(float(opp.ev) * 100, 2) if opp.ev else 0,
                "confidence": round(float(opp.confidence_score), 3) if opp.confidence_score else 0,
                "value_grade": opp.value_grade,
                "risk_level": opp.risk_level,
                "kelly_stake_pct": round(float(opp.kelly_stake) * 100, 2) if opp.kelly_stake else 0,
                "detected_at": opp.detected_at.isoformat() if opp.detected_at else None,
            })
        db.close()
        return results


class GetMarketDetailInput(BaseModel):
    event_id: str = Field(..., description="Event ID to get details for")


class GetMarketDetailTool(BaseTool):
    name: str = "get_market_detail"
    description: str = "Get detailed market information for a specific event including all outcomes and bookmakers."
    args_schema: type = GetMarketDetailInput

    def _run(self, event_id: str) -> dict:
        from backend.app.database import SessionLocal, Event, OddsRecord
        db = SessionLocal()
        evt = db.query(Event).filter(Event.event_id == event_id).first()
        if not evt:
            db.close()
            return {"error": "Event not found"}
        odds = db.query(OddsRecord).filter(OddsRecord.event_id == event_id).all()
        outcomes = {}
        for o in odds:
            outcomes.setdefault(o.outcome, []).append({
                "bookmaker": o.bookmaker,
                "odd": float(o.odd) if o.odd else None,
            })
        result = {
            "event_id": evt.event_id,
            "sport": evt.sport,
            "home_team": evt.home_team,
            "away_team": evt.away_team,
            "start_time": evt.start_time.isoformat() if evt.start_time else None,
            "status": evt.status,
            "outcomes": outcomes,
        }
        db.close()
        return result


class GetTrendingMarketsInput(BaseModel):
    hours: int = Field(24, description="Lookback window in hours")
    limit: int = Field(10, description="Max results")


class GetTrendingMarketsTool(BaseTool):
    name: str = "get_trending_markets"
    description: str = "Find markets with unusual odds movement or high volatility in recent hours."
    args_schema: type = GetTrendingMarketsInput

    def _run(self, hours: int = 24, limit: int = 10) -> list[dict]:
        from backend.app.database import SessionLocal, OddsRecord
        from sqlalchemy import func
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        db = SessionLocal()
        rows = db.query(
            OddsRecord.event_id, OddsRecord.outcome,
            func.min(OddsRecord.odd).label("min_odd"),
            func.max(OddsRecord.odd).label("max_odd"),
            func.count(OddsRecord.id).label("ticks"),
        ).filter(OddsRecord.timestamp >= cutoff) \
         .group_by(OddsRecord.event_id, OddsRecord.outcome) \
         .order_by(func.count(OddsRecord.id).desc()).limit(limit).all()
        results = []
        for r in rows:
            pct_change = ((float(r.max_odd) - float(r.min_odd)) / float(r.min_odd)) * 100 if r.min_odd else 0
            results.append({
                "event_id": r.event_id,
                "outcome": r.outcome,
                "min_odd": float(r.min_odd) if r.min_odd else None,
                "max_odd": float(r.max_odd) if r.max_odd else None,
                "change_pct": round(pct_change, 2),
                "odds_ticks": r.ticks,
            })
        db.close()
        return results
