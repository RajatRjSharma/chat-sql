#!/usr/bin/env python3
"""Optional live warehouse eval (NOT run in CI).

Requires a connected Postgres sales warehouse + AI credentials.
Uses offline golden questions and prints pass/fail for:
  - schema linking allowlist recall (via /prepare path internals)
  - optional SQL execution when DATABASE_URL is set

Usage:
  cd backend
  PYTHONPATH=. .venv/bin/python scripts/eval_live.py \\
    --database-url "$DATABASE_URL" \\
    --schema sales

Without AI keys this script only validates offline linking (same as make eval).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as scripts/eval_live.py
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.services.schema_linking_pipeline import (  # noqa: E402
    apply_schema_linking,
    real_tables,
)
from tests.eval.catalog_fixture import build_eval_catalog  # noqa: E402
from tests.eval.golden_cases import GOLDEN_CASES  # noqa: E402


def run_offline_linking() -> int:
    catalog = build_eval_catalog()
    by_name = {c.table: c for c in catalog}
    failed = 0
    print("== Offline linking pipeline (production apply_schema_linking) ==")
    for case in GOLDEN_CASES:
        if case.expect_overview or not case.must_include_tables:
            continue
        seeds = [by_name[t] for t in case.rag_seed_tables if t in by_name]
        result = apply_schema_linking(
            case.question,
            seeds,
            catalog,
            default_hops=settings.rag_expand_hops,
            max_tables=settings.rag_max_tables,
        )
        allow = set(real_tables(result.linked_chunks))
        missing = [t for t in case.must_include_tables if t not in allow]
        status = "PASS" if not missing else "FAIL"
        if missing:
            failed += 1
        print(
            f"  [{status}] {case.id}: hops={result.hops_used} "
            f"mode={result.context_mode} missing={missing or '-'}"
        )
    print(f"\n{failed} failure(s)")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default="",
        help="Optional live warehouse URL (execution checks not yet automated)",
    )
    parser.add_argument("--schema", default="sales")
    args = parser.parse_args()
    code = run_offline_linking()
    if args.database_url:
        print(
            f"\n(Live SQL EX against {args.schema} is not wired yet — "
            "use manual smoke asks after deploy.)"
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
