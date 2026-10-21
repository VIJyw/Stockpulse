-- StockPulse schema (PostgreSQL). Generated from stockpulse/db.py.
-- You don't need to run this by hand: `python -m stockpulse.pipeline init` creates everything.
-- It's here for review, the TDD, and anyone who wants to inspect the model in plain SQL.
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
    run_id          SERIAL PRIMARY KEY,
    run_date        DATE,
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL,  -- success | failed | skipped
    trigger_source  TEXT,
    rows_processed  INTEGER NOT NULL DEFAULT 0,
    alerts_created  INTEGER NOT NULL DEFAULT 0,
    failed_checks   TEXT,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_alerts_status ON reorder_alerts(status, sku);
CREATE INDEX IF NOT EXISTS idx_runs_date ON pipeline_runs(run_date);

-- Views used by Tableau and the API
DROP VIEW IF EXISTS v_latest_inventory;
CREATE VIEW v_latest_inventory AS
    SELECT s.snapshot_date, s.sku, p.name, p.category, p.supplier_id,
           p.is_perishable, p.shelf_life_days, p.reorder_point,
           s.closing_stock, s.avg_daily_sales, s.days_of_cover,
           s.below_reorder_point, s.waste_risk, s.stockout
    FROM inventory_snapshots s
    JOIN products p ON p.sku = s.sku
    WHERE s.snapshot_date = (SELECT MAX(snapshot_date) FROM inventory_snapshots);

DROP VIEW IF EXISTS v_supplier_performance;
CREATE VIEW v_supplier_performance AS
    SELECT sp.supplier_id, sp.name, sp.promised_lead_time_days,
           COUNT(a.alert_id) AS deliveries,
           SUM(CASE WHEN a.delay_days <= 0 THEN 1 ELSE 0 END) AS on_time_deliveries,
           AVG(1.0 * a.delay_days) AS avg_delay_days
    FROM suppliers sp
    LEFT JOIN reorder_alerts a
           ON a.supplier_id = sp.supplier_id AND a.status = 'received'
    GROUP BY sp.supplier_id, sp.name, sp.promised_lead_time_days;

