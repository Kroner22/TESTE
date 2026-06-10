"""Teste Dia 5 - Dashboard, API Key, Usage Tracking"""
import sys, os
sys.path.insert(0, r'C:\Users\cex\Desktop\OmegaPredictions')
os.chdir(r'C:\Users\cex\Desktop\OmegaPredictions')
os.environ['RUNTIME_MODE'] = 'SIMULATION'
os.environ['MVP_DB_PATH'] = 'data/test_day5.db'
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
EMAIL = f'user{uuid.uuid4().hex[:8]}@omega.com'

# Register
r = client.post('/api/v1/auth/register', json={'email': EMAIL, 'password': '123456'})
assert r.status_code == 201
token = r.json()['access_token']
print(f'[OK] Registered: {EMAIL}')

# ── Test 1: Dashboard shows plan and usage stats ──
r = client.get('/api/v1/auth/dashboard', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200
d = r.json()
assert d['plan'] == 'free'
assert d['requests_count'] == 0
assert d['requests_limit'] == 1000
assert d['has_api_key'] == False
print(f'[OK] Dashboard: plan={d["plan"]} requests={d["requests_count"]}/{d["requests_limit"]}')

# ── Test 2: Generate API key ──
r = client.post('/api/v1/auth/api-key', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200
api_key = r.json()['api_key']
assert api_key.startswith('om_')
print(f'[OK] API key generated: {api_key[:16]}...')

# ── Test 3: Dashboard now shows API key ──
r = client.get('/api/v1/auth/dashboard', headers={'Authorization': f'Bearer {token}'})
assert r.json()['has_api_key'] == True
assert r.json()['api_key'] == api_key
print('[OK] Dashboard reflects API key')

# ── Test 4: Authenticate via API key instead of JWT ──
r = client.get('/api/v1/auth/me', headers={'X-API-Key': api_key})
assert r.status_code == 200
assert r.json()['email'] == EMAIL
print(f'[OK] API key auth works: {r.json()["email"]}')

# ── Test 5: Access paid endpoint with API key ──
# Need to upgrade user to paid first
from backend.app.auth import hash_password
from backend.app.database import SessionLocal
db = SessionLocal()
user = db.query(User).filter(User.email == EMAIL).first()
user.plan = "paid"
db.commit()
db.close()
r = client.get('/api/v1/opportunities', headers={'X-API-Key': api_key})
assert r.status_code == 200, f'Paid via API key failed: {r.status_code}'
print(f'[OK] Paid endpoint via API key: {r.status_code}')

# ── Test 6: Revoke API key ──
r = client.delete('/api/v1/auth/api-key', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200
assert r.json()['detail'] == 'Chave de API revogada com sucesso'
r2 = client.get('/api/v1/auth/me', headers={'X-API-Key': api_key})
assert r2.status_code == 401
print(f'[OK] API key revoked, old key rejected: {r2.status_code}')

# ── Test 7: Usage counter incremented ──
r = client.get('/api/v1/auth/dashboard', headers={'Authorization': f'Bearer {token}'})
assert r.json()['requests_count'] >= 1
print(f'[OK] Usage tracked: requests_count={r.json()["requests_count"]}')

# Cleanup
import pathlib
try:
    db_path = pathlib.Path('data/test_day5.db')
    for f in [db_path, db_path.with_suffix('.db-shm'), db_path.with_suffix('.db-wal')]:
        if f.exists(): f.unlink()
except PermissionError:
    pass

print('\n=== DIA 5 COMPLETO ===')
print('Dashboard, API Key management, usage tracking funcionando')
