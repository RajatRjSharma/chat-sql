# Offline Text-to-SQL evaluation (Spider/BIRD-inspired)
#
# What this covers (CI-safe, no live LLM/DB):
# - Full linking pipeline recall (mention + column/synonym + FK expand)
#   via production `apply_schema_linking` — catches bugs like
#   "Total revenue by region and channel" missing `customers`
# - Overview vs analytics routing
# - Context hygiene (synthetic catalog/ER chunks stay out of column SQL context)
# - Scope gate (analytics stay answerable; trivia refused)
# - UNANSWERABLE expand-on-retry recovery
# - Empty allowlist fail-closed validation
#
# Run:
#   make eval
#   # or
#   cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/eval -q
#
# Also included in `make test` / CI (`pytest tests`).
#
# CLI snapshot (same linking checks):
#   cd backend && PYTHONPATH=. .venv/bin/python scripts/eval_live.py
#
# Live execution accuracy (EX) against a warehouse is out of scope for CI;
# smoke the golden questions manually after deploy.
#
# Industry mapping:
# | Spider/BIRD idea              | Our offline proxy                                      |
# |------------------------------|--------------------------------------------------------|
# | Exact Match (EM)             | Not in CI (LLM SQL varies)                             |
# | Execution Accuracy (EX)      | Manual smoke / future live harness                     |
# | Schema linking               | test_full_pipeline_linking_recall + catalog_fixture    |
# | Hardness / multi-dim joins   | revenue_by_region_channel, orders_by_region goldens    |
# | Component checks             | overview routing, hygiene, scope, unanswerable retry   |
