"""IoT-domain offline catalog fixture (devices / sensors / readings)."""

from __future__ import annotations

from app.services.schema_linker import SchemaChunk

_IOT_SPECS: dict[str, tuple[str, list[dict[str, str]]]] = {
    "sites": (
        "  - site_id: integer (PK)\n"
        "  - name: varchar\n"
        "  - timezone: varchar",
        [],
    ),
    "devices": (
        "  - device_id: integer (PK)\n"
        "  - site_id: integer\n"
        "  - device_code: varchar\n"
        "  - device_type: varchar\n"
        "  - status: varchar",
        [
            {
                "column": "site_id",
                "referenced_table": "sites",
                "referenced_column": "site_id",
            },
        ],
    ),
    "sensors": (
        "  - sensor_id: integer (PK)\n"
        "  - device_id: integer\n"
        "  - metric_name: varchar\n"
        "  - unit: varchar",
        [
            {
                "column": "device_id",
                "referenced_table": "devices",
                "referenced_column": "device_id",
            },
        ],
    ),
    "sensor_readings": (
        "  - reading_id: bigint (PK)\n"
        "  - sensor_id: integer\n"
        "  - recorded_at: timestamp\n"
        "  - temperature: numeric\n"
        "  - humidity: numeric\n"
        "  - pressure: numeric",
        [
            {
                "column": "sensor_id",
                "referenced_table": "sensors",
                "referenced_column": "sensor_id",
            },
        ],
    ),
}

IOT_CATALOG_TABLES: tuple[str, ...] = tuple(sorted(_IOT_SPECS.keys()))


def build_iot_catalog() -> list[SchemaChunk]:
    chunks: list[SchemaChunk] = []
    for table, (cols, fks) in _IOT_SPECS.items():
        content = f"Table: iot.{table}\nColumns:\n{cols}"
        chunks.append(
            SchemaChunk(
                table=table,
                content=content,
                metadata={
                    "chunk_kind": "table",
                    "schema": "iot",
                    "foreign_keys": fks,
                },
            )
        )
    return chunks
