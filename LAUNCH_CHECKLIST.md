# Omega Predictions — Launch Readiness Checklist

## Core MVP (14 dias)

### Funcionalidades
- [x] Autenticacao JWT (register, login, me, protecao)
- [x] CRUD Predictions com filtros e paginacao
- [x] Sistema de planos (free/paid) com gating
- [x] Stripe Checkout + Webhook + Portal
- [x] Telegram Bot (notificacoes + comandos)
- [x] Background Scanner (arbitragem + value betting)
- [x] Admin Panel (stats, usuarios, planos)
- [x] Rate Limiting (slowapi + rolling window por plano)
- [x] Password Reset (forgot/reset/token)
- [x] Frontend Web Dashboard SPA

### Motor de valor (domains/value)
- [x] Probability engine (implied, overround: basic/power/shin)
- [x] Expected Value (EV, confidence intervals, grade)
- [x] Kelly Criterion (full, fractional, bankroll clamp)
- [x] Confidence scoring (sample size, model, history, stability)
- [x] Risk scoring (edge volatility, time pressure, regime, depth)
- [x] ValueDetector (end-to-end orchestration)

### Infraestrutura
- [x] Dockerfile + docker-compose (api + redis)
- [x] .env.production template
- [x] .dockerignore
- [x] Iniciar.bat startup script
- [x] Health checks (/health/live, /health/ready)

### Qualidade
- [x] 12 suites de teste de API (Dias 1-13)
- [x] 1 suite de teste E2E (Dia 14)
- [x] 104 testes unitarios do motor de valor
- [x] Testes de seguranca (token reuse, same-msg-for-unknown-email)

## Pre-lancamento

### Seguranca
- [ ] Trocar SECRET_KEY no .env.production (gerar com `openssl rand -hex 32`)
- [ ] Desabilitar DEBUG no .env.production
- [ ] Configurar CORS_ORIGINS para o dominio real
- [ ] Rate limiting habilitado (RATE_LIMIT_ENABLED=true)
- [ ] Logs em JSON (LOG_FORMAT=json)

### Stripe
- [ ] Adicionar chaves reais STRIPE_SECRET_KEY + STRIPE_WEBHOOK_SECRET
- [ ] Configurar webhook no dashboard do Stripe
- [ ] Testar ciclo completo de pagamento em modo test
- [ ] Criar Price ID no Stripe e configurar STRIPE_PRICE_ID

### Telegram
- [ ] Criar bot no @BotFather e configurar TELEGRAM_BOT_TOKEN
- [ ] Testar comando /start e notificacoes

### Deploy
- [ ] Configurar dominio SSL (certbot / Cloudflare)
- [ ] CI/CD: GitHub Actions para build + push Docker
- [ ] Health check monitorado (UptimeRobot / BetterStack)
- [ ] Backup automatico do banco SQLite
- [ ] Logs centralizados (opcional: Grafana Loki)

### Banco de dados
- [ ] Plano de migracao SQLite -> PostgreSQL se necessario
- [ ] Configurar DATABASE_URL no .env.production

### Documentacao
- [x] README com instrucoes de setup
- [x] Iniciar.bat para desenvolvimento local
- [ ] Documentar API endpoints (automatico via /docs)

### Pos-lancamento (proximos passos)
- [ ] Dashboard de metrics (Prometheus + Grafana)
- [ ] Cache Redis (ja configurado no docker-compose)
- [ ] Rate limiting reforcado por IP
- [ ] Notificacoes WhatsApp
- [ ] Celery workers para scans assincronos
