from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal, Event, PaperTradeRecord, OpportunityRecord
from backend.app.plan_limiter import require_plan

router = APIRouter(prefix="/api/v1", tags=["performance"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/performance")
def performance_summary(
    db: Session = Depends(get_db),
    _=Depends(require_plan("paid")),
):
    total = db.query(func.count(PaperTradeRecord.id)).scalar() or 0
    closed = db.query(func.count(PaperTradeRecord.id)).filter(
        PaperTradeRecord.is_open == False).scalar() or 0
    winners = db.query(func.count(PaperTradeRecord.id)).filter(
        PaperTradeRecord.pnl > 0).scalar() or 0
    losers = db.query(func.count(PaperTradeRecord.id)).filter(
        PaperTradeRecord.pnl < 0).scalar() or 0
    total_pnl = db.query(func.sum(PaperTradeRecord.pnl)).filter(
        PaperTradeRecord.pnl.isnot(None)).scalar() or 0
    total_stake = db.query(func.sum(PaperTradeRecord.stake)).filter(
        PaperTradeRecord.is_open == False).scalar() or 0
    avg_pnl = float(total_pnl) / max(closed, 1)
    avg_confidence = db.query(func.avg(PaperTradeRecord.confidence)).scalar() or 0
    avg_ev = db.query(func.avg(OpportunityRecord.ev)).scalar() or 0

    # By grade breakdown
    grade_data = db.query(
        OpportunityRecord.value_grade,
        func.count(PaperTradeRecord.id),
        func.sum(PaperTradeRecord.pnl),
    ).join(
        PaperTradeRecord,
        OpportunityRecord.event_id == PaperTradeRecord.event_id,
        isouter=True,
    ).group_by(OpportunityRecord.value_grade).all()

    grades = []
    for g, cnt, pnl in grade_data:
        if cnt:
            grades.append({
                "grade": g,
                "trades": cnt,
                "pnl": round(float(pnl or 0), 2),
            })

    # Best/worst trades
    best = db.query(PaperTradeRecord).filter(
        PaperTradeRecord.pnl.isnot(None)
    ).order_by(PaperTradeRecord.pnl.desc()).first()

    worst = db.query(PaperTradeRecord).filter(
        PaperTradeRecord.pnl.isnot(None)
    ).order_by(PaperTradeRecord.pnl.asc()).first()

    return {
        "total_trades": total,
        "closed_trades": closed,
        "winners": winners,
        "losers": losers,
        "win_rate": round(winners / max(closed, 1) * 100, 1),
        "total_pnl": round(float(total_pnl), 2),
        "total_stake": round(float(total_stake), 2),
        "roi_pct": round(float(total_pnl) / max(float(total_stake), 0.01) * 100, 2),
        "avg_pnl_per_trade": round(avg_pnl, 2),
        "avg_confidence": round(float(avg_confidence), 3),
        "avg_ev_pct": round(float(avg_ev) * 100, 2),
        "by_grade": grades,
        "best_trade": {
            "event_id": best.event_id,
            "pnl": round(float(best.pnl), 2),
            "pnl_pct": round(float(best.pnl_pct), 2),
        } if best else None,
        "worst_trade": {
            "event_id": worst.event_id,
            "pnl": round(float(worst.pnl), 2),
            "pnl_pct": round(float(worst.pnl_pct), 2),
        } if worst else None,
    }


@router.get("/performance/trades")
def trade_history(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    outcome: str = Query(None, regex="^(winner|loser)$"),
    db: Session = Depends(get_db),
    _=Depends(require_plan("paid")),
):
    q = db.query(PaperTradeRecord, Event).join(
        Event, PaperTradeRecord.event_id == Event.event_id, isouter=True
    ).filter(PaperTradeRecord.is_open == False)

    if outcome == "winner":
        q = q.filter(PaperTradeRecord.pnl > 0)
    elif outcome == "loser":
        q = q.filter(PaperTradeRecord.pnl < 0)

    total = q.count()
    rows = q.order_by(PaperTradeRecord.entry_timestamp.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "trades": [
            {
                "position_id": t.position_id,
                "event_id": t.event_id,
                "sport": ev.sport if ev else None,
                "home_team": ev.home_team if ev else None,
                "away_team": ev.away_team if ev else None,
                "market": t.market,
                "outcome": t.outcome,
                "entry_odd": float(t.entry_odd),
                "exit_odd": float(t.exit_odd) if t.exit_odd else None,
                "stake": float(t.stake),
                "pnl": float(t.pnl) if t.pnl else None,
                "pnl_pct": float(t.pnl_pct) if t.pnl_pct else None,
                "confidence": float(t.confidence) if t.confidence else None,
                "entry_timestamp": t.entry_timestamp.isoformat() if t.entry_timestamp else None,
                "exit_timestamp": t.exit_timestamp.isoformat() if t.exit_timestamp else None,
            }
            for t, ev in rows
        ],
    }
