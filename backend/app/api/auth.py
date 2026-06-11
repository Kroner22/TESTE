import os
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
        "subscription_status": current_user.subscription_status or "inactive",
        "has_subscription": bool(current_user.stripe_subscription_id),
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


# ── Telegram ──────────────────────────────────────────────────


class TelegramLinkRequest(BaseModel):
    chat_id: str


@router.post("/telegram/link")
def link_telegram(
    req: TelegramLinkRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.telegram_chat_id = req.chat_id
    current_user.notify_telegram = True
    db.commit()
    return {"detail": "Telegram vinculado com sucesso", "chat_id": req.chat_id}


@router.delete("/telegram/link")
def unlink_telegram(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.telegram_chat_id = None
    current_user.notify_telegram = False
    db.commit()
    return {"detail": "Telegram desvinculado com sucesso"}


# ── Notification Preferences ──────────────────────────────────


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    token: str
    new_password: str


class NotificationPreferences(BaseModel):
    notify_telegram: bool = False
    notify_whatsapp: bool = False
    notify_min_grade: str = "SOLID"


@router.get("/notifications")
def get_notification_prefs(
    current_user: User = Depends(get_current_user),
):
    return {
        "notify_telegram": bool(current_user.notify_telegram),
        "notify_whatsapp": bool(current_user.notify_whatsapp),
        "notify_min_grade": current_user.notify_min_grade or "SOLID",
        "telegram_chat_id": current_user.telegram_chat_id,
    }


@router.put("/notifications")
def update_notification_prefs(
    prefs: NotificationPreferences,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.notify_telegram = prefs.notify_telegram
    current_user.notify_whatsapp = prefs.notify_whatsapp
    current_user.notify_min_grade = prefs.notify_min_grade
    db.commit()
    return {"detail": "Preferencias de notificacao atualizadas"}


# ── Password Reset ────────────────────────────────────────────


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        return {"detail": "Se o email existir, voce recebera um link de recuperacao"}
    from backend.app.auth import create_reset_token
    token = create_reset_token(user)
    db.commit()
    reset_link = f"{os.getenv('DOMAIN', 'http://localhost:8000')}/app/#/reset-password?token={token}&email={req.email}"
    print(f"[PASSWORD RESET] Link para {req.email}: {reset_link}")
    return {"detail": "Se o email existir, voce recebera um link de recuperacao"}


@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(400, "Link invalido ou expirado")
    from backend.app.auth import verify_reset_token
    if not verify_reset_token(user, req.token):
        raise HTTPException(400, "Link invalido ou expirado")
    user.password_hash = hash_password(req.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()
    return {"detail": "Senha redefinida com sucesso"}


@router.post("/notifications/test")
def test_notification(
    current_user: User = Depends(get_current_user),
):
    if not current_user.telegram_chat_id:
        raise HTTPException(400, "Nenhum Telegram vinculado")
    if not current_user.notify_telegram:
        raise HTTPException(400, "Notificacoes Telegram desativadas")

    import asyncio
    from backend.notifications.telegram import send_message
    text = (
        "\u2705 <b>Teste de Notificacao Omega Predictions</b>\n"
        "Se voce esta vendo esta mensagem, sua integracao "
        "com Telegram esta funcionando perfeitamente!"
    )
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(send_message(current_user.telegram_chat_id, text))
    except RuntimeError:
        asyncio.run(send_message(current_user.telegram_chat_id, text))

    return {"detail": "Mensagem de teste enviada para o Telegram"}
