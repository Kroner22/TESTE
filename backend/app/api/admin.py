from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.auth import User, get_current_user
from backend.app.database import SessionLocal, Event, OddsRecord, OpportunityRecord, PaperTradeRecord
from backend.app.plan_limiter import require_admin

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/stats")
def admin_stats(
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    total_users = db.query(func.count(User.id)).scalar() or 0
    users_by_plan = db.query(User.plan, func.count(User.id)).group_by(User.plan).all()
    total_events = db.query(func.count(Event.id)).scalar() or 0
    total_odds = db.query(func.count(OddsRecord.id)).scalar() or 0
    total_opps = db.query(func.count(OpportunityRecord.id)).scalar() or 0
    total_trades = db.query(func.count(PaperTradeRecord.id)).scalar() or 0
    total_pnl = db.query(func.sum(PaperTradeRecord.pnl)).filter(
        PaperTradeRecord.pnl.isnot(None)).scalar() or 0

    grades = db.query(
        OpportunityRecord.value_grade,
        func.count(OpportunityRecord.id),
    ).group_by(OpportunityRecord.value_grade).all()

    sports = db.query(Event.sport, func.count(Event.id)).group_by(Event.sport).all()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "users": {
            "total": total_users,
            "by_plan": {p: c for p, c in users_by_plan},
        },
        "data": {
            "events": total_events,
            "odds": total_odds,
            "opportunities": total_opps,
            "paper_trades": total_trades,
            "total_pnl": round(float(total_pnl), 2),
        },
        "opportunities_by_grade": {g: c for g, c in grades},
        "events_by_sport": {s: c for s, c in sports},
    }


@router.get("/users")
def list_users(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    total = db.query(func.count(User.id)).scalar() or 0
    users = db.query(User).order_by(User.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "plan": u.plan,
                "credits": u.credits,
                "requests_count": u.requests_count or 0,
                "requests_limit": u.requests_limit or 1000,
                "telegram_chat_id": u.telegram_chat_id,
                "notify_telegram": bool(u.notify_telegram),
                "has_api_key": bool(u.api_key),
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
    }


class PlanUpdateRequest(BaseModel):
    plan: str


@router.put("/users/{user_id}/plan")
def update_user_plan(
    user_id: int,
    req: PlanUpdateRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    if req.plan not in ("free", "paid", "admin"):
        raise HTTPException(400, "Plano invalido. Use: free, paid, admin")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Usuario nao encontrado")
    user.plan = req.plan
    db.commit()
    return {"detail": f"Plano do usuario {user.email} atualizado para {req.plan}"}


@router.post("/seed/predictions")
def reseed_predictions(
    _=Depends(require_admin),
):
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "scripts/seed_predictions.py"],
        capture_output=True, text=True, timeout=120,
    )
    return {
        "detail": "Seed concluido",
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }
