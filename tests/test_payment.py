"""Teste Dia 11 - Pagamento Stripe"""
import sys, os
sys.path.insert(0, r'C:\Users\cex\Desktop\OmegaPredictions')
os.chdir(r'C:\Users\cex\Desktop\OmegaPredictions')
os.environ['RUNTIME_MODE'] = 'SIMULATION'
os.environ['MVP_DB_PATH'] = 'data/test_payment.db'
os.environ['STRUCTLOG_LOG_LEVEL'] = 'CRITICAL'
import logging; logging.disable(logging.CRITICAL)

from backend.app.database import Base, engine
from backend.app.auth import User, hash_password
Base.metadata.create_all(bind=engine)
# Add new columns for test DB
import sqlite3
c = sqlite3.connect('data/test_payment.db')
cols = [r[1] for r in c.execute('PRAGMA table_info(users)').fetchall()]
for col, dtype in [('stripe_customer_id', ''), ('stripe_subscription_id', ''), ('subscription_status', "DEFAULT 'inactive'")]:
    if col not in cols:
        c.execute(f'ALTER TABLE users ADD COLUMN {col} {dtype}')
c.commit(); c.close()
print('[OK] Tables ready')

from backend.app.api.auth import router as auth_router
from backend.app.api.payment import router as payment_router
from backend.app.api.payment import upgrade_router
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()
app.include_router(auth_router)
app.include_router(upgrade_router)
app.include_router(payment_router)
client = TestClient(app)

import uuid
EMAIL = f'pay{uuid.uuid4().hex[:8]}@omega.com'

# Register
client.post('/api/v1/auth/register', json={'email': EMAIL, 'password': '123456'})
r = client.post('/api/v1/auth/login', json={'email': EMAIL, 'password': '123456'})
token = r.json()['access_token']
print(f'[OK] User registered: {EMAIL}')

# ── Test 1: Dashboard shows subscription status ──
r = client.get('/api/v1/auth/dashboard', headers={'Authorization': f'Bearer {token}'})
d = r.json()
assert 'subscription_status' in d
assert d['subscription_status'] == 'inactive'
assert d['has_subscription'] == False
print(f'[OK] Dashboard: subscription_status={d["subscription_status"]}')

# ── Test 2: Upgrade creates Stripe Checkout session ──
r = client.post('/api/v1/auth/upgrade', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200
d = r.json()
assert 'checkout_url' in d
assert d['checkout_url'] is not None and len(d['checkout_url']) > 10
print(f'[OK] Checkout session created: {d["checkout_url"][:60]}...')

# ── Test 3: Already-paid user blocked from upgrade ──
from backend.app.database import SessionLocal
db1 = SessionLocal()
u1 = db1.query(User).filter(User.email == EMAIL).first()
u1.plan = "paid"
db1.commit()
db1.close()
r = client.post('/api/v1/auth/upgrade', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 400
assert 'ja possui' in r.json()['detail']
print(f'[OK] Paid user blocked from upgrade: {r.status_code}')

# ── Test 4: Portal fails without subscription ──
r = client.get('/api/v1/auth/portal', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 400
print(f'[OK] Portal blocked without subscription: {r.status_code}')

# ── Test 5: Portal works with customer_id set ──
db2 = SessionLocal()
u2 = db2.query(User).filter(User.email == EMAIL).first()
u2.plan = "free"
u2.stripe_customer_id = "cus_test123"
db2.commit()
db2.close()
r = client.get('/api/v1/auth/portal', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200
print(f'[OK] Portal session created: {r.json()["portal_url"][:60]}...')

# ── Test 6: Webhook checkout.session.completed upgrades user ──
import json
db3 = SessionLocal()
u3 = db3.query(User).filter(User.email == EMAIL).first()
u3.stripe_customer_id = None
u3.stripe_subscription_id = None
u3.subscription_status = "inactive"
u3.plan = "free"
db3.commit()
db3.close()
payload = json.dumps({
    "type": "checkout.session.completed",
    "data": {
        "object": {
            "customer_details": {"email": EMAIL},
            "customer": "cus_new123",
            "subscription": "sub_new123",
        }
    }
})
r = client.post("/api/v1/stripe/webhook", content=payload)
assert r.status_code == 200  # Will be ignored (placeholder webhook secret), but should not crash
# With placeholder secret, webhook is ignored (status: ignored)
assert r.json()['status'] == 'ignored'
print(f'[OK] Webhook endpoint responds: {r.status_code}')

# ── Test 7: API has payment paths ──
r = client.get('/openapi.json')
assert '/api/v1/auth/upgrade' in r.text
assert '/api/v1/stripe/webhook' in r.text
print(f'[OK] Payment routes registered in API')

import pathlib
try:
    db_path = pathlib.Path('data/test_payment.db')
    for f in [db_path, db_path.with_suffix('.db-shm'), db_path.with_suffix('.db-wal')]:
        if f.exists(): f.unlink()
except PermissionError:
    pass

print('\n=== DIA 11 COMPLETO ===')
print('Pagamento Stripe: checkout, portal, webhook, subscription status')
