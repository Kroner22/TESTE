.PHONY: help install dev test lint docker-up docker-down clean

help:
	@echo "Sports Quant Platform — Makefile"
	@echo ""
	@echo "Development:"
	@echo "  make install       Install all dependencies (Python + Node)"
	@echo "  make dev           Run API + Frontend in dev mode"
	@echo "  make test          Run all tests"
	@echo "  make lint          Lint Python and TypeScript"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-up     Start production stack"
	@echo "  make docker-down   Stop production stack"
	@echo "  make docker-build  Build images without starting"
	@echo "  make docker-logs   Tail logs from all services"
	@echo ""
	@echo "Utility:"
	@echo "  make clean         Remove cache, build artifacts"
	@echo "  make format        Auto-format Python code"
	@echo "  make check         Lint + test (pre-commit)"

install:
	cd backend && pip install -r requirements-dev.txt
	cd frontend && npm ci

dev:
	@echo "Starting API on :8000 and Frontend on :3000..."
	cd backend && uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000 &
	cd frontend && npm run dev &
	wait

test:
	cd backend && python -m pytest tests/ -v --tb=short

lint:
	cd backend && ruff check backend/ tests/
	cd frontend && npm run lint

format:
	cd backend && ruff format backend/ tests/

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-build:
	docker compose build

docker-logs:
	docker compose logs -f

docker-clean:
	docker compose down -v

check: lint test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/.next
	rm -rf frontend/node_modules
	rm -rf .coverage coverage.xml htmlcov/
	rm -rf *.egg-info dist/ build/
	@echo "Cleaned."
