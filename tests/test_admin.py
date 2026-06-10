"""Teste Dia 9 - Admin Panel"""
import sys, os
sys.path.insert(0, r'C:\Users\cex\Desktop\OmegaPredictions')
os.chdir(r'C:\Users\cex\Desktop\OmegaPredictions')
os.environ['RUNTIME_MODE'] = 'SIMULATION'
os.environ['MVP_DB_PATH'] = 'data/test_admin.db'
os.environ['STRUCTLOG_LOG_LEVEL'] = 'CRITICAL'
import logging; logging.disable(logging.CRITICAL)

from backend.app.database import Base, engine
from backend.app.auth import User
Base.metadata.create_all(bind=engine)
print('[OK] User table created')

from backend.app.api.auth import router as auth_router
from backend.app.api.admin import router as admin_router
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()
app.include_router(auth_router)
app.include_router(admin_router)
client = TestClient(app)

import uuid

# Register a regular user
EMAIL = f'user{uuid.uuid4().hex[:8]}@omega.com'
client.post('/api/v1/auth/register', json={'email': EMAIL, 'password': '123456'})
r = client.post('/api/v1/auth/login', json={'email': EMAIL, 'password': '123456'})
user_token = r.json()['access_token']

# Register an admin user
ADMIN_EMAIL = f'admin{uuid.uuid4().hex[:8]}@omega.com'
client.post('/api/v1/auth/register', json={'email': ADMIN_EMAIL, 'password': 'admin123'})

from backend.app.auth import hash_password
from backend.app.database import SessionLocal
db = SessionLocal()
admin_user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
admin_user.plan = "admin"
db.commit()
db.close()

r = client.post('/api/v1/auth/login', json={'email': ADMIN_EMAIL, 'password': 'admin123'})
admin_token = r.json()['access_token']
print(f'[OK] Users registered (admin + regular)')

# ── Test 1: Regular user blocked from admin ──
r = client.get('/api/v1/admin/stats', headers={'Authorization': f'Bearer {user_token}'})
assert r.status_code == 403
print(f'[OK] Regular user blocked from admin: {r.status_code}')

# ── Test 2: Admin can access stats ──
r = client.get('/api/v1/admin/stats', headers={'Authorization': f'Bearer {admin_token}'})
assert r.status_code == 200
d = r.json()
assert 'users' in d
assert 'data' in d
assert d['users']['total'] >= 2
assert 'events_by_sport' in d
print(f'[OK] Admin stats: {d["users"]["total"]} users, {d["data"]["events"]} events')

# ── Test 3: Admin can list users ──
r = client.get('/api/v1/admin/users', headers={'Authorization': f'Bearer {admin_token}'})
assert r.status_code == 200
d = r.json()
assert d['total'] >= 2
assert len(d['users']) >= 2
emails = [u['email'] for u in d['users']]
assert EMAIL in emails
assert ADMIN_EMAIL in emails
print(f'[OK] Users list: {d["total"]} users found')

# ── Test 4: Admin can upgrade user plan ──
r = client.put(f'/api/v1/admin/users/1/plan',
    headers={'Authorization': f'Bearer {admin_token}'},
    json={'plan': 'paid'})
assert r.status_code == 200
print(f'[OK] User plan upgraded: {r.json()["detail"]}')

# ── Test 5: Invalid plan rejected ──
r = client.put(f'/api/v1/admin/users/1/plan',
    headers={'Authorization': f'Bearer {admin_token}'},
    json={'plan': 'invalid'})
assert r.status_code == 400
print(f'[OK] Invalid plan rejected: {r.status_code}')

# ── Test 6: Non-existent user returns 404 ──
r = client.put('/api/v1/admin/users/99999/plan',
    headers={'Authorization': f'Bearer {admin_token}'},
    json={'plan': 'paid'})
assert r.status_code == 404
print(f'[OK] Non-existent user: {r.status_code}')

# Cleanup
import pathlib
try:
    db_path = pathlib.Path('data/test_admin.db')
    for f in [db_path, db_path.with_suffix('.db-shm'), db_path.with_suffix('.db-wal')]:
        if f.exists(): f.unlink()
except PermissionError:
    pass

print('\n=== DIA 9 COMPLETO ===')
print('Admin panel: stats, users, plan management')
