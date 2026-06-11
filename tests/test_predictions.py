"""Teste Dia 6 - Predictions endpoint com dados seedados"""
import sys, os
sys.path.insert(0, r'C:\Users\cex\Desktop\OmegaPredictions')
os.chdir(r'C:\Users\cex\Desktop\OmegaPredictions')
os.environ['RUNTIME_MODE'] = 'SIMULATION'
os.environ['STRUCTLOG_LOG_LEVEL'] = 'CRITICAL'
os.environ['MVP_DB_PATH'] = 'data/test_predictions.db'
import logging; logging.disable(logging.CRITICAL)

# Clean + seed all tables
for f in ['data/test_predictions.db', 'data/test_predictions.db-wal', 'data/test_predictions.db-shm']:
    try: os.remove(f)
    except FileNotFoundError: pass

from backend.app.auth import User
from backend.app.database import Base, engine
Base.metadata.create_all(bind=engine)

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from backend.app.database import SessionLocal, Event, OpportunityRecord

db = SessionLocal()

# Seed events
sports = {
    "soccer": [("Man City","Liverpool"), ("Real Madrid","Barcelona")],
    "basketball": [("Lakers","Celtics"), ("Warriors","Nuggets")],
    "baseball": [("Yankees","RedSox")],
}
now = datetime.now(timezone.utc)
for sport, pairs in sports.items():
    for home, away in pairs:
        db.add(Event(event_id=f"{sport}_{home.lower()}_{away.lower()}", sport=sport,
                     home_team=home, away_team=away,
                     start_time=now + timedelta(hours=2), status="scheduled"))
db.commit()

# Seed opportunities (one per event)
from backend.app.database import Event as EvModel
for ev in db.query(EvModel).all():
    db.add(OpportunityRecord(
        event_id=ev.event_id, market="h2h", outcome="home",
        bookmaker="Pinnacle", odd=Decimal("2.10"),
        implied_prob=Decimal("0.4762"), fair_prob=Decimal("0.52"),
        ev=Decimal("0.092"), edge_score=Decimal("9.2"),
        confidence_score=Decimal("0.85"), kelly_stake=Decimal("0.03"),
        value_grade="STRONG", risk_level="MEDIUM",
        detected_at=now, is_active=True,
    ))
db.commit()
db.close()

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

client.post('/api/v1/auth/register', json={'email': EMAIL, 'password': '123456'})
db = SessionLocal()
user = db.query(User).filter(User.email == EMAIL).first()
user.plan = "paid"
db.commit(); db.close()

r = client.post('/api/v1/auth/login', json={'email': EMAIL, 'password': '123456'})
token = r.json()['access_token']
print(f'[OK] Paid user authenticated')

# ── Test 1: Get predictions ──
r = client.get('/api/v1/predictions', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200, f'Failed: {r.status_code} {r.json()}'
data = r.json()
assert data['total'] > 0
assert len(data['predictions']) > 0
print(f'[OK] Predictions: {data["total"]} total, {len(data["predictions"])} returned')

# ── Test 2: Fields present ──
p = data['predictions'][0]
required = ['event_id', 'sport', 'home_team', 'away_team', 'outcome', 'odd', 'ev_pct', 'confidence', 'value_grade', 'risk_level']
for field in required:
    assert field in p, f'Missing field: {field}'
print(f'[OK] All required fields present')

# ── Test 3: Filter by sport ──
r = client.get('/api/v1/predictions?sport=soccer', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200
sports_set = set(p['sport'] for p in r.json()['predictions'])
assert sports_set == {'soccer'}, f'Expected only soccer, got {sports_set}'
print(f'[OK] Filter by sport=soccer: {r.json()["total"]} predictions')

# ── Test 4: Filter by grade ──
r = client.get('/api/v1/predictions?grade=ELITE', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200
print(f'[OK] Filter by grade=ELITE: {r.json()["total"]} predictions')

# ── Test 5: Pagination ──
r = client.get('/api/v1/predictions?limit=3&offset=0', headers={'Authorization': f'Bearer {token}'})
assert len(r.json()['predictions']) == 3
assert r.json()['limit'] == 3
print(f'[OK] Pagination: limit=3 returned {len(r.json()["predictions"])} predictions')

# ── Test 6: Free user gets 403 ──
EMAIL2 = f'free{uuid.uuid4().hex[:8]}@omega.com'
client.post('/api/v1/auth/register', json={'email': EMAIL2, 'password': '123456'})
r2 = client.post('/api/v1/auth/login', json={'email': EMAIL2, 'password': '123456'})
free_token = r2.json()['access_token']
r = client.get('/api/v1/predictions', headers={'Authorization': f'Bearer {free_token}'})
assert r.status_code == 403
print(f'[OK] Free user blocked: {r.status_code}')

print('\n=== DIA 6 COMPLETO ===')
print('Predictions endpoint servindo dados seedados com filtros e paginacao')
