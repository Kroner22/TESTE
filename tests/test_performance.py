"""Teste Dia 8 - Performance Dashboard com paper trades"""
import sys, os
sys.path.insert(0, r'C:\Users\cex\Desktop\OmegaPredictions')
os.chdir(r'C:\Users\cex\Desktop\OmegaPredictions')
os.environ['RUNTIME_MODE'] = 'SIMULATION'
os.environ['STRUCTLOG_LOG_LEVEL'] = 'CRITICAL'
import logging; logging.disable(logging.CRITICAL)

# Ensure trades exist
from backend.app.database import DB_PATH
import sqlite3
c = sqlite3.connect(DB_PATH)
pt = c.execute('SELECT count(*) FROM paper_trades').fetchone()[0]
c.close()
if pt == 0:
    print('[!] Nenhum paper trade encontrado. Executando seed...')
    from scripts.seed_trades import main as seed_trades
    seed_trades()

from backend.app.api.auth import router as auth_router
from backend.app.api.performance import router as perf_router
from backend.app.middleware.logging import RateLimitMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()
app.add_middleware(RateLimitMiddleware)
app.include_router(auth_router)
app.include_router(perf_router)
client = TestClient(app)

import uuid
EMAIL = f'perf{uuid.uuid4().hex[:8]}@omega.com'

client.post('/api/v1/auth/register', json={'email': EMAIL, 'password': '123456'})
from backend.app.auth import hash_password
from backend.app.database import SessionLocal
from backend.app.auth import User
db = SessionLocal()
user = db.query(User).filter(User.email == EMAIL).first()
user.plan = "paid"
db.commit(); db.close()

r = client.post('/api/v1/auth/login', json={'email': EMAIL, 'password': '123456'})
token = r.json()['access_token']
print(f'[OK] Paid user authenticated')

# ── Test 1: Performance summary ──
r = client.get('/api/v1/performance', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200, f'Failed: {r.status_code} {r.json()}'
data = r.json()
assert data['total_trades'] > 0
assert 'win_rate' in data
assert 'total_pnl' in data
assert 'roi_pct' in data
assert 'avg_confidence' in data
assert 'by_grade' in data
print(f'[OK] Performance: {data["total_trades"]} trades, {data["win_rate"]}% win rate, P&L=${data["total_pnl"]}')

# ── Test 2: Field values reasonable ──
assert 0 <= data['win_rate'] <= 100
assert isinstance(data['roi_pct'], float)
assert data['by_grade'] is not None
print(f'[OK] Fields valid: ROI={data["roi_pct"]}% avg_confidence={data["avg_confidence"]}')

# ── Test 3: Trade history ──
r = client.get('/api/v1/performance/trades', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200
data = r.json()
assert data['total'] > 0
assert len(data['trades']) > 0
t = data['trades'][0]
for field in ['position_id', 'event_id', 'market', 'outcome', 'entry_odd', 'stake', 'pnl']:
    assert field in t, f'Missing field: {field}'
print(f'[OK] Trade history: {data["total"]} trades, {len(data["trades"])} returned')

# ── Test 4: Filter by winner ──
r = client.get('/api/v1/performance/trades?outcome=winner', headers={'Authorization': f'Bearer {token}'})
assert all(t['pnl'] > 0 for t in r.json()['trades'] if t['pnl'] is not None)
print(f'[OK] Winner filter: {r.json()["total"]} winning trades')

# ── Test 5: Filter by loser ──
r = client.get('/api/v1/performance/trades?outcome=loser', headers={'Authorization': f'Bearer {token}'})
assert all(t['pnl'] < 0 for t in r.json()['trades'] if t['pnl'] is not None)
print(f'[OK] Loser filter: {r.json()["total"]} losing trades')

# ── Test 6: Pagination ──
r = client.get('/api/v1/performance/trades?limit=5&offset=0', headers={'Authorization': f'Bearer {token}'})
assert len(r.json()['trades']) == 5
assert r.json()['limit'] == 5
print(f'[OK] Pagination: limit=5 returned {len(r.json()["trades"])} trades')

# ── Test 7: Free user blocked ──
EMAIL2 = f'freeperf{uuid.uuid4().hex[:8]}@omega.com'
client.post('/api/v1/auth/register', json={'email': EMAIL2, 'password': '123456'})
r2 = client.post('/api/v1/auth/login', json={'email': EMAIL2, 'password': '123456'})
free_token = r2.json()['access_token']
r = client.get('/api/v1/performance', headers={'Authorization': f'Bearer {free_token}'})
assert r.status_code == 403
print(f'[OK] Free user blocked: {r.status_code}')

print('\n=== DIA 8 COMPLETO ===')
print('Performance dashboard: P&L, win rate, ROI, trade history com filtros')
