"""Teste Dia 6 - Predictions endpoint com dados seedados"""
import sys, os
sys.path.insert(0, r'C:\Users\cex\Desktop\OmegaPredictions')
os.chdir(r'C:\Users\cex\Desktop\OmegaPredictions')
os.environ['RUNTIME_MODE'] = 'SIMULATION'
os.environ['STRUCTLOG_LOG_LEVEL'] = 'CRITICAL'
import logging; logging.disable(logging.CRITICAL)

# Check that seeded data exists
from backend.app.database import DB_PATH
import sqlite3
c = sqlite3.connect(DB_PATH)
opps = c.execute('SELECT count(*) FROM opportunities').fetchone()[0]
c.close()
if opps == 0:
    print('[!] Nenhuma oportunidade encontrada. Execute scripts/seed_predictions.py primeiro.')
    print('    Executando seed agora...')
    from scripts.seed_predictions import main as seed_main
    seed_main()

from backend.app.api.auth import router as auth_router
from backend.app.api.predictions import router as pred_router
from backend.app.middleware.logging import RateLimitMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()
app.add_middleware(RateLimitMiddleware)
app.include_router(auth_router)
app.include_router(pred_router)
client = TestClient(app)

import uuid
EMAIL = f'test{uuid.uuid4().hex[:8]}@omega.com'

# Register paid user
client.post('/api/v1/auth/register', json={'email': EMAIL, 'password': '123456'})
from backend.app.auth import hash_password
from backend.app.database import SessionLocal
db = SessionLocal()
from backend.app.auth import User
user = db.query(User).filter(User.email == EMAIL).first()
user.plan = "paid"
db.commit()
db.close()

r = client.post('/api/v1/auth/login', json={'email': EMAIL, 'password': '123456'})
token = r.json()['access_token']
print(f'[OK] Paid user authenticated')

# ── Test 1: Get predictions ──
r = client.get('/api/v1/predictions', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200, f'Predictions failed: {r.status_code} {r.json()}'
data = r.json()
assert data['total'] > 0, 'No predictions returned'
assert len(data['predictions']) > 0
print(f'[OK] Predictions: {data["total"]} total, {len(data["predictions"])} returned')

# ── Test 2: Fields present ──
p = data['predictions'][0]
required = ['event_id', 'sport', 'home_team', 'away_team', 'outcome', 'odd', 'ev_pct', 'confidence', 'value_grade', 'risk_level']
for field in required:
    assert field in p, f'Missing field: {field}'
print(f'[OK] All required fields present: {list(p.keys())}')

# ── Test 3: Filter by sport ──
r = client.get('/api/v1/predictions?sport=soccer', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200
sports = set(p['sport'] for p in r.json()['predictions'])
assert sports == {'soccer'}, f'Expected only soccer, got {sports}'
print(f'[OK] Filter by sport=soccer: {r.json()["total"]} predictions')

# ── Test 4: Filter by grade ──
r = client.get('/api/v1/predictions?grade=ELITE', headers={'Authorization': f'Bearer {token}'})
# May be 0 if no ELITE predictions, but should still work
assert r.status_code == 200
print(f'[OK] Filter by grade=ELITE: {r.json()["total"]} predictions')

# ── Test 5: Pagination ──
r = client.get('/api/v1/predictions?limit=3&offset=0', headers={'Authorization': f'Bearer {token}'})
assert len(r.json()['predictions']) == 3
assert r.json()['limit'] == 3
print(f'[OK] Pagination: limit=3 returned {len(r.json()["predictions"])} predictions')

# ── Test 6: Free user gets 403 ──
# Register a free user
EMAIL2 = f'free{uuid.uuid4().hex[:8]}@omega.com'
client.post('/api/v1/auth/register', json={'email': EMAIL2, 'password': '123456'})
r2 = client.post('/api/v1/auth/login', json={'email': EMAIL2, 'password': '123456'})
free_token = r2.json()['access_token']
r = client.get('/api/v1/predictions', headers={'Authorization': f'Bearer {free_token}'})
assert r.status_code == 403, f'Free user should be blocked: {r.status_code}'
print(f'[OK] Free user blocked from predictions: {r.status_code}')

print('\n=== DIA 6 COMPLETO ===')
print('Predictions endpoint servindo dados seedados com filtros e paginacao')
