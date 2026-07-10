# Voice-Driven Data Analyst — development commands
# Run from project root: make <target>

.DEFAULT_GOAL := help

BACKEND_DIR := backend
VENV := $(BACKEND_DIR)/.venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
# Use these after `cd $(BACKEND_DIR)` (paths relative to backend/)
VENV_BIN := .venv/bin
RUN_BACKEND := cd $(BACKEND_DIR) && PYTHONPATH=.

APP_DB_CONTAINER := vda_app_db
WAREHOUSE_DB_CONTAINER := vda_warehouse_db

# Local demo warehouse defaults (Makefile only — NOT stored in .env)
# Override: make warehouse-seed DEMO_WH_HOST=db.example.com ...
DEMO_WH_NAME ?= Demo Sales Warehouse
DEMO_WH_HOST ?= localhost
DEMO_WH_PORT ?= 5433
DEMO_WH_DATABASE ?= bi_warehouse
DEMO_WH_SCHEMA ?= sales   # optional — PostgreSQL default if empty
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
	docker compose up -d

.PHONY: down
down: ## Stop and remove containers (keeps data volumes)
	docker compose down

.PHONY: destroy
destroy: ## Destroy both DB containers and wipe all stored data
	docker compose down -v --remove-orphans
	@echo "Destroyed: vda_app_db, vda_warehouse_db, and all database volumes."

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
venv: ## Create Python virtual environment
	python3 -m venv $(VENV)

.PHONY: install
install: venv ## Install backend dependencies
	$(PIP) install --upgrade pip
	$(PIP) install -r $(BACKEND_DIR)/requirements.txt

.PHONY: install-dev
install-dev: install ## Install backend + dev dependencies
	$(PIP) install -r $(BACKEND_DIR)/requirements-dev.txt

.PHONY: test
test: ## Run backend test suite
	$(RUN_BACKEND) $(VENV_BIN)/pytest tests -v

.PHONY: test-cov
test-cov: ## Run tests with coverage report
	$(RUN_BACKEND) $(VENV_BIN)/pytest tests -v --cov=app --cov-report=term-missing

# ---------------------------------------------------------------------------
# Project DB — ORM migrations (Alembic)
# ---------------------------------------------------------------------------

.PHONY: migrate
migrate: ## Apply all Alembic migrations to project DB
	$(RUN_BACKEND) $(VENV_BIN)/alembic upgrade head

.PHONY: migrate-down
migrate-down: ## Roll back one Alembic migration
	$(RUN_BACKEND) $(VENV_BIN)/alembic downgrade -1

.PHONY: migrate-history
migrate-history: ## Show Alembic migration history
	$(RUN_BACKEND) $(VENV_BIN)/alembic history --verbose

.PHONY: migrate-current
migrate-current: ## Show current Alembic revision
	$(RUN_BACKEND) $(VENV_BIN)/alembic current

.PHONY: migrate-revision
migrate-revision: ## Create new autogenerate migration (usage: make migrate-revision msg="add column")
	$(RUN_BACKEND) $(VENV_BIN)/alembic revision --autogenerate -m "$(msg)"

# ---------------------------------------------------------------------------
# Warehouse DB — SQL init, seed, demo check
# ---------------------------------------------------------------------------

.PHONY: warehouse-init
warehouse-init: ## Apply warehouse SQL schema (sales tables + readonly role)
	docker exec -i $(WAREHOUSE_DB_CONTAINER) psql -U postgres -d bi_warehouse < $(BACKEND_DIR)/scripts/init_warehouse.sql

.PHONY: warehouse-seed
warehouse-seed: ## Seed demo sales data (pass creds via DEMO_WH_* make vars)
	$(RUN_BACKEND) $(VENV_BIN)/python scripts/seed_warehouse.py $(WH_CREDS)

.PHONY: warehouse-check-cli
warehouse-check-cli: ## Inspect warehouse using CLI credentials (no project DB)
	$(RUN_BACKEND) $(VENV_BIN)/python scripts/demo_check_warehouse.py $(WH_CREDS)

.PHONY: warehouse-psql
warehouse-psql: ## Open psql shell on warehouse DB
	docker exec -it $(WAREHOUSE_DB_CONTAINER) psql -U postgres -d bi_warehouse

# ---------------------------------------------------------------------------
# API server
# ---------------------------------------------------------------------------

.PHONY: dev
dev: ## Run FastAPI dev server (reload)
	$(RUN_BACKEND) $(VENV_BIN)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# ---------------------------------------------------------------------------
# Day 1 full setup (run commands in order — does not auto-run)
# ---------------------------------------------------------------------------

.PHONY: setup-day1
setup-day1: ## Print Day 1 setup command sequence
	@echo "Run these commands in order:"
	@echo "  1. cp .env.example .env   # set APP_DB_* and AI_API_KEY"
	@echo "  2. make up"
	@echo "  3. make wait-db"
	@echo "  4. make install"
	@echo "  5. make migrate"
	@echo "  6. make warehouse-init"
	@echo "  7. make warehouse-seed"
	@echo "  8. make warehouse-check-cli   # optional: verify warehouse data"
	@echo "  9. make dev"
	@echo "Then test API manually: http://localhost:8000/docs"
	@echo "Day 2: POST /api/data/connect → POST /api/data/embed-schema → POST /api/chat"

.PHONY: setup-day1-run
setup-day1-run: up wait-db install migrate warehouse-init warehouse-seed ## Run Day 1 DB setup (then: make dev)
	@echo "Day 1 DB setup complete. Start API with: make dev"
	@echo "Test API manually: http://localhost:8000/docs"
	@echo "Day 2: connect warehouse → embed-schema → /api/chat"

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

.PHONY: clean
clean: ## Remove Python cache files
	find $(BACKEND_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find $(BACKEND_DIR) -type f -name "*.pyc" -delete 2>/dev/null || true

.PHONY: app-psql
app-psql: ## Open psql shell on project DB
	docker exec -it $(APP_DB_CONTAINER) psql -U postgres -d bi_app
