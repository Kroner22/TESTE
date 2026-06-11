@echo off
REM Omega Predictions - Startup Script
echo.
echo   _____                    _____       _ _ _                
echo  ^|  _  ^|___ ___ ___ ___   ^|     ^|_ _ _^| ^|_^| ^|_ ___ ___ ___ 
echo  ^|   __^| .'^| . ^| -_^|  _^|  ^|  ^|  ^| ^| ^| ^| ^| ^|  _^| .'^| . ^| -_^|
echo  ^|__^|  ^|__,^|_  ^|___^|_^|    ^|_____^|_____^|_^|_^|_^|___^|__,^|_  ^|___^|
echo            ^|_^|                                    ^|_^|        
echo.
echo ========================================
echo  Omega Predictions - Inicializacao
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERRO] Python nao encontrado. Instale Python 3.13+
    pause
    exit /b 1
)
echo [OK] Python encontrado

REM Check if .env exists
if not exist .env (
    if exist .env.production (
        copy .env.production .env
        echo [OK] .env copiado de .env.production
    ) else (
        echo [AVISO] .env nao encontrado. Usando variaveis padrao.
    )
)

REM Install dependencies
if exist requirements.txt (
    echo [INFO] Instalando dependencias...
    pip install -r requirements.txt -q
    if %ERRORLEVEL% neq 0 (
        echo [ERRO] Falha ao instalar dependencias
        pause
        exit /b 1
    )
    echo [OK] Dependencias instaladas
)

REM Seed predictions if needed
python -c "import os; os.environ['RUNTIME_MODE']='SIMULATION'; from backend.app.database import DB_PATH; import sqlite3; c=sqlite3.connect(DB_PATH); n=c.execute('SELECT count(*) FROM opportunities').fetchone()[0]; c.close(); exit(0 if n>0 else 1)" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [INFO] Seed de predictions...
    python scripts/seed_predictions.py
    python scripts/seed_trades.py
    echo [OK] Predictions seedadas
) else (
    echo [OK] Predictions ja existem no banco
)

echo.
echo ========================================
echo  Iniciando servidor em http://localhost:8000
echo  Frontend: http://localhost:8000/app
echo  Docs:     http://localhost:8000/docs
echo ========================================
echo.

uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
