# ==================================================================
# AgencyOS — Makefile
# Convenience targets for local development and operations.
# On Windows, run these inside WSL / Git Bash, or call the underlying
# commands (scripts/setup/setup-dev.ps1 is provided as an alternative).
# ==================================================================

.DEFAULT_GOAL := help

-include .env
export

BACKEND_DIR  := backend
FRONTEND_DIR := frontend

.PHONY: help
help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------

.PHONY: setup
setup: ## Bootstrap the repo (env templates + storage dirs)
	@bash scripts/setup/setup-dev.sh

.PHONY: install
install: ## Install backend + frontend dependencies locally
	cd $(BACKEND_DIR) && pip install -r requirements-dev.txt
	cd $(FRONTEND_DIR) && npm install

# ------------------------------------------------------------------
# Docker Compose (dev)
# ------------------------------------------------------------------

.PHONY: up
up: ## Start infrastructure (postgres + n8n)
	docker compose up -d postgres n8n

.PHONY: up-full
up-full: ## Start everything (postgres, n8n, backend, frontend)
	docker compose --profile full up -d

.PHONY: down
down: ## Stop all services
	docker compose down

.PHONY: logs
logs: ## Tail service logs
	docker compose logs -f

.PHONY: ps
ps: ## Show running services
	docker compose ps

.PHONY: build
build: ## Build dev images
	docker compose build

# ------------------------------------------------------------------
# Production Compose (docker-compose.prod.yml)
# ------------------------------------------------------------------

.PHONY: prod-build
prod-build: ## Build production images (requires .env.production)
	docker compose -f docker-compose.prod.yml --env-file .env.production build

.PHONY: prod-up
prod-up: ## Start the production stack (requires .env.production)
	docker compose -f docker-compose.prod.yml --env-file .env.production up -d

.PHONY: prod-down
prod-down: ## Stop the production stack
	docker compose -f docker-compose.prod.yml down

# ------------------------------------------------------------------
# Local development servers
# ------------------------------------------------------------------

.PHONY: backend
backend: ## Run the FastAPI backend with hot reload
	cd $(BACKEND_DIR) && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

.PHONY: frontend
frontend: ## Run the Next.js frontend in dev mode
	cd $(FRONTEND_DIR) && npm run dev

# ------------------------------------------------------------------
# Database / migrations
# ------------------------------------------------------------------

.PHONY: migrate
migrate: ## Apply pending Alembic migrations (experimental local path)
	cd $(BACKEND_DIR) && alembic upgrade head

.PHONY: migrate-sql
migrate-sql: ## Apply SQL migrations (database/migrations/) — V1 schema path
	bash scripts/db/migrate.sh

.PHONY: migrate-new
migrate-new: ## Create a new Alembic migration (msg="...")
	cd $(BACKEND_DIR) && alembic revision --autogenerate -m "$(msg)"

.PHONY: seed
seed: ## Run database seeds (see database/seeds/)
	cd $(BACKEND_DIR) && bash ../scripts/db/seed.sh

# ------------------------------------------------------------------
# Quality (mirrors the CI pipeline)
# ------------------------------------------------------------------

.PHONY: verify-contract
verify-contract: ## Verify frontend/backend API contract + docs consistency
	cd $(BACKEND_DIR) && python scripts/ci/contract_diff.py
	cd $(BACKEND_DIR) && python scripts/ci/docs_api_consistency.py

.PHONY: ci
ci: pgcheck lint test verify-contract ## Run the full local CI pipeline

# Fail loudly (rather than silently skip) when the integration/e2e DB layer
# cannot run. Without this guard, `pytest` would report a green run with all
# DB/schema/migration tests skipped, producing a false-green `make ci`.
# Override with SKIP_DB_GUARD=1 only when you truly intend to run the frontend
# checks without the backend DB integration layer.
.PHONY: pgcheck
pgcheck: ## Verify PostgreSQL is reachable before running the full CI pipeline
	@if [ "$$SKIP_DB_GUARD" = "1" ]; then \
		echo "SKIP_DB_GUARD=1: skipping PostgreSQL reachability check."; \
	elif command -v python >/dev/null 2>&1; then \
		python scripts/ci/pg_guard.py && echo "PostgreSQL reachable." \
		|| { echo "ERROR: PostgreSQL not reachable (or TEST_POSTGRES_URL/DATABASE_URL invalid)."; \
		     echo "Start it with 'make up' (or 'docker compose up -d postgres') then re-run 'make ci'."; \
		     echo "Point TEST_POSTGRES_URL at an existing server if non-default."; \
		     echo "Override this guard (at your own risk) with: make ci SKIP_DB_GUARD=1"; \
		     exit 1; }; \
	else \
		echo "ERROR: 'python' not found; cannot verify PostgreSQL reachability for CI."; \
		exit 1; \
	fi

.PHONY: lint
lint: ## Lint backend (ruff) + frontend (eslint + prettier + typecheck)
	cd $(BACKEND_DIR) && ruff check .
	cd $(FRONTEND_DIR) && npm run lint
	cd $(FRONTEND_DIR) && npm run format:check
	cd $(FRONTEND_DIR) && npm run typecheck

.PHONY: test
test: ## Run backend + frontend test suites
	cd $(BACKEND_DIR) && pytest
	cd $(FRONTEND_DIR) && npm test

.PHONY: format
format: ## Auto-format backend (ruff) + frontend (prettier)
	cd $(BACKEND_DIR) && ruff format .
	cd $(FRONTEND_DIR) && npm run format

.PHONY: clean
clean: ## Remove caches and build artifacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf $(FRONTEND_DIR)/.next $(FRONTEND_DIR)/node_modules
	rm -rf .pytest_cache .ruff_cache coverage
