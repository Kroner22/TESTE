"""Teste Dia 7 - Notificacoes Telegram e preferencias"""
import sys, os
sys.path.insert(0, r'C:\Users\cex\Desktop\OmegaPredictions')
os.chdir(r'C:\Users\cex\Desktop\OmegaPredictions')
os.environ['RUNTIME_MODE'] = 'SIMULATION'
os.environ['MVP_DB_PATH'] = 'data/test_notif.db'
os.environ['STRUCTLOG_LOG_LEVEL'] = 'CRITICAL'
import logging; logging.disable(logging.CRITICAL)

from backend.app.database import Base, engine
from backend.app.auth import User
Base.metadata.create_all(bind=engine)
print('[OK] User table created')

from backend.app.api.auth import router as auth_router
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()
app.include_router(auth_router)
client = TestClient(app)

import uuid
EMAIL = f'notif{uuid.uuid4().hex[:8]}@omega.com'

# Register
r = client.post('/api/v1/auth/register', json={'email': EMAIL, 'password': '123456'})
token = r.json()['access_token']
print(f'[OK] Registered: {EMAIL}')

# ── Test 1: Get notification prefs (defaults) ──
r = client.get('/api/v1/auth/notifications', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200
d = r.json()
assert d['notify_telegram'] == False
assert d['notify_whatsapp'] == False
assert d['notify_min_grade'] == 'SOLID'
assert d['telegram_chat_id'] == None
print(f'[OK] Default prefs: telegram={d["notify_telegram"]} grade={d["notify_min_grade"]}')

# ── Test 2: Update notification prefs ──
r = client.put('/api/v1/auth/notifications', headers={'Authorization': f'Bearer {token}'},
    json={'notify_telegram': True, 'notify_whatsapp': False, 'notify_min_grade': 'STRONG'})
assert r.status_code == 200
r = client.get('/api/v1/auth/notifications', headers={'Authorization': f'Bearer {token}'})
assert r.json()['notify_telegram'] == True
assert r.json()['notify_min_grade'] == 'STRONG'
print(f'[OK] Prefs updated: telegram={r.json()["notify_telegram"]} grade={r.json()["notify_min_grade"]}')

# ── Test 3: Link Telegram ──
r = client.post('/api/v1/auth/telegram/link', headers={'Authorization': f'Bearer {token}'},
    json={'chat_id': '123456789'})
assert r.status_code == 200
assert r.json()['chat_id'] == '123456789'
r = client.get('/api/v1/auth/notifications', headers={'Authorization': f'Bearer {token}'})
assert r.json()['telegram_chat_id'] == '123456789'
assert r.json()['notify_telegram'] == True  # link auto-enables
print(f'[OK] Telegram linked: {r.json()["telegram_chat_id"]}')

# ── Test 4: Test notification (should fail without bot token) ──
r = client.post('/api/v1/auth/notifications/test', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200
print(f'[OK] Test notification dispatch: {r.json()["detail"]}')

# ── Test 5: Unlink Telegram ──
r = client.delete('/api/v1/auth/telegram/link', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 200
r = client.get('/api/v1/auth/notifications', headers={'Authorization': f'Bearer {token}'})
assert r.json()['telegram_chat_id'] == None
assert r.json()['notify_telegram'] == False
print(f'[OK] Telegram unlinked, notify disabled')

# ── Test 6: Test notification without linked Telegram ──
r = client.post('/api/v1/auth/notifications/test', headers={'Authorization': f'Bearer {token}'})
assert r.status_code == 400
print(f'[OK] Test blocked without Telegram: {r.status_code}')

# ── Test 7: Dispatch top predictions (formatting test) ──
from backend.notifications.telegram import format_prediction_message
pred = {
    "event_id": "test123", "outcome": "home", "odd": 2.5,
    "ev_pct": 12.5, "edge_score": 8.2, "confidence": 0.85,
    "value_grade": "STRONG", "risk_level": "MEDIUM",
    "sport": "soccer", "home_team": "Flamengo", "away_team": "Palmeiras",
}
msg = format_prediction_message(pred)
assert "Flamengo" in msg
assert "STRONG" in msg
assert "12.5%" in msg
print(f'[OK] Message formatted correctly:\n{msg}')

# Cleanup
import pathlib
try:
    db_path = pathlib.Path('data/test_notif.db')
    for f in [db_path, db_path.with_suffix('.db-shm'), db_path.with_suffix('.db-wal')]:
        if f.exists(): f.unlink()
except PermissionError:
    pass

print('\n=== DIA 7 COMPLETO ===')
print('Notificacoes Telegram: link, prefs, dispatch, formatacao')
