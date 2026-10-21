-- Phase 3 step 5: verify the pipeline's numbers by hand (PostgreSQL syntax; run in the Neon SQL editor or psql).

-- 1. One row per SKU per day, no gaps
SELECT sale_date, COUNT(*) AS skus FROM daily_sales GROUP BY sale_date ORDER BY sale_date;

-- 2. Stock chain holds for every SKU: today's opening = yesterday's closing
SELECT t.sku, t.snapshot_date, t.opening_stock, y.closing_stock AS yesterday_closing
FROM inventory_snapshots t
JOIN inventory_snapshots y ON y.sku = t.sku AND y.snapshot_date = t.snapshot_date - INTERVAL '1 day'
WHERE t.opening_stock <> y.closing_stock;          -- expect 0 rows

-- 3. Stock formula holds: closing = opening + received - sold
SELECT * FROM inventory_snapshots
WHERE closing_stock <> opening_stock + units_received - units_sold;   -- expect 0 rows

-- 4. Spot-check one SKU over time
SELECT snapshot_date, opening_stock, units_received, units_sold, closing_stock, days_of_cover
FROM inventory_snapshots WHERE sku = 'SKU00001' ORDER BY snapshot_date;

-- 5. Today's reorder alerts by category
SELECT p.category, COUNT(*) AS alerts, SUM(a.suggested_order_qty) AS units_ordered
FROM reorder_alerts a JOIN products p ON p.sku = a.sku
WHERE a.alert_date = (SELECT MAX(alert_date) FROM reorder_alerts)
GROUP BY p.category ORDER BY alerts DESC;

-- 6. Pipeline health: last 10 runs
SELECT run_id, run_date, status, rows_processed, alerts_created, error_message
FROM pipeline_runs ORDER BY run_id DESC LIMIT 10;
