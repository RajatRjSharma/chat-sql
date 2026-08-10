"""HR-domain offline catalog fixture (employees / departments / payroll)."""

from __future__ import annotations

from app.services.schema_linker import SchemaChunk

_HR_SPECS: dict[str, tuple[str, list[dict[str, str]]]] = {
    "departments": (
        "  - department_id: integer (PK)\n"
        "  - name: varchar\n"
        "  - cost_center: varchar",
        [],
    ),
    "employees": (
        "  - employee_id: integer (PK)\n"
        "  - department_id: integer\n"
        "  - full_name: varchar\n"
        "  - title: varchar\n"
        "  - hire_date: date\n"
        "  - status: varchar",
        [
            {
                "column": "department_id",
                "referenced_table": "departments",
                "referenced_column": "department_id",
            },
        ],
    ),
    "payroll_entries": (
        "  - payroll_id: bigint (PK)\n"
        "  - employee_id: integer\n"
        "  - pay_date: date\n"
        "  - salary: numeric\n"
        "  - bonus: numeric",
        [
            {
                "column": "employee_id",
                "referenced_table": "employees",
                "referenced_column": "employee_id",
            },
        ],
    ),
    "leave_requests": (
        "  - leave_id: integer (PK)\n"
        "  - employee_id: integer\n"
        "  - leave_type: varchar\n"
        "  - days: integer\n"
        "  - status: varchar",
        [
            {
                "column": "employee_id",
                "referenced_table": "employees",
                "referenced_column": "employee_id",
            },
        ],
    ),
}

HR_CATALOG_TABLES: tuple[str, ...] = tuple(sorted(_HR_SPECS.keys()))


def build_hr_catalog() -> list[SchemaChunk]:
    chunks: list[SchemaChunk] = []
    for table, (cols, fks) in _HR_SPECS.items():
        content = f"Table: hr.{table}\nColumns:\n{cols}"
        chunks.append(
            SchemaChunk(
                table=table,
                content=content,
                metadata={
                    "chunk_kind": "table",
                    "schema": "hr",
                    "foreign_keys": fks,
                },
            )
        )
    return chunks
