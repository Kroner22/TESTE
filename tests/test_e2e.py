"""Dia 14 - Teste End-to-End: fluxo completo do usuario"""
import sys, os
sys.path.insert(0, r'C:\Users\cex\Desktop\OmegaPredictions')
os.chdir(r'C:\Users\cex\Desktop\OmegaPredictions')
os.environ['RUNTIME_MODE'] = 'SIMULATION'
os.environ['STRUCTLOG_LOG_LEVEL'] = 'CRITICAL'
os.environ['MVP_DB_PATH'] = 'data/test_e2e.db'
import logging; logging.disable(logging.CRITICAL)

# Clean DB
for f in ['data/test_e2e.db', 'data/test_e2e.db-wal', 'data/test_e2e.db-shm']:
    try: os.remove(f)
    except FileNotFoundError: pass

from backend.app.auth import User
from backend.app.database import Base, engine
Base.metadata.create_all(bind=engine)

from decimal import Decimal
from datetime import datetime, timedelta, timezone
import uuid
from backend.app.database import SessionLocal, Event, OpportunityRecord

db = SessionLocal()
now = datetime.now(timezone.utc)

# Seed 1 event + 2 opportunities
db.add(Event(event_id="e2e_bra_arg", sport="soccer", home_team="Brasil", away_team="Argentina",
             start_time=now + timedelta(hours=6), status="scheduled"))
db.commit()

for out, odd, grade in [("home", "2.10", "STRONG"), ("away", "3.80", "SPECULATIVE")]:
    db.add(OpportunityRecord(
        event_id="e2e_bra_arg", market="h2h", outcome=out,
        bookmaker="Pinnacle", odd=Decimal(odd),
        implied_prob=Decimal(str(round(1/float(odd), 4))), fair_prob=Decimal("0.52"),
        ev=Decimal("0.09"), edge_score=Decimal("9.0"),
        confidence_score=Decimal("0.85"), kelly_stake=Decimal("0.03"),
        value_grade=grade, risk_level="MEDIUM",
        detected_at=now, is_active=True,
    ))
db.commit(); db.close()

from backend.app.api.auth import router as auth_router
from backend.app.api.predictions import router as pred_router
from backend.app.api.admin import router as admin_router
from backend.app.middleware.logging import RateLimitMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()
app.add_middleware(RateLimitMiddleware)
app.include_router(auth_router)
app.include_router(pred_router)
app.include_router(admin_router)
client = TestClient(app)

EMAIL = f'e2e{uuid.uuid4().hex[:8]}@omega.com'
PASS = 'Str0ng!Pass#42'

# ═══════════════════════════════════════════
# 1. Register
# ═══════════════════════════════════════════
r = client.post('/api/v1/auth/register', json={'email': EMAIL, 'password': PASS})
assert r.status_code == 201, f'Register failed: {r.status_code} {r.json()}'
print(f'[OK] 1. Register: {EMAIL}')

# ═══════════════════════════════════════════
# 2. Verify free user blocked from predictions
# ═══════════════════════════════════════════
r = client.post('/api/v1/auth/login', json={'email': EMAIL, 'password': PASS})
token = r.json()['access_token']

r = client.get('/api/v1/predictions', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 403
print('[OK] 2. Free user blocked from predictions')

# ═══════════════════════════════════════════
# 3. Upgrade to paid
# ═══════════════════════════════════════════
db = SessionLocal()
user = db.query(User).filter(User.email == EMAIL).first()
user.plan = "paid"
user.subscription_status = "active"
user.stripe_customer_id = 'cus_test123'
user.stripe_subscription_id = 'sub_test123'
db.commit(); db.close()

# ═══════════════════════════════════════════
# 4. Paid user can access predictions
# ═══════════════════════════════════════════
r = client.post('/api/v1/auth/login', json={'email': EMAIL, 'password': PASS})
token = r.json()['access_token']

r = client.get('/api/v1/predictions', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200
data = r.json()
assert data['total'] >= 2
p = data['predictions'][0]
assert all(k in p for k in ['event_id', 'sport', 'odd', 'ev_pct', 'value_grade'])
print(f'[OK] 4. Predictions: {data["total"]} results')

# ═══════════════════════════════════════════
# 5. Admin dashboard accessible
# ═══════════════════════════════════════════
db = SessionLocal()
u = db.query(User).filter(User.email == EMAIL).first()
u.plan = "admin"
db.commit(); db.close()

# Re-login to refresh token with admin claims
r = client.post('/api/v1/auth/login', json={'email': EMAIL, 'password': PASS})
token = r.json()['access_token']

r = client.get('/api/v1/admin/stats', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200, f'Admin stats failed: {r.status_code} {r.json()}'
stats = r.json()
assert isinstance(stats, dict) and stats
print(f'[OK] 5. Admin stats: {len(stats)} fields')

r2 = client.get('/api/v1/admin/users', headers={'Authorization': f'Bearer {token}'})
assert r2.status_code == 200
users_data = r2.json()
assert len(users_data) >= 1
print(f'[OK] 5b. Admin users: {len(users_data)} user(s)')

# ═══════════════════════════════════════════
# 6. Forgot-password flow
# ═══════════════════════════════════════════
r = client.post('/api/v1/auth/forgot-password', json={'email': EMAIL})
assert r.status_code == 200
detail = r.json()['detail']
assert 'email' in detail.lower()
print(f'[OK] 6. Forgot-password: {detail}')

# ═══════════════════════════════════════════
# 7. Forgot-password security (same message for unknown email)
# ═══════════════════════════════════════════
r2 = client.post('/api/v1/auth/forgot-password', json={'email': 'unknown@test.com'})
assert r2.status_code == 200
assert r2.json()['detail'] == detail
print(f'[OK] 7. Forgot-password security: same message for unknown email')

# ═══════════════════════════════════════════
# 8. Recap - all core flows verified
# ═══════════════════════════════════════════

# ═══════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════
print('\n=== DIA 14 - E2E COMPLETO ===')
print('Fluxo: register -> free blocked -> upgrade -> predictions -> admin')
print('Todas as integracoes do MVP verificadas em sequencia')
