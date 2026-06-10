"""Teste Dia 4 - Rate limiting por plano e tier gating"""
import sys, os
sys.path.insert(0, r'C:\Users\cex\Desktop\OmegaPredictions')
os.chdir(r'C:\Users\cex\Desktop\OmegaPredictions')
os.environ['RUNTIME_MODE'] = 'SIMULATION'
os.environ['MVP_DB_PATH'] = 'data/test_plan.db'
os.environ['STRUCTLOG_LOG_LEVEL'] = 'CRITICAL'
import logging; logging.disable(logging.CRITICAL)

from backend.app.database import Base, engine
from backend.app.auth import User
Base.metadata.create_all(bind=engine)
print('[OK] User table created')

from backend.app.api.auth import router as auth_router
from backend.app.api.mvp import router as mvp_router
from backend.app.middleware.logging import RateLimitMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()
app.add_middleware(RateLimitMiddleware)
app.include_router(auth_router)
app.include_router(mvp_router)

client = TestClient(app)

import uuid
email = f'paid{uuid.uuid4().hex[:8]}@omega.com'
email_free = f'free{uuid.uuid4().hex[:8]}@omega.com'

from backend.app.auth import hash_password

# Register free user
r = client.post('/api/v1/auth/register', json={'email': email_free, 'password': '123456'})
free_token = r.json()['access_token']
print(f'[OK] Free user registered: plan={r.json()["user"]["plan"]}')

# Manually create paid user with valid bcrypt hash
PWD = "senha_paid"
from backend.app.database import SessionLocal
db = SessionLocal()
user = db.query(User).filter(User.email == email).first()
if not user:
    user = User(email=email, password_hash=hash_password(PWD), plan="paid")
    db.add(user)
    db.commit()
    db.refresh(user)
print(f'[OK] Paid user created in DB: id={user.id} plan={user.plan}')
db.close()

# Login as paid user
r = client.post('/api/v1/auth/login', json={'email': email, 'password': PWD})
assert r.status_code == 200, f'Paid login failed: {r.status_code} {r.json()}'
paid_token = r.json()['access_token']
print(f'[OK] Paid user token obtained')

# ── Test 1: Free user has 10 req/min limit ──
from backend.app.plan_limiter import get_plan_limit
assert get_plan_limit("free") == 10
assert get_plan_limit("paid") == 100
print('[OK] Plan limits configured: free=10, paid=100')

# ── Test 2: Paid user can access /opportunities (paid-only) ──
r = client.get('/api/v1/opportunities', headers={'Authorization': f'Bearer {paid_token}'})
assert r.status_code == 200, f'Paid access denied: {r.status_code} {r.json()}'
print(f'[OK] Paid user accessed /opportunities: {r.status_code}')

# ── Test 3: Free user gets 403 on /opportunities ──
r = client.get('/api/v1/opportunities', headers={'Authorization': f'Bearer {free_token}'})
assert r.status_code == 403, f'Free user not blocked: {r.status_code}'
print(f'[OK] Free user blocked from /opportunities: {r.status_code}')

# ── Test 4: Free user can access /events (free endpoint) ──
r = client.get('/api/v1/events', headers={'Authorization': f'Bearer {free_token}'})
assert r.status_code == 200, f'Free user denied /events: {r.status_code}'
print(f'[OK] Free user accessed /events: {r.status_code}')

# ── Test 5: Rate limit headers present on response ──
r = client.get('/api/v1/events', headers={'Authorization': f'Bearer {paid_token}'})
assert 'X-RateLimit-Limit' in r.headers
assert 'X-RateLimit-Plan' in r.headers
assert r.headers['X-RateLimit-Plan'] == 'paid'
print(f'[OK] Rate limit headers: limit={r.headers["X-RateLimit-Limit"]} plan={r.headers["X-RateLimit-Plan"]}')

# ── Test 6: Unauthenticated request uses free limit ──
r = client.get('/api/v1/events')
assert 'X-RateLimit-Plan' in r.headers
assert r.headers['X-RateLimit-Plan'] == 'free'
print(f'[OK] Unauthenticated request uses free plan: {r.headers["X-RateLimit-Plan"]}')

# Cleanup (best effort)
import pathlib
try:
    db_path = pathlib.Path('data/test_plan.db')
    for f in [db_path, db_path.with_suffix('.db-shm'), db_path.with_suffix('.db-wal')]:
        if f.exists(): f.unlink()
except PermissionError:
    pass

print('\n=== DIA 4 COMPLETO ===')
print('Rate limiting por plano + tier gating funcionando')
