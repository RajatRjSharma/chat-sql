# Offline Text-to-SQL evaluation (Spider/BIRD-inspired)
#
# What this covers (CI-safe, no live LLM/DB):
# - Schema-linking recall for mentioned tables
# - Overview vs analytics routing
# - Context hygiene (synthetic catalog/ER chunks stay out of column-level SQL context)
# - Scope gate smoke checks
# - Empty allowlist fail-closed validation
#
# Run:
#   make eval
#   # or
#   cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/eval -q
#
# Live execution accuracy (EX) against a warehouse is out of scope for CI;
# use manual smoke questions after deploy, or extend with a credentialed script later.
#
# Industry mapping:
# | Spider/BIRD idea              | Our offline proxy                          |
# |------------------------------|--------------------------------------------|
# | Exact Match (EM)             | Not in CI (LLM SQL varies)                 |
# | Execution Accuracy (EX)      | Manual / future live harness               |
# | Schema linking               | tests/eval golden must_include_tables      |
# | Component / hardness splits  | golden_cases.py ids + notes                |
