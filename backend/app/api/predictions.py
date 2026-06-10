from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal, Event, OpportunityRecord
from backend.app.plan_limiter import require_plan

router = APIRouter(prefix="/api/v1", tags=["predictions"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/predictions")
def list_predictions(
    sport: str = Query(None),
    min_ev: float = Query(0, ge=0),
    min_confidence: float = Query(0, ge=0, le=1),
    grade: str = Query(None),
    risk: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _=Depends(require_plan("paid")),
):
    q = (
        db.query(OpportunityRecord, Event)
        .join(Event, OpportunityRecord.event_id == Event.event_id)
        .filter(OpportunityRecord.is_active == True)
        .filter(OpportunityRecord.ev >= min_ev)
        .filter(OpportunityRecord.confidence_score >= min_confidence)
    )
    if sport:
        q = q.filter(Event.sport == sport)
    if grade:
        q = q.filter(OpportunityRecord.value_grade == grade.upper())
    if risk:
        q = q.filter(OpportunityRecord.risk_level == risk.upper())

    total = q.count()
    rows = q.order_by(OpportunityRecord.ev.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "predictions": [
            {
                "event_id": opp.event_id,
                "sport": ev.sport,
                "home_team": ev.home_team,
                "away_team": ev.away_team,
                "start_time": ev.start_time.isoformat() if ev.start_time else None,
                "market": opp.market,
                "outcome": opp.outcome,
                "odd": float(opp.odd),
                "ev_pct": round(float(opp.ev) * 100, 2),
                "fair_prob_pct": round(float(opp.fair_prob) * 100, 1),
                "implied_prob_pct": round(float(opp.implied_prob) * 100, 1),
                "edge_score": float(opp.edge_score),
                "confidence": float(opp.confidence_score),
                "kelly_stake_pct": round(float(opp.kelly_stake) * 100, 1),
                "value_grade": opp.value_grade,
                "risk_level": opp.risk_level,
            }
            for opp, ev in rows
        ],
    }
