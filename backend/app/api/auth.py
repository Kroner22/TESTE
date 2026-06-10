from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import (
    User, hash_password, verify_password,
    create_access_token, get_current_user,
    generate_api_key,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


from datetime import datetime

class UserResponse(BaseModel):
    id: int
    email: str
    plan: str
    credits: int
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class DashboardResponse(BaseModel):
    id: int
    email: str
    plan: str
    credits: int
    requests_count: int
    requests_remaining: int
    api_key: Optional[str] = None
    has_api_key: bool

    class Config:
        from_attributes = True


@router.post("/register", status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email ja cadastrado")

    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        plan="free",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.email, "plan": user.plan, "user_id": user.id})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "plan": user.plan,
        },
    }


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email ou senha incorretos")

    token = create_access_token({"sub": user.email, "plan": user.plan, "user_id": user.id})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "plan": user.plan,
        },
    }


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/dashboard")
def dashboard(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "plan": current_user.plan,
        "credits": current_user.credits,
        "requests_count": current_user.requests_count or 0,
        "requests_limit": current_user.requests_limit or 1000,
        "requests_remaining": (current_user.requests_limit or 1000) - (current_user.requests_count or 0),
        "has_api_key": bool(current_user.api_key),
        "api_key": current_user.api_key,
    }


@router.post("/api-key")
def generate_new_api_key(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.api_key = generate_api_key()
    db.commit()
    return {"api_key": current_user.api_key, "detail": "Chave de API gerada com sucesso"}


@router.delete("/api-key")
def revoke_api_key(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.api_key = None
    db.commit()
    return {"detail": "Chave de API revogada com sucesso"}
