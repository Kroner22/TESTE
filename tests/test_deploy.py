"""Teste Dia 13 - Deploy e Configuracao de Producao"""
import sys, os
sys.path.insert(0, r'C:\Users\cex\Desktop\OmegaPredictions')
os.chdir(r'C:\Users\cex\Desktop\OmegaPredictions')

import pathlib

# ── Test 1: Dockerfile exists ──
assert pathlib.Path('Dockerfile').exists()
content = open('Dockerfile').read()
assert 'python:3.13' in content
assert 'uvicorn' in content
assert 'EXPOSE 8000' in content
print(f'[OK] Dockerfile: {len(content)} bytes')

# ── Test 2: docker-compose.yml exists ──
assert pathlib.Path('docker-compose.yml').exists()
content = open('docker-compose.yml').read()
assert 'redis' in content
assert 'api' in content
print(f'[OK] docker-compose.yml: api + redis services')

# ── Test 3: requirements.txt exists ──
assert pathlib.Path('requirements.txt').exists()
pkgs = open('requirements.txt').read().strip().split('\n')
assert len(pkgs) >= 8
print(f'[OK] requirements.txt: {len(pkgs)} packages')

# ── Test 4: .env.production exists ──
assert pathlib.Path('.env.production').exists()
content = open('.env.production').read()
assert 'ENVIRONMENT=production' in content
assert 'STRIPE_SECRET_KEY' in content
assert 'TELEGRAM_BOT_TOKEN' in content
print(f'[OK] .env.production: production environment template')

# ── Test 5: .dockerignore exists ──
assert pathlib.Path('.dockerignore').exists()
print(f'[OK] .dockerignore')

# ── Test 6: Iniciar.bat startup script exists ──
assert pathlib.Path('Iniciar.bat').exists()
print(f'[OK] Iniciar.bat startup script')

# ── Test 7: Production settings validation ──
content = open('.env.production').read()
assert 'DEBUG=false' in content
assert 'RATE_LIMIT_ENABLED=true' in content
assert 'LOG_FORMAT=json' in content
print(f'[OK] Production settings validated (debug off, rate limit on, json logs)')

# ── Test 8: Server still works ──
os.environ['RUNTIME_MODE'] = 'SIMULATION'
os.environ['STRUCTLOG_LOG_LEVEL'] = 'CRITICAL'
import logging; logging.disable(logging.CRITICAL)
from backend.app.main import app
from fastapi.testclient import TestClient
client = TestClient(app)
r = client.get('/health/live')
assert r.status_code == 200
print(f'[OK] Health check: {r.status_code}')

print('\n=== DIA 13 COMPLETO ===')
print('Deploy config: Docker, compose, production env, startup')
