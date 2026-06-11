"""Teste Dia 12 - Password Reset"""
import sys, os
sys.path.insert(0, r'C:\Users\cex\Desktop\OmegaPredictions')
os.chdir(r'C:\Users\cex\Desktop\OmegaPredictions')
os.environ['RUNTIME_MODE'] = 'SIMULATION'
os.environ['MVP_DB_PATH'] = 'data/test_reset.db'
os.environ['STRUCTLOG_LOG_LEVEL'] = 'CRITICAL'
import logging; logging.disable(logging.CRITICAL)

from backend.app.database import Base, engine
from backend.app.auth import User
Base.metadata.create_all(bind=engine)
import sqlite3
c = sqlite3.connect('data/test_reset.db')
cols = [r[1] for r in c.execute('PRAGMA table_info(users)').fetchall()]
for col in ['reset_token', 'reset_token_expires']:
    if col not in cols:
        c.execute(f'ALTER TABLE users ADD COLUMN {col}')
c.commit(); c.close()
print('[OK] Tables ready')

from backend.app.api.auth import router as auth_router
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()
app.include_router(auth_router)
client = TestClient(app)

import uuid
EMAIL = f'reset{uuid.uuid4().hex[:8]}@omega.com'
NEW_PWD = 'nova_senha_123'

# Register
r = client.post('/api/v1/auth/register', json={'email': EMAIL, 'password': '123456'})
assert r.status_code == 201
print(f'[OK] User registered: {EMAIL}')

# ── Test 1: Forgot password (existing email) ──
r = client.post('/api/v1/auth/forgot-password', json={'email': EMAIL})
assert r.status_code == 200
print(f'[OK] Forgot-password: {r.json()["detail"]}')

# ── Test 2: Forgot password (nonexistent email - same message for security) ──
r = client.post('/api/v1/auth/forgot-password', json={'email': 'noone@none.com'})
assert r.status_code == 200
assert r.json()['detail'] == 'Se o email existir, voce recebera um link de recuperacao'
print(f'[OK] Forgot-password security: same message for unknown email')

# ── Test 3: Get reset token from DB ──
from backend.app.database import SessionLocal
db = SessionLocal()
user = db.query(User).filter(User.email == EMAIL).first()
token = user.reset_token
assert token is not None
assert user.reset_token_expires is not None
db.close()
print(f'[OK] Reset token generated: {token[:20]}...')

# ── Test 4: Reset password with valid token ──
r = client.post('/api/v1/auth/reset-password', json={
    'email': EMAIL, 'token': token, 'new_password': NEW_PWD
})
assert r.status_code == 200
assert r.json()['detail'] == 'Senha redefinida com sucesso'
print(f'[OK] Password reset successful')

# ── Test 5: Login with new password ──
r = client.post('/api/v1/auth/login', json={'email': EMAIL, 'password': NEW_PWD})
assert r.status_code == 200
print(f'[OK] Login with new password works')

# ── Test 6: Login with old password fails ──
r = client.post('/api/v1/auth/login', json={'email': EMAIL, 'password': '123456'})
assert r.status_code == 401
print(f'[OK] Old password rejected: {r.status_code}')

# ── Test 7: Reuse token fails (already consumed) ──
r = client.post('/api/v1/auth/reset-password', json={
    'email': EMAIL, 'token': token, 'new_password': 'outra_senha'
})
assert r.status_code == 400
print(f'[OK] Reused token rejected: {r.status_code}')

# ── Test 8: Invalid token fails ──
r = client.post('/api/v1/auth/reset-password', json={
    'email': EMAIL, 'token': 'token_invalido', 'new_password': 'outra_senha'
})
assert r.status_code == 400
print(f'[OK] Invalid token rejected: {r.status_code}')

# Cleanup
import pathlib
try:
    db_path = pathlib.Path('data/test_reset.db')
    for f in [db_path, db_path.with_suffix('.db-shm'), db_path.with_suffix('.db-wal')]:
        if f.exists(): f.unlink()
except PermissionError:
    pass

print('\n=== DIA 12 COMPLETO ===')
print('Password reset: forgot-password, reset-password, token validation, security')
