"""Teste completo de autenticacao - Dia 3"""
import sys, os, json
sys.path.insert(0, r'C:\Users\cex\Desktop\OmegaPredictions')
os.chdir(r'C:\Users\cex\Desktop\OmegaPredictions')
os.environ['RUNTIME_MODE'] = 'SIMULATION'
os.environ['MVP_DB_PATH'] = 'data/test_auth.db'
import logging; logging.disable(logging.CRITICAL)
os.environ['STRUCTLOG_LOG_LEVEL'] = 'CRITICAL'

from backend.app.database import Base, engine
from backend.app.auth import User

Base.metadata.create_all(bind=engine)
print('[OK] User table created')

from backend.app.api.auth import router as auth_router
from fastapi import FastAPI
from fastapi.testclient import TestClient

_test_app = FastAPI()
_test_app.include_router(auth_router)

client = TestClient(_test_app)

import uuid
EMAIL = f'teste{uuid.uuid4().hex[:8]}@omega.com'

# 1. Register
r = client.post('/api/v1/auth/register', json={
    'email': EMAIL,
    'password': '123456'
})
data = r.json()
assert r.status_code == 201, f'Register failed: {data}'
token = data['access_token']
print(f'[OK] Register: {r.status_code} - plan={data["user"]["plan"]}')

# 2. Duplicate register (should fail)
r = client.post('/api/v1/auth/register', json={
    'email': EMAIL,
    'password': '123456'
})
assert r.status_code == 400
print(f'[OK] Duplicate blocked: {r.status_code} - {r.json()["detail"]}')

# 3. Login
r = client.post('/api/v1/auth/login', json={
    'email': EMAIL,
    'password': '123456'
})
assert r.status_code == 200
print(f'[OK] Login: {r.status_code} - token={r.json()["access_token"][:20]}...')

# 4. Get current user
r = client.get('/api/v1/auth/me', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200
assert r.json()['email'] == EMAIL
print(f'[OK] Get Me: {r.status_code} - email={r.json()["email"]} plan={r.json()["plan"]}')

# 5. No auth (should fail)
r = client.get('/api/v1/auth/me')
assert r.status_code == 401
print(f'[OK] No Auth blocked: {r.status_code}')

# 6. Wrong password
r = client.post('/api/v1/auth/login', json={
    'email': EMAIL,
    'password': 'senha_errada'
})
assert r.status_code == 401
print(f'[OK] Wrong password blocked: {r.status_code}')

print('\n=== DIA 3 COMPLETO ===')
print('Autenticacao JWT funcionando: register, login, me, protecao')
