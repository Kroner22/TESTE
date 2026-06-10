"""Teste Dia 10 - Frontend Web Dashboard"""
import sys, os
sys.path.insert(0, r'C:\Users\cex\Desktop\OmegaPredictions')
os.chdir(r'C:\Users\cex\Desktop\OmegaPredictions')
os.environ['RUNTIME_MODE'] = 'SIMULATION'
os.environ['STRUCTLOG_LOG_LEVEL'] = 'CRITICAL'
import logging; logging.disable(logging.CRITICAL)

from backend.app.main import app
from fastapi.testclient import TestClient
client = TestClient(app)

# ── Test 1: Frontend loads ──
r = client.get('/app')
assert r.status_code == 200
assert 'Omega' in r.text
assert 'tailwindcss' in r.text
assert 'login' in r.text.lower()
print(f'[OK] Frontend loaded: {len(r.text)} bytes')

# ── Test 2: Sub-path also serves frontend ──
r = client.get('/app/dashboard')
assert r.status_code == 200
assert 'Omega' in r.text
print(f'[OK] Sub-path /app/dashboard works')

# ── Test 3: Deep path works ──
r = client.get('/app/predictions/soccer')
assert r.status_code == 200
assert 'Omega' in r.text
print(f'[OK] Deep path /app/predictions/soccer works')

# ── Test 4: Contains auth form elements ──
assert 'auth-email' in r.text
assert 'auth-pass' in r.text
assert 'auth-form' in r.text
print(f'[OK] Auth form elements present')

# ── Test 5: Contains all nav sections ──
assert 'Dashboard' in r.text
assert 'Predictions' in r.text
assert 'Performance' in r.text
assert 'Config' in r.text
print(f'[OK] Navigation sections present')

# ── Test 6: API routes still work independently ──
r = client.get('/api/v1/auth/me')
assert r.status_code == 401
print(f'[OK] API route still working: /me -> {r.status_code}')

# ── Test 7: Root endpoint works ──
r = client.get('/')
assert r.status_code == 200
print(f'[OK] Root endpoint works')

print('\n=== DIA 10 COMPLETO ===')
print('Frontend Web Dashboard: SPA com TailwindCSS')
