from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from .auth import User, get_current_user, track_usage
from .database import get_db

PLAN_LIMITS: dict[str, int] = {
    "free": 10,
    "paid": 100,
    "admin": 1000,
}

WINDOW_SECONDS = 60


def get_plan_limit(plan: str) -> int:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def require_plan(min_plan: str = "paid"):
    def _check(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if current_user.plan == "free" and min_plan != "free":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Plano gratuito nao tem acesso a este recurso. Assine o plano paid.",
            )
        track_usage(current_user, db)
        return current_user
    return _check


def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.plan != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return current_user
