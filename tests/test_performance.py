"""Teste Dia 8 - Performance Dashboard com paper trades"""
import sys, os
sys.path.insert(0, r'C:\Users\cex\Desktop\OmegaPredictions')
os.chdir(r'C:\Users\cex\Desktop\OmegaPredictions')
os.environ['RUNTIME_MODE'] = 'SIMULATION'
os.environ['STRUCTLOG_LOG_LEVEL'] = 'CRITICAL'
os.environ['MVP_DB_PATH'] = 'data/test_performance.db'
import logging; logging.disable(logging.CRITICAL)

# Clean DB
for f in ['data/test_performance.db', 'data/test_performance.db-wal', 'data/test_performance.db-shm']:
    try: os.remove(f)
    except FileNotFoundError: pass

from backend.app.auth import User
from backend.app.database import Base, engine
Base.metadata.create_all(bind=engine)

from decimal import Decimal
from datetime import datetime, timedelta, timezone
import uuid
from backend.app.database import SessionLocal, PaperTradeRecord

db = SessionLocal()
now = datetime.now(timezone.utc)

# Seed paper trades
trades = [
    PaperTradeRecord(
        position_id=f"pt_{uuid.uuid4().hex[:12]}", event_id="soccer_a_b",
        market="h2h", outcome="home", bookmaker="Pinnacle",
        entry_odd=Decimal("2.10"), entry_ev=Decimal("0.08"), stake=Decimal("50"),
        entry_timestamp=now - timedelta(hours=48), is_open=False,
        exit_odd=Decimal("2.30"), exit_timestamp=now - timedelta(hours=2),
        pnl=Decimal("4.76"), pnl_pct=Decimal("9.52"),
        confidence=Decimal("0.85"), kelly_fraction=Decimal("0.25"),
    ),
    PaperTradeRecord(
        position_id=f"pt_{uuid.uuid4().hex[:12]}", event_id="basketball_c_d",
        market="h2h", outcome="away", bookmaker="DraftKings",
        entry_odd=Decimal("1.80"), entry_ev=Decimal("0.05"), stake=Decimal("75"),
        entry_timestamp=now - timedelta(hours=72), is_open=False,
        exit_odd=Decimal("1.65"), exit_timestamp=now - timedelta(hours=6),
        pnl=Decimal("-6.25"), pnl_pct=Decimal("-8.33"),
        confidence=Decimal("0.72"), kelly_fraction=Decimal("0.25"),
    ),
    PaperTradeRecord(
        position_id=f"pt_{uuid.uuid4().hex[:12]}", event_id="soccer_e_f",
        market="h2h", outcome="draw", bookmaker="Bet365",
        entry_odd=Decimal("3.40"), entry_ev=Decimal("0.12"), stake=Decimal("30"),
        entry_timestamp=now - timedelta(hours=96), is_open=False,
        exit_odd=Decimal("3.80"), exit_timestamp=now - timedelta(hours=24),
        pnl=Decimal("3.53"), pnl_pct=Decimal("11.76"),
        confidence=Decimal("0.45"), kelly_fraction=Decimal("0.10"),
    ),
    PaperTradeRecord(
        position_id=f"pt_{uuid.uuid4().hex[:12]}", event_id="baseball_g_h",
        market="h2h", outcome="home", bookmaker="FanDuel",
        entry_odd=Decimal("1.95"), entry_ev=Decimal("0.03"), stake=Decimal("100"),
        entry_timestamp=now - timedelta(hours=12), is_open=False,
        exit_odd=Decimal("1.70"), exit_timestamp=now - timedelta(hours=1),
        pnl=Decimal("-12.82"), pnl_pct=Decimal("-12.82"),
        confidence=Decimal("0.60"), kelly_fraction=Decimal("0.25"),
    ),
    PaperTradeRecord(
        position_id=f"pt_{uuid.uuid4().hex[:12]}", event_id="soccer_i_j",
        market="h2h", outcome="home", bookmaker="Pinnacle",
        entry_odd=Decimal("2.50"), entry_ev=Decimal("0.15"), stake=Decimal("40"),
        entry_timestamp=now - timedelta(hours=36), is_open=False,
        exit_odd=Decimal("2.80"), exit_timestamp=now - timedelta(hours=4),
        pnl=Decimal("4.80"), pnl_pct=Decimal("12.00"),
        confidence=Decimal("0.91"), kelly_fraction=Decimal("0.33"),
    ),
]
db.bulk_save_objects(trades)
db.commit(); db.close()

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

EMAIL = f'perf{uuid.uuid4().hex[:8]}@omega.com'
client.post('/api/v1/auth/register', json={'email': EMAIL, 'password': '123456'})
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
