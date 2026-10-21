"""Thin database layer.

Works against PostgreSQL (Neon/Supabase) in production and SQLite for local
development and tests. SQL is written with `?` placeholders and translated
to `%s` for Postgres, so the rest of the code never cares which one it has.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import config

SCHEMA_TEMPLATE = """
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id              TEXT PRIMARY KEY,
    name                     TEXT NOT NULL,
    promised_lead_time_days  INTEGER NOT NULL,
    sim_on_time_prob         REAL NOT NULL  -- simulation parameter only
);

CREATE TABLE IF NOT EXISTS products (
    sku              TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    category         TEXT NOT NULL,
    supplier_id      TEXT NOT NULL REFERENCES suppliers(supplier_id),
    is_perishable    INTEGER NOT NULL,
    shelf_life_days  INTEGER,
    unit_cost        REAL NOT NULL,
    lead_time_days   INTEGER NOT NULL,
    safety_stock     INTEGER NOT NULL,
    reorder_point    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_sales (
    sale_date   DATE NOT NULL,
    sku         TEXT NOT NULL REFERENCES products(sku),
    units_sold  INTEGER NOT NULL,
    PRIMARY KEY (sale_date, sku)
);

CREATE TABLE IF NOT EXISTS inventory_snapshots (
    snapshot_date        DATE NOT NULL,
    sku                  TEXT NOT NULL REFERENCES products(sku),
    opening_stock        INTEGER NOT NULL,
    units_received       INTEGER NOT NULL,
    units_sold           INTEGER NOT NULL,
    lost_sales           INTEGER NOT NULL,
    closing_stock        INTEGER NOT NULL,
    avg_daily_sales      REAL NOT NULL,
    days_of_cover        REAL,
    below_reorder_point  INTEGER NOT NULL,
    waste_risk           INTEGER NOT NULL,
    stockout             INTEGER NOT NULL,
    PRIMARY KEY (snapshot_date, sku)
);

CREATE TABLE IF NOT EXISTS reorder_alerts (
    alert_id                TEXT PRIMARY KEY,
    alert_date              DATE NOT NULL,
    sku                     TEXT NOT NULL REFERENCES products(sku),
    supplier_id             TEXT NOT NULL REFERENCES suppliers(supplier_id),
    stock_at_alert          INTEGER NOT NULL,
    reorder_point           INTEGER NOT NULL,
    suggested_order_qty     INTEGER NOT NULL,
    expected_delivery_date  DATE NOT NULL,
    sim_arrival_date        DATE NOT NULL,  -- simulation only: when the truck really shows up
    status                  TEXT NOT NULL,  -- open | received
    received_date           DATE,
    delay_days              INTEGER
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          {SERIAL_PK},
    run_date        DATE,
    started_at      {TIMESTAMP} NOT NULL,
    finished_at     {TIMESTAMP},
    status          TEXT NOT NULL,  -- success | failed | skipped
    trigger_source  TEXT,
    rows_processed  INTEGER NOT NULL DEFAULT 0,
    alerts_created  INTEGER NOT NULL DEFAULT 0,
    failed_checks   TEXT,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_alerts_status ON reorder_alerts(status, sku);
CREATE INDEX IF NOT EXISTS idx_runs_date ON pipeline_runs(run_date);
"""

VIEWS = {
    # Latest day's inventory joined to product attributes: the main Tableau source.
    "v_latest_inventory": """
        CREATE VIEW v_latest_inventory AS
        SELECT s.snapshot_date, s.sku, p.name, p.category, p.supplier_id,
               p.is_perishable, p.shelf_life_days, p.reorder_point,
               s.closing_stock, s.avg_daily_sales, s.days_of_cover,
               s.below_reorder_point, s.waste_risk, s.stockout
        FROM inventory_snapshots s
        JOIN products p ON p.sku = s.sku
        WHERE s.snapshot_date = (SELECT MAX(snapshot_date) FROM inventory_snapshots)
    """,
    # Supplier on-time performance from received orders.
    "v_supplier_performance": """
        CREATE VIEW v_supplier_performance AS
        SELECT sp.supplier_id, sp.name, sp.promised_lead_time_days,
               COUNT(a.alert_id) AS deliveries,
               SUM(CASE WHEN a.delay_days <= 0 THEN 1 ELSE 0 END) AS on_time_deliveries,
               AVG(1.0 * a.delay_days) AS avg_delay_days
        FROM suppliers sp
        LEFT JOIN reorder_alerts a
               ON a.supplier_id = sp.supplier_id AND a.status = 'received'
        GROUP BY sp.supplier_id, sp.name, sp.promised_lead_time_days
    """,
}


class Database:
    """Small wrapper over a DB-API connection (sqlite3 or psycopg2)."""

    def __init__(self, url: str | None = None):
        self.url = url or config.database_url()
        if self.url.startswith("sqlite:///"):
            self.dialect = "sqlite"
            path = self.url[len("sqlite:///"):]
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(path)
            self.conn.execute("PRAGMA foreign_keys = ON")
        elif self.url.startswith(("postgres://", "postgresql://")):
            import psycopg2  # imported lazily so local dev doesn't need it

            self.dialect = "postgres"
            self.conn = psycopg2.connect(self.url)
        else:
            raise ValueError("DATABASE_URL must start with sqlite:/// or postgresql://")

    # ---------- helpers ----------
    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.dialect == "postgres" else sql

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), tuple(params))
        cur.close()

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), tuple(params))
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, _clean_row(r))) for r in cur.fetchall()]
        cur.close()
        return rows

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        rows = self.query(sql, params)
        return next(iter(rows[0].values())) if rows else None

    def upsert(self, table: str, columns: list[str], rows: Iterable[Sequence[Any]],
               key_columns: list[str]) -> int:
        """Insert rows; if the primary key already exists, overwrite the row.

        This is what makes re-loading a day safe (idempotent).
        """
        rows = [tuple(_py(v) for v in r) for r in rows]
        if not rows:
            return 0
        col_list = ", ".join(columns)
        updates = [c for c in columns if c not in key_columns]
        conflict = (f"ON CONFLICT ({', '.join(key_columns)}) DO UPDATE SET "
                    + ", ".join(f"{c} = excluded.{c}" for c in updates)) if updates \
            else f"ON CONFLICT ({', '.join(key_columns)}) DO NOTHING"
        cur = self.conn.cursor()
        if self.dialect == "postgres":
            from psycopg2.extras import execute_values

            execute_values(cur, f"INSERT INTO {table} ({col_list}) VALUES %s {conflict}",
                           rows, page_size=1000)
        else:
            marks = ", ".join("?" for _ in columns)
            cur.executemany(f"INSERT INTO {table} ({col_list}) VALUES ({marks}) {conflict}", rows)
        cur.close()
        return len(rows)

    @contextmanager
    def transaction(self):
        """All-or-nothing block: commit on success, roll back on any error."""
        try:
            yield self
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def close(self) -> None:
        self.conn.close()

    # ---------- schema ----------
    def create_schema(self) -> None:
        ddl = SCHEMA_TEMPLATE.format(
            SERIAL_PK="INTEGER PRIMARY KEY AUTOINCREMENT" if self.dialect == "sqlite"
            else "SERIAL PRIMARY KEY",
            TIMESTAMP="TEXT" if self.dialect == "sqlite" else "TIMESTAMPTZ",
        )
        with self.transaction():
            for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
                self.execute(stmt)
            for name, body in VIEWS.items():
                self.execute(f"DROP VIEW IF EXISTS {name}")
                self.execute(body)


def _py(value: Any) -> Any:
    """Convert numpy/pandas scalars into plain Python types for the driver."""
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and value != value:  # NaN -> NULL
        return None
    return value


def _clean_row(row: Sequence[Any]) -> list[Any]:
    """Normalise driver types (dates, Decimals) to JSON-friendly values."""
    out = []
    for v in row:
        if hasattr(v, "isoformat"):
            v = v.isoformat()
        elif type(v).__name__ == "Decimal":
            v = float(v)
        out.append(v)
    return out
