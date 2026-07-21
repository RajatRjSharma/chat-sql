# Voice-Driven Data Analyst — development commands
# Run from project root: make <target>

.DEFAULT_GOAL := help

BACKEND_DIR := backend
VENV := $(BACKEND_DIR)/.venv
PYTHON := $(VENV)/bin/python
# Prefer `python -m <tool>` over console scripts (portable across machines/paths)
RUN_PY := cd $(BACKEND_DIR) && PYTHONPATH=. .venv/bin/python

APP_DB_CONTAINER := vda_app_db
WAREHOUSE_DB_CONTAINER := vda_warehouse_db
export COMPOSE_PROJECT_NAME := vda

# Local demo warehouse defaults (Makefile only; not read from .env)
# Override example: make warehouse-seed DEMO_WH_HOST=db.example.com ...
DEMO_WH_NAME ?= Demo Sales Warehouse
DEMO_WH_HOST ?= localhost
DEMO_WH_PORT ?= 5433
DEMO_WH_DATABASE ?= bi_warehouse
DEMO_WH_SCHEMA ?= sales   # optional; empty uses the PostgreSQL connection default
DEMO_WH_USER ?= bi_readonly
DEMO_WH_PASSWORD ?= readonly_pass
DEMO_WH_ADMIN_USER ?= postgres
DEMO_WH_ADMIN_PASSWORD ?= postgres

WH_CREDS = --name "$(DEMO_WH_NAME)" --host $(DEMO_WH_HOST) --port $(DEMO_WH_PORT) \
	--database $(DEMO_WH_DATABASE) --schema $(DEMO_WH_SCHEMA) \
	--username $(DEMO_WH_USER) --password $(DEMO_WH_PASSWORD) \
	--admin-username $(DEMO_WH_ADMIN_USER) --admin-password $(DEMO_WH_ADMIN_PASSWORD)

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

.PHONY: help
help: ## Show available commands
	@echo "Voice-Driven Data Analyst — Makefile commands"
	@echo ""
	@grep -E '^[a-zA-Z0-9_.-]+:.*##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Docker — databases
# ---------------------------------------------------------------------------

.PHONY: up
up: ## Start app_db (5432) and warehouse_db (5433)
	docker compose up -d --remove-orphans

.PHONY: down
down: ## Stop and remove containers (keeps data volumes)
	docker compose down --remove-orphans

.PHONY: destroy
destroy: ## Destroy both DB containers and wipe all stored data
	docker compose down -v --remove-orphans
	-docker rm -f $(APP_DB_CONTAINER) $(WAREHOUSE_DB_CONTAINER) >/dev/null 2>&1
	@echo "Destroyed: $(APP_DB_CONTAINER), $(WAREHOUSE_DB_CONTAINER), and all database volumes."

.PHONY: down-volumes
down-volumes: destroy ## Alias for make destroy

.PHONY: ps
ps: ## Show container status
	docker compose ps

.PHONY: logs
logs: ## Tail database logs
	docker compose logs -f

.PHONY: wait-db
wait-db: ## Wait until both databases are healthy
	@echo "Waiting for app_db..."
	@until docker exec $(APP_DB_CONTAINER) pg_isready -U postgres -d bi_app >/dev/null 2>&1; do sleep 1; done
	@echo "Waiting for warehouse_db..."
	@until docker exec $(WAREHOUSE_DB_CONTAINER) pg_isready -U postgres -d bi_warehouse >/dev/null 2>&1; do sleep 1; done
	@echo "Both databases are ready."

# ---------------------------------------------------------------------------
# Python environment
# ---------------------------------------------------------------------------

.PHONY: venv
venv: ## Create the virtual environment if missing or unusable
	@if [ ! -x "$(PYTHON)" ]; then \
		echo "Creating virtualenv at $(VENV)..."; \
		python3 -m venv $(VENV); \
	elif ! "$(PYTHON)" -c "import sys; from pathlib import Path; \
		raise SystemExit(0 if Path(sys.prefix).resolve() == Path('$(CURDIR)/$(VENV)').resolve() else 1)" \
		2>/dev/null; then \
		echo "Virtualenv is broken or was moved; recreating $(VENV)..."; \
		rm -rf $(VENV); \
		python3 -m venv $(VENV); \
	fi

.PHONY: venv-recreate
venv-recreate: ## Recreate the virtual environment from scratch
	rm -rf $(VENV)
	python3 -m venv $(VENV)

.PHONY: install
install: venv ## Create venv if needed, then install backend dependencies
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r $(BACKEND_DIR)/requirements.txt

.PHONY: install-dev
install-dev: install ## Install backend + dev dependencies
	$(PYTHON) -m pip install -r $(BACKEND_DIR)/requirements-dev.txt

.PHONY: test
test: ## Run backend test suite
	$(RUN_PY) -m pytest tests -v

.PHONY: test-cov
test-cov: ## Run tests with coverage report
	$(RUN_PY) -m pytest tests -v --cov=app --cov-report=term-missing

# ---------------------------------------------------------------------------
# Project DB — ORM migrations (Alembic)
# ---------------------------------------------------------------------------

.PHONY: migrate
migrate: ## Apply all Alembic migrations to project DB
	$(RUN_PY) -m alembic upgrade head

.PHONY: migrate-down
migrate-down: ## Roll back one Alembic migration
	$(RUN_PY) -m alembic downgrade -1

.PHONY: migrate-history
migrate-history: ## Show Alembic migration history
	$(RUN_PY) -m alembic history --verbose

.PHONY: migrate-current
migrate-current: ## Show current Alembic revision
	$(RUN_PY) -m alembic current

.PHONY: migrate-revision
migrate-revision: ## Create new autogenerate migration (usage: make migrate-revision msg="add column")
	$(RUN_PY) -m alembic revision --autogenerate -m "$(msg)"

# ---------------------------------------------------------------------------
# Warehouse DB — SQL init, seed, demo check
# ---------------------------------------------------------------------------

.PHONY: warehouse-init
warehouse-init: ## Apply warehouse SQL schema (sales + readonly + uploader roles)
	docker exec -i $(WAREHOUSE_DB_CONTAINER) psql -U postgres -d bi_warehouse < $(BACKEND_DIR)/scripts/init_warehouse.sql

.PHONY: warehouse-seed
warehouse-seed: ## Seed demo sales data (pass creds via DEMO_WH_* make vars)
	$(RUN_PY) scripts/seed_warehouse.py $(WH_CREDS)

.PHONY: warehouse-check-cli
warehouse-check-cli: ## Inspect warehouse using CLI credentials (no project DB)
	$(RUN_PY) scripts/demo_check_warehouse.py $(WH_CREDS)

.PHONY: warehouse-psql
warehouse-psql: ## Open psql shell on warehouse DB
	docker exec -it $(WAREHOUSE_DB_CONTAINER) psql -U postgres -d bi_warehouse

# ---------------------------------------------------------------------------
# API server
# ---------------------------------------------------------------------------

.PHONY: dev
dev: ## Run FastAPI dev server (reload)
	$(RUN_PY) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# ---------------------------------------------------------------------------
# Frontend (Next.js)
# ---------------------------------------------------------------------------

FRONTEND_DIR := frontend

.PHONY: frontend-install
frontend-install: ## Install frontend npm dependencies
	cd $(FRONTEND_DIR) && npm install

.PHONY: frontend-dev
frontend-dev: ## Run Next.js dev server (port 3000)
	cd $(FRONTEND_DIR) && npm run dev

.PHONY: frontend-build
frontend-build: ## Production build of the Next.js app
	cd $(FRONTEND_DIR) && npm run build

.PHONY: frontend-e2e-install
frontend-e2e-install: ## Install Playwright Chromium browser (once per machine)
	cd $(FRONTEND_DIR) && npx playwright install chromium

.PHONY: frontend-e2e
frontend-e2e: ## Run Playwright UI E2E tests (mocked API)
	cd $(FRONTEND_DIR) && npm run test:e2e

.PHONY: frontend-e2e-ui
frontend-e2e-ui: ## Open Playwright UI mode
	cd $(FRONTEND_DIR) && npm run test:e2e:ui

# ---------------------------------------------------------------------------
# Full local setup
# ---------------------------------------------------------------------------

.PHONY: setup
setup: ## Print recommended setup command sequence
	@echo "Run these commands in order:"
	@echo "  1. cp .env.example .env   # set APP_DB_* and AI_API_KEY"
	@echo "  2. make up"
	@echo "  3. make wait-db"
	@echo "  4. make install"
	@echo "  5. make migrate"
	@echo "  6. make warehouse-init"
	@echo "  7. make warehouse-seed"
	@echo "  8. make warehouse-check-cli   # optional: verify warehouse data"
	@echo "  9. make frontend-install"
	@echo " 10. make dev                   # terminal A — API :8000"
	@echo " 11. make frontend-dev          # terminal B — UI  :3000"
	@echo "API docs: http://localhost:8000/docs"
	@echo "UI: http://localhost:3000"
	@echo "Flow: connect warehouse → embed-schema → chat (UI or API)"

.PHONY: setup-run
setup-run: up wait-db install migrate warehouse-init warehouse-seed ## Provision databases and dependencies
	@echo "Setup complete. Start the API with: make dev"
	@echo "Start the UI with: make frontend-dev  (after make frontend-install)"
	@echo "API docs: http://localhost:8000/docs"
	@echo "UI: http://localhost:3000"
	@echo "Flow: connect warehouse → embed-schema → chat"

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

.PHONY: clean
clean: ## Remove Python cache files
	find $(BACKEND_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find $(BACKEND_DIR) -type f -name "*.pyc" -delete 2>/dev/null || true
	find $(BACKEND_DIR) -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

.PHONY: app-psql
app-psql: ## Open psql shell on project DB
	docker exec -it $(APP_DB_CONTAINER) psql -U postgres -d bi_app
