from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal, Event, OddsRecord, OpportunityRecord, AlertRecord
from backend.app.plan_limiter import require_plan

router = APIRouter(prefix="/api/v1", tags=["mvp"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/events")
def list_events(
    sport: str = Query(None),
    status: str = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(Event)
    if sport:
        q = q.filter(Event.sport == sport)
    if status:
        q = q.filter(Event.status == status)
    q = q.order_by(Event.start_time).limit(limit)
    return [{
        "event_id": e.event_id,
        "sport": e.sport,
        "home_team": e.home_team,
        "away_team": e.away_team,
        "start_time": e.start_time.isoformat(),
        "status": e.status,
    } for e in q]


@router.get("/events/{event_id}/odds")
def get_odds(event_id: str, limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    odds = (
        db.query(OddsRecord)
        .filter(OddsRecord.event_id == event_id)
        .order_by(OddsRecord.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [{
        "market": o.market,
        "outcome": o.outcome,
        "bookmaker": o.bookmaker,
        "odd": float(o.odd),
        "timestamp": o.timestamp.isoformat(),
        "is_opening": o.is_opening,
    } for o in odds]


@router.get("/opportunities")
def list_opportunities(
    min_ev: float = Query(0, ge=0),
    min_confidence: float = Query(0, ge=0, le=1),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _=Depends(require_plan("paid")),
):
    q = (
        db.query(OpportunityRecord)
        .filter(OpportunityRecord.ev >= min_ev)
        .filter(OpportunityRecord.confidence_score >= min_confidence)
        .order_by(OpportunityRecord.ev.desc(), OpportunityRecord.confidence_score.desc())
        .limit(limit)
    )
    return [{
        "event_id": o.event_id,
        "market": o.market,
        "outcome": o.outcome,
        "bookmaker": o.bookmaker,
        "odd": float(o.odd),
        "ev": float(o.ev) * 100,
        "fair_prob": float(o.fair_prob) * 100,
        "implied_prob": float(o.implied_prob) * 100,
        "confidence": float(o.confidence_score),
        "edge_score": float(o.edge_score),
        "kelly_stake": float(o.kelly_stake),
        "value_grade": o.value_grade,
        "risk_level": o.risk_level,
    } for o in q]


@router.get("/alerts")
def list_alerts(
    severity: str = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _=Depends(require_plan("paid")),
):
    q = db.query(AlertRecord)
    if severity:
        q = q.filter(AlertRecord.severity == severity)
    q = q.order_by(AlertRecord.created_at.desc()).limit(limit)
    return [{
        "event_id": a.event_id,
        "alert_type": a.alert_type,
        "severity": a.severity,
        "message": a.message,
        "ev_value": float(a.ev_value) if a.ev_value else None,
        "created_at": a.created_at.isoformat(),
    } for a in q]
