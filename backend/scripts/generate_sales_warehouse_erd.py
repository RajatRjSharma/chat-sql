#!/usr/bin/env python3
"""Generate the complete sales warehouse ERD from the checked-in SQL schema.

Outputs a zoomable SVG containing every table, column, type, key marker, and
foreign-key relationship. The SVG can be rasterized to PNG with any SVG tool.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SQL_FILES = (
    ROOT / "backend/scripts/init_warehouse.sql",
    ROOT / "backend/scripts/sales_extended/01_extend_sales_schema.sql",
)
OUTPUT = ROOT / "docs/sales-warehouse-erd-full.svg"

DOMAIN_TABLES = {
    "1  ORG & REFERENCE": [
        "regions",
        "territories",
        "departments",
        "employees",
        "warehouses",
        "channels",
        "currencies",
        "order_statuses",
        "payment_methods",
        "carriers",
    ],
    "2  CATALOG & SUPPLY": [
        "categories",
        "products",
        "product_variants",
        "product_prices",
        "suppliers",
        "supplier_products",
        "purchase_orders",
        "purchase_order_lines",
        "warehouse_inventory",
        "inventory_movements",
    ],
    "3  CUSTOMERS": [
        "customer_segments",
        "customers",
        "customer_addresses",
        "customer_contacts",
        "customer_notes",
        "loyalty_accounts",
        "loyalty_transactions",
    ],
    "4  ORDERS & FULFILLMENT": [
        "orders",
        "order_lines",
        "order_status_history",
        "payments",
        "refunds",
        "shipments",
        "shipment_lines",
        "returns",
        "return_lines",
    ],
    "5  MARKETING & SUPPORT": [
        "campaigns",
        "campaign_channels",
        "campaign_touches",
        "coupons",
        "coupon_redemptions",
        "order_discounts",
        "ticket_categories",
        "tickets",
        "ticket_messages",
    ],
    "6  FINANCE": [
        "invoices",
        "invoice_lines",
        "ledger_accounts",
        "ledger_entries",
        "exchange_rates",
    ],
}

DOMAIN_COLORS = {
    "1  ORG & REFERENCE": ("#17324d", "#eaf1f7"),
    "2  CATALOG & SUPPLY": ("#087f8c", "#e8f7f7"),
    "3  CUSTOMERS": ("#cc8500", "#fff5dd"),
    "4  ORDERS & FULFILLMENT": ("#d94f32", "#fff0ec"),
    "5  MARKETING & SUPPORT": ("#2f8b4b", "#edf8f0"),
    "6  FINANCE": ("#355da8", "#edf2fb"),
}


@dataclass
class Column:
    name: str
    data_type: str
    nullable: bool = True
    primary_key: bool = False
    foreign_key: bool = False
    unique: bool = False
    default: bool = False


@dataclass(frozen=True)
class ForeignKey:
    source_table: str
    source_column: str
    target_table: str
    target_column: str


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)

    def column(self, name: str) -> Column | None:
        return next((column for column in self.columns if column.name == name), None)


def split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def parse_column(definition: str) -> tuple[Column, ForeignKey | None] | None:
    text = definition.strip()
    if not text or re.match(
        r"^(?:CONSTRAINT|PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE|CHECK)\b",
        text,
        re.IGNORECASE,
    ):
        return None
    match = re.match(r'"?([A-Za-z_]\w*)"?\s+(.+)$', text, re.DOTALL)
    if not match:
        return None
    name, remainder = match.groups()
    keyword = re.search(
        r"\s+(?:PRIMARY\s+KEY|NOT\s+NULL|NULL|DEFAULT|REFERENCES|UNIQUE|CHECK)\b",
        remainder,
        re.IGNORECASE,
    )
    data_type = (remainder[: keyword.start()] if keyword else remainder).strip()
    data_type = re.sub(r"\s+", " ", data_type).upper()
    ref = re.search(
        r"REFERENCES\s+sales\.([A-Za-z_]\w*)\s*\(\s*([A-Za-z_]\w*)\s*\)",
        remainder,
        re.IGNORECASE,
    )
    column = Column(
        name=name,
        data_type=data_type,
        nullable=not bool(re.search(r"\bNOT\s+NULL\b", remainder, re.IGNORECASE)),
        primary_key=bool(re.search(r"\bPRIMARY\s+KEY\b", remainder, re.IGNORECASE)),
        foreign_key=ref is not None,
        unique=bool(re.search(r"\bUNIQUE\b", remainder, re.IGNORECASE)),
        default=bool(re.search(r"\bDEFAULT\b", remainder, re.IGNORECASE)),
    )
    foreign_key = (
        ForeignKey("", name, ref.group(1), ref.group(2)) if ref is not None else None
    )
    return column, foreign_key


def parse_schema() -> tuple[dict[str, Table], list[ForeignKey]]:
    sql = "\n".join(path.read_text() for path in SQL_FILES)
    sql = re.sub(r"--[^\n]*", "", sql)
    tables: dict[str, Table] = {}
    foreign_keys: list[ForeignKey] = []

    create_re = re.compile(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+sales\.([A-Za-z_]\w*)\s*"
        r"\((.*?)\)\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    for match in create_re.finditer(sql):
        table_name, body = match.groups()
        table = tables.setdefault(table_name, Table(table_name))
        definitions = split_top_level(body)
        for definition in definitions:
            parsed = parse_column(definition)
            if parsed:
                column, foreign_key = parsed
                if table.column(column.name) is None:
                    table.columns.append(column)
                if foreign_key:
                    foreign_keys.append(
                        ForeignKey(
                            table_name,
                            foreign_key.source_column,
                            foreign_key.target_table,
                            foreign_key.target_column,
                        )
                    )
                continue
            pk_match = re.search(
                r"PRIMARY\s+KEY\s*\(([^)]+)\)", definition, re.IGNORECASE
            )
            if pk_match:
                for name in pk_match.group(1).split(","):
                    column = table.column(name.strip().strip('"'))
                    if column:
                        column.primary_key = True
                        column.nullable = False
            unique_match = re.search(r"UNIQUE\s*\(([^)]+)\)", definition, re.IGNORECASE)
            if unique_match:
                for name in unique_match.group(1).split(","):
                    column = table.column(name.strip().strip('"'))
                    if column:
                        column.unique = True

    alter_re = re.compile(
        r"ALTER\s+TABLE\s+sales\.([A-Za-z_]\w*)\s+(.*?);",
        re.IGNORECASE | re.DOTALL,
    )
    for match in alter_re.finditer(sql):
        table_name, body = match.groups()
        if "ADD COLUMN" not in body.upper():
            continue
        table = tables.setdefault(table_name, Table(table_name))
        for definition in split_top_level(body):
            cleaned = re.sub(
                r"^\s*ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+",
                "",
                definition,
                flags=re.IGNORECASE,
            )
            parsed = parse_column(cleaned)
            if parsed and table.column(parsed[0].name) is None:
                table.columns.append(parsed[0])

    alter_fk_re = re.compile(
        r"ALTER\s+TABLE\s+sales\.([A-Za-z_]\w*).*?"
        r"FOREIGN\s+KEY\s*\(\s*([A-Za-z_]\w*)\s*\)\s*"
        r"REFERENCES\s+sales\.([A-Za-z_]\w*)\s*\(\s*([A-Za-z_]\w*)\s*\)",
        re.IGNORECASE | re.DOTALL,
    )
    for match in alter_fk_re.finditer(sql):
        source_table, source_column, target_table, target_column = match.groups()
        foreign_keys.append(
            ForeignKey(source_table, source_column, target_table, target_column)
        )
        column = tables[source_table].column(source_column)
        if column:
            column.foreign_key = True

    # PK columns are inherently NOT NULL.
    for table in tables.values():
        for column in table.columns:
            if column.primary_key:
                column.nullable = False

    foreign_keys = list(dict.fromkeys(foreign_keys))
    expected = {name for names in DOMAIN_TABLES.values() for name in names}
    missing = sorted(expected - tables.keys())
    extra = sorted(tables.keys() - expected)
    if missing or extra or len(tables) != 50:
        raise RuntimeError(
            f"Expected exactly 50 mapped tables; missing={missing}, extra={extra}, "
            f"parsed={len(tables)}"
        )
    return tables, foreign_keys


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def table_height(table: Table) -> int:
    return 78 + len(table.columns) * 34 + 18


def balanced_columns(tables: list[Table], count: int = 3) -> list[list[Table]]:
    columns: list[list[Table]] = [[] for _ in range(count)]
    heights = [0] * count
    for table in sorted(tables, key=table_height, reverse=True):
        index = min(range(count), key=lambda i: heights[i])
        columns[index].append(table)
        heights[index] += table_height(table) + 34
    for column in columns:
        column.sort(key=lambda table: table.name)
    return columns


def render_svg(tables: dict[str, Table], foreign_keys: list[ForeignKey]) -> str:
    width = 9000
    panel_width = 2860
    panel_gap = 105
    panel_x = [70, 70 + panel_width + panel_gap, 70 + 2 * (panel_width + panel_gap)]
    top = 330
    card_width = 870
    card_gap = 40
    panel_padding = 55
    panel_header = 72
    table_gap = 34

    domains = list(DOMAIN_TABLES)
    domain_layout: dict[str, tuple[int, int, int]] = {}
    positions: dict[str, tuple[int, int, int, int]] = {}
    row_heights: list[int] = []

    for row in range(2):
        heights: list[int] = []
        for col in range(3):
            domain = domains[row * 3 + col]
            columns = balanced_columns([tables[name] for name in DOMAIN_TABLES[domain]])
            tallest = max(
                sum(table_height(table) + table_gap for table in column)
                for column in columns
            )
            heights.append(panel_header + panel_padding * 2 + tallest)
        row_heights.append(max(heights))

    row_y = [top, top + row_heights[0] + 110]
    for index, domain in enumerate(domains):
        row, col = divmod(index, 3)
        x = panel_x[col]
        y = row_y[row]
        height = row_heights[row]
        domain_layout[domain] = (x, y, panel_width, height)
        columns = balanced_columns([tables[name] for name in DOMAIN_TABLES[domain]])
        for column_index, column in enumerate(columns):
            card_x = x + panel_padding + column_index * (card_width + card_gap)
            card_y = y + panel_header + panel_padding
            for table in column:
                height_table = table_height(table)
                positions[table.name] = (card_x, card_y, card_width, height_table)
                card_y += height_table + table_gap

    height = row_y[1] + row_heights[1] + 120
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        "<defs>",
        '<filter id="shadow" x="-10%" y="-10%" width="120%" height="130%">'
        '<feDropShadow dx="0" dy="4" stdDeviation="7" flood-color="#102a43" '
        'flood-opacity=".12"/></filter>',
        '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#4b6175"/></marker>',
        '<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">'
        '<path d="M 40 0 L 0 0 0 40" fill="none" stroke="#dbe5ec" '
        'stroke-width="1"/></pattern>',
        "</defs>",
        f'<rect width="{width}" height="{height}" fill="#f8fafc"/>',
        f'<rect width="{width}" height="{height}" fill="url(#grid)" opacity=".35"/>',
        '<text x="4500" y="92" text-anchor="middle" font-family="Arial, sans-serif" '
        'font-size="58" font-weight="800" fill="#102a43">'
        "Sales Warehouse — Complete Physical ERD</text>",
        '<text x="4500" y="148" text-anchor="middle" font-family="Arial, sans-serif" '
        'font-size="25" fill="#486581">'
        f"sales schema · {len(tables)} tables · "
        f"{sum(len(t.columns) for t in tables.values())} columns · "
        f"{len(foreign_keys)} foreign keys</text>",
        '<text x="4500" y="202" text-anchor="middle" font-family="Arial, sans-serif" '
        'font-size="21" fill="#627d98">'
        "PK primary key · FK foreign key · UQ unique · NN not null · DF default"
        "</text>",
        '<text x="4500" y="244" text-anchor="middle" font-family="Arial, sans-serif" '
        'font-size="18" fill="#829ab1">'
        "Generated from backend/scripts/init_warehouse.sql + "
        "sales_extended/01_extend_sales_schema.sql</text>",
    ]

    for domain, (x, y, panel_w, panel_h) in domain_layout.items():
        color, wash = DOMAIN_COLORS[domain]
        parts.extend(
            [
                f'<rect x="{x}" y="{y}" width="{panel_w}" height="{panel_h}" rx="24" '
                f'fill="{wash}" stroke="{color}" stroke-width="3" opacity=".94"/>',
                f'<path d="M {x + 24} {y} H {x + panel_w - 24} Q {x + panel_w} {y} '
                f'{x + panel_w} {y + 24} V {y + panel_header} H {x} V {y + 24} '
                f'Q {x} {y} {x + 24} {y} Z" fill="{color}"/>',
                f'<text x="{x + 34}" y="{y + 48}" font-family="Arial, sans-serif" '
                f'font-size="28" font-weight="800" fill="#ffffff">{esc(domain)}</text>',
            ]
        )

    # Relationships sit behind cards. FK column names in cards identify each edge.
    table_domain = {
        table_name: domain
        for domain, table_names in DOMAIN_TABLES.items()
        for table_name in table_names
    }
    for fk in foreign_keys:
        if fk.source_table not in positions or fk.target_table not in positions:
            continue
        sx, sy, sw, sh = positions[fk.source_table]
        tx, ty, tw, th = positions[fk.target_table]
        source_center = (sx + sw / 2, sy + sh / 2)
        target_center = (tx + tw / 2, ty + th / 2)
        if target_center[0] >= source_center[0]:
            x1, x2 = sx + sw, tx
        else:
            x1, x2 = sx, tx + tw
        y1, y2 = source_center[1], target_center[1]
        bend = max(70, abs(x2 - x1) * 0.38)
        c1 = x1 + bend if x2 >= x1 else x1 - bend
        c2 = x2 - bend if x2 >= x1 else x2 + bend
        color = DOMAIN_COLORS[table_domain[fk.source_table]][0]
        parts.append(
            f'<path d="M {x1:.0f} {y1:.0f} C {c1:.0f} {y1:.0f}, '
            f'{c2:.0f} {y2:.0f}, {x2:.0f} {y2:.0f}" fill="none" '
            f'stroke="{color}" stroke-width="3" opacity=".32" marker-end="url(#arrow)">'
            f"<title>{esc(fk.source_table)}.{esc(fk.source_column)} → "
            f"{esc(fk.target_table)}.{esc(fk.target_column)}</title></path>"
        )

    for table_name, (x, y, card_w, card_h) in positions.items():
        table = tables[table_name]
        domain = table_domain[table_name]
        color, _wash = DOMAIN_COLORS[domain]
        parts.extend(
            [
                f'<rect x="{x}" y="{y}" width="{card_w}" height="{card_h}" rx="14" '
                'fill="#ffffff" stroke="#bcccdc" stroke-width="2" filter="url(#shadow)"/>',
                f'<path d="M {x + 14} {y} H {x + card_w - 14} Q {x + card_w} {y} '
                f'{x + card_w} {y + 14} V {y + 58} H {x} V {y + 14} '
                f'Q {x} {y} {x + 14} {y} Z" fill="{color}"/>',
                f'<text x="{x + 22}" y="{y + 39}" font-family="Arial, sans-serif" '
                f'font-size="25" font-weight="800" fill="#ffffff">'
                f"{esc(table.name)}</text>",
                f'<text x="{x + card_w - 18}" y="{y + 38}" text-anchor="end" '
                'font-family="Arial, sans-serif" font-size="17" fill="#ffffff" '
                f'opacity=".8">{len(table.columns)} cols</text>',
            ]
        )
        row_y_pos = y + 84
        for index, column in enumerate(table.columns):
            if index:
                parts.append(
                    f'<line x1="{x + 16}" y1="{row_y_pos - 22}" '
                    f'x2="{x + card_w - 16}" y2="{row_y_pos - 22}" '
                    'stroke="#e8eef3" stroke-width="1"/>'
                )
            flags: list[str] = []
            if column.primary_key:
                flags.append("PK")
            if column.foreign_key:
                flags.append("FK")
            if column.unique:
                flags.append("UQ")
            if not column.nullable:
                flags.append("NN")
            if column.default:
                flags.append("DF")
            flag_text = " ".join(flags) or "·"
            flag_color = "#b42318" if column.primary_key else "#1f5f99"
            parts.extend(
                [
                    f'<text x="{x + 18}" y="{row_y_pos}" '
                    'font-family="Menlo,Consolas,monospace" font-size="17" '
                    f'font-weight="700" fill="{flag_color}">{esc(flag_text)}</text>',
                    f'<text x="{x + 146}" y="{row_y_pos}" '
                    'font-family="Menlo,Consolas,monospace" font-size="19" '
                    'font-weight="600" fill="#243b53">'
                    f"{esc(column.name)}</text>",
                    f'<text x="{x + card_w - 18}" y="{row_y_pos}" text-anchor="end" '
                    'font-family="Menlo,Consolas,monospace" font-size="17" '
                    f'fill="#627d98">{esc(column.data_type)}</text>',
                ]
            )
            row_y_pos += 34

    parts.extend(
        [
            f'<text x="70" y="{height - 44}" font-family="Arial, sans-serif" '
            'font-size="18" fill="#627d98">'
            "Relationship lines point from FK-bearing table to referenced table. "
            "Open the SVG for lossless zoom and relationship tooltips.</text>",
            "</svg>",
        ]
    )
    return "\n".join(parts)


def main() -> None:
    tables, foreign_keys = parse_schema()
    OUTPUT.write_text(render_svg(tables, foreign_keys))
    print(
        f"Wrote {OUTPUT} — {len(tables)} tables, "
        f"{sum(len(table.columns) for table in tables.values())} columns, "
        f"{len(foreign_keys)} foreign keys"
    )


if __name__ == "__main__":
    main()
