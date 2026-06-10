@echo off
title Omega Predictions
cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════╗
echo  ║     OMEGA PREDICTIONS PLATFORM      ║
echo  ║    Selecione uma opcao:             ║
echo  ╚══════════════════════════════════════╝
echo.
echo  [1] Iniciar API (http://localhost:8000)
echo  [2] Iniciar Frontend (http://localhost:3000)
echo  [3] Rodar Testes
echo  [4] Abrir GitHub
echo  [5] Sobre
echo.
choice /c 12345 /n /m "Digite [1-5]: "
if errorlevel 5 goto about
if errorlevel 4 goto github
if errorlevel 3 goto tests
if errorlevel 2 goto frontend
if errorlevel 1 goto api

:api
echo.
echo  Iniciando API Omega Predictions...
python run.py
goto end

:frontend
echo.
echo  Iniciando Frontend...
cd frontend
npm run dev
goto end

:tests
echo.
echo  Rodando testes...
python -m pytest tests/ -v
pause
goto end

:github
echo.
echo  Para conectar ao GitHub, crie um repositorio em:
echo  https://github.com/new
echo.
echo  Depois execute:
echo  git remote add origin https://github.com/SEU_USUARIO/omega-predictions.git
echo  git push -u origin main
echo.
pause
goto end

:about
echo.
echo  Omega Predictions v0.1.0
echo  Plataforma de Previsoes Esportivas com IA Multi-Agente
echo.
echo  Baseado em:
echo    - sports_quant (motor de value bets)
echo    - AI_OPERATING_SYSTEM (orquestracao multi-agente)
echo    - sports_ingestion (pipeline de dados)
echo.
echo  532 eventos · 2830 odds · 550 paper trades
echo.
pause

:end
