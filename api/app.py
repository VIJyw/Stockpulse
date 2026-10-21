"""StockPulse REST API (Flask).

Endpoints
  GET /                      list of endpoints
  GET /health                API + database reachability
  GET /low-stock             SKUs at/below reorder point, most urgent first
                             ?limit=50  ?category=Dairy  ?on_order=false
  GET /sku/<sku>             stock, days of cover, 14-day sales trend, open order
  GET /pipeline-status       last run, last successful run, data freshness
  GET /supplier-performance  on-time delivery rate per supplier (v1.2.0)

Run locally:  flask --app api.app run      Production (Render): gunicorn api.app:app
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, g, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from stockpulse import __version__  # noqa: E402
from stockpulse.db import Database  # noqa: E402


def create_app(database_url: str | None = None) -> Flask:
    app = Flask(__name__)
    app.json.sort_keys = False

    def db() -> Database:
        if "db" not in g:
            g.db = Database(database_url)
        return g.db

    @app.teardown_appcontext
    def _close(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    def latest_date() -> str | None:
        d = db().scalar("SELECT MAX(sale_date) AS d FROM daily_sales")
        return str(d)[:10] if d else None

    @app.get("/")
    def index():
        return jsonify(service="StockPulse API", version=__version__,
                       endpoints=["/health", "/low-stock", "/sku/<sku>",
                                  "/pipeline-status", "/supplier-performance"])

    @app.get("/health")
    def health():
        try:
            db().scalar("SELECT 1 AS ok")
            return jsonify(status="ok", database="reachable", version=__version__)
        except Exception as exc:  # report, don't crash
            return jsonify(status="degraded", database="unreachable", error=str(exc)), 503

    @app.get("/low-stock")
    def low_stock():
        as_of = latest_date()
        if as_of is None:
            return jsonify(as_of=None, count=0, items=[])
        try:
            limit = max(1, min(int(request.args.get("limit", 50)), 500))
        except ValueError:
            return jsonify(error="limit must be an integer"), 400
        sql = """
            SELECT s.sku, p.name, p.category, p.supplier_id, s.closing_stock, p.reorder_point,
                   s.avg_daily_sales, s.days_of_cover, s.stockout,
                   a.suggested_order_qty AS on_order_qty, a.expected_delivery_date
            FROM inventory_snapshots s
            JOIN products p ON p.sku = s.sku
            LEFT JOIN reorder_alerts a ON a.sku = s.sku AND a.status = 'open'
            WHERE s.snapshot_date = ? AND s.below_reorder_point = 1
        """
        params: list = [as_of]
        if request.args.get("category"):
            sql += " AND p.category = ?"
            params.append(request.args["category"])
        if request.args.get("on_order", "").lower() == "false":
            sql += " AND a.alert_id IS NULL"
        # Most urgent first: out of stock, then fewest days of cover.
        sql += " ORDER BY s.stockout DESC, COALESCE(s.days_of_cover, 0) ASC, s.sku LIMIT ?"
        params.append(limit)
        rows = db().query(sql, params)
        for r in rows:
            r["on_order"] = r["on_order_qty"] is not None
            r["stockout"] = bool(r["stockout"])
        total = db().scalar("SELECT COUNT(*) AS n FROM inventory_snapshots "
                            "WHERE snapshot_date = ? AND below_reorder_point = 1", (as_of,))
        return jsonify(as_of=as_of, total_below_reorder_point=total, count=len(rows), items=rows)

    @app.get("/sku/<sku>")
    def sku_detail(sku: str):
        product = db().query("SELECT * FROM products WHERE sku = ?", (sku,))
        if not product:
            return jsonify(error=f"SKU {sku} not found"), 404
        latest = db().query("SELECT * FROM inventory_snapshots WHERE sku = ? "
                            "ORDER BY snapshot_date DESC LIMIT 1", (sku,))
        trend = db().query("SELECT sale_date, units_sold FROM daily_sales WHERE sku = ? "
                           "ORDER BY sale_date DESC LIMIT 14", (sku,))
        order = db().query("SELECT alert_date, suggested_order_qty, expected_delivery_date "
                           "FROM reorder_alerts WHERE sku = ? AND status = 'open'", (sku,))
        snap = latest[0] if latest else {}
        return jsonify(
            product=product[0],
            as_of=snap.get("snapshot_date"),
            closing_stock=snap.get("closing_stock"),
            days_of_cover=snap.get("days_of_cover"),
            avg_daily_sales=snap.get("avg_daily_sales"),
            below_reorder_point=bool(snap.get("below_reorder_point", 0)),
            waste_risk=bool(snap.get("waste_risk", 0)),
            sales_trend_14d=list(reversed(trend)),
            open_order=order[0] if order else None,
        )

    @app.get("/pipeline-status")
    def pipeline_status():
        last = db().query("SELECT run_id, run_date, status, started_at, finished_at, rows_processed, "
                          "alerts_created, error_message FROM pipeline_runs "
                          "ORDER BY run_id DESC LIMIT 1")
        ok = db().query("SELECT run_date, finished_at FROM pipeline_runs WHERE status = 'success' "
                        "ORDER BY run_id DESC LIMIT 1")
        freshness = None
        if ok and ok[0]["finished_at"]:
            finished = datetime.fromisoformat(str(ok[0]["finished_at"]))
            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=timezone.utc)
            freshness = round((datetime.now(timezone.utc) - finished).total_seconds() / 3600, 1)
        recent = db().query("SELECT status FROM pipeline_runs ORDER BY run_id DESC LIMIT 30")
        counted = [r for r in recent if r["status"] != "skipped"]
        success_rate = (round(sum(r["status"] == "success" for r in counted) / len(counted), 3)
                        if counted else None)
        return jsonify(last_run=last[0] if last else None,
                       last_successful_run=ok[0] if ok else None,
                       hours_since_last_success=freshness,
                       success_rate_last_30_runs=success_rate,
                       latest_data_date=latest_date())

    @app.get("/supplier-performance")
    def supplier_performance():
        rows = db().query("SELECT * FROM v_supplier_performance ORDER BY supplier_id")
        for r in rows:
            r["on_time_rate"] = (round(r["on_time_deliveries"] / r["deliveries"], 3)
                                 if r["deliveries"] else None)
            if r["avg_delay_days"] is not None:
                r["avg_delay_days"] = round(float(r["avg_delay_days"]), 2)
        return jsonify(suppliers=rows)

    @app.errorhandler(Exception)
    def handle_error(exc):
        code = getattr(exc, "code", 500)
        return jsonify(error=str(exc)), code if isinstance(code, int) else 500

    return app


app = create_app()
