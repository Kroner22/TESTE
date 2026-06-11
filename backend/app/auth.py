import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt as _bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db, Base
from sqlalchemy import Boolean, Column, Integer, String, DateTime, func, Text

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

SECRET_KEY = "omega-predictions-jwt-secret-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    plan = Column(String(16), default="free")
    credits = Column(Integer, default=0)
    requests_count = Column(Integer, default=0)
    requests_limit = Column(Integer, default=1000)
    telegram_chat_id = Column(String(64), nullable=True)
    whatsapp_phone = Column(String(32), nullable=True)
    api_key = Column(String(64), unique=True, nullable=True)
    notify_telegram = Column(Boolean, default=False)
    notify_whatsapp = Column(Boolean, default=False)
    notify_min_grade = Column(String(16), default="SOLID")
    stripe_customer_id = Column(String(128), nullable=True)
    stripe_subscription_id = Column(String(128), nullable=True)
    subscription_status = Column(String(32), default="inactive")
    reset_token = Column(Text, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


def generate_api_key() -> str:
    return f"om_{secrets.token_hex(32)}"


def generate_reset_token() -> str:
    return secrets.token_urlsafe(48)


def create_reset_token(user: User) -> str:
    token = generate_reset_token()
    user.reset_token = token
    user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
    return token


def verify_reset_token(user: User, token: str) -> bool:
    if not user.reset_token or not user.reset_token_expires:
        return False
    if user.reset_token != token:
        return False
    expires = user.reset_token_expires
    if expires.tzinfo is None:
        from datetime import timezone as tz
        expires = expires.replace(tzinfo=tz.utc)
    if datetime.now(timezone.utc) > expires:
        return False
    return True


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais invalidas",
        headers={"WWW-Authenticate": "Bearer"},
    )

    api_key = request.headers.get("X-API-Key")
    if api_key:
        user = db.query(User).filter(User.api_key == api_key).first()
        if user is None:
            raise credentials_exception
        return user

    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user


def track_usage(current_user: User, db: Session) -> None:
    current_user.requests_count = (current_user.requests_count or 0) + 1
    db.commit()


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
