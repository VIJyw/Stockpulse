# Tableau Dashboard Guide

## Connect

In Tableau Desktop: Connect → To a Server → **PostgreSQL**. Use the host, database, user, and password from your Neon/Supabase connection string, and enable SSL. Tableau Public can't keep a live database connection, so if you publish there, use an extract and refresh it before taking screenshots.

## Data sources

| Source | Use for |
|---|---|
| `v_latest_inventory` | Today's stock, cover, and flags by SKU |
| `inventory_snapshots` joined to `products` on `sku` | Trends over time |
| `v_supplier_performance` | On-time rate per supplier |
| `pipeline_runs` | Platform health |

## Dashboard 1: Operations (store managers)

| Sheet | Build |
|---|---|
| Low-stock list | `v_latest_inventory`, filter `below_reorder_point = 1`; rows: `sku`, `name`, `category`; columns: `closing_stock`, `reorder_point`, `days_of_cover`; sort by `days_of_cover` ascending; color `stockout` |
| Days of cover by category | Bar: `category` vs AVG(`days_of_cover`); reference line at 3 days |
| Waste-risk perishables | Filter `waste_risk = 1`; show `days_of_cover` vs `shelf_life_days` |
| Supplier on-time | Bar: `name` vs calculated field `[on_time_deliveries] / [deliveries]`, formatted as % |
| KPI tiles | COUNT of SKUs below reorder point, stockouts, waste-risk items |

Add a `category` filter that applies to all sheets.

## Dashboard 2: Platform health (TPM)

| Sheet | Build |
|---|---|
| Success rate | Calculated field `IF [status] = 'success' THEN 1 ELSE 0 END`; AVG over the last 30 non-skipped runs |
| Run history | `run_id` or `started_at` on columns, `rows_processed` as bars, color by `status` |
| Failed checks | Table of failed runs: `run_date`, `error_message` |
| Data freshness | Calculated field `DATEDIFF('hour', {FIXED : MAX(IF [status] = 'success' THEN [finished_at] END)}, NOW())`; show as a big number, red if > 30 |

## Portfolio screenshots

Capture both dashboards on a normal day and the Platform Health dashboard during Incident 1 (showing the failed run). Save them to `docs/screenshots/`.
