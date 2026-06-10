<#
.SYNOPSIS
    Script de setup para Omega Predictions — instala dependências e configura ambiente
.DESCRIPTION
    Instala PostgreSQL, Docker, dependências Python e prepara o ambiente de produção
#>

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$BACKEND = Join-Path $ROOT "backend"
$FRONTEND = Join-Path $ROOT "frontend"

Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   Omega Predictions - Setup Completo    ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# 1. Verificar Python
Write-Host "[1/6] Verificando Python..." -ForegroundColor Yellow
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "  Python nao encontrado! Instale Python 3.11+ em https://python.org" -ForegroundColor Red
    exit 1
}
$pyVersion = python --version
Write-Host "  $pyVersion" -ForegroundColor Green

# 2. Instalar dependências Python
Write-Host "[2/6] Instalando dependencias Python..." -ForegroundColor Yellow
pip install -r "$BACKEND\requirements.txt" -q
if ($?) {
    Write-Host "  Dependencias instaladas" -ForegroundColor Green
} else {
    Write-Host "  Erro ao instalar dependencias" -ForegroundColor Red
}

# 3. Verificar Git
Write-Host "[3/6] Verificando Git..." -ForegroundColor Yellow
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
    Write-Host "  Git $(git --version)" -ForegroundColor Green
} else {
    Write-Host "  Git nao encontrado. Instale em https://git-scm.com" -ForegroundColor Red
}

# 4. Configurar GitHub Remote
Write-Host "[4/6] Configurando GitHub..." -ForegroundColor Yellow
$remote = git remote get-url origin 2>$null
if (-not $remote) {
    Write-Host "  Remote nao configurado. Apos criar repositorio no GitHub, execute:" -ForegroundColor Yellow
    Write-Host "  git remote add origin https://github.com/SEU_USUARIO/omega-predictions.git" -ForegroundColor White
    Write-Host "  git push -u origin main" -ForegroundColor White
} else {
    Write-Host "  Remote: $remote" -ForegroundColor Green
}

# 5. Verificar Node.js (para frontend)
Write-Host "[5/6] Verificando Node.js..." -ForegroundColor Yellow
$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    Write-Host "  Node $(node --version)" -ForegroundColor Green
    if (Test-Path "$FRONTEND\package.json") {
        Write-Host "  Instalando dependencias do frontend..." -ForegroundColor Yellow
        Set-Location $FRONTEND
        npm install --silent 2>$null
        Set-Location $ROOT
        Write-Host "  Frontend pronto" -ForegroundColor Green
    }
} else {
    Write-Host "  Node nao encontrado (opcional para backend-only)" -ForegroundColor Yellow
}

# 6. Resumo
Write-Host "[6/6] Resumo do Ambiente:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Para iniciar o servidor:" -ForegroundColor White
Write-Host "    python run.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Para acessar a API:" -ForegroundColor White
Write-Host "    http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Para testar:" -ForegroundColor White
Write-Host "    python -m pytest tests/" -ForegroundColor Cyan
Write-Host ""
Write-Host "Omega Predictions - Setup concluido!" -ForegroundColor Green
