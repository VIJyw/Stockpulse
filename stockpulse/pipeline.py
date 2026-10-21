"""StockPulse daily pipeline: Extract -> Quality gates -> Transform -> Load.

Commands
  python -m stockpulse.pipeline init                 create tables/views and load seed data
  python -m stockpulse.pipeline run                  process the next unloaded day
  python -m stockpulse.pipeline run --date 2026-06-05 --force
                                                     reload the latest loaded day (idempotent)
  python -m stockpulse.pipeline backfill --days 30   process the next 30 days in order
  python -m stockpulse.pipeline status               print the last few runs

Guarantees
  * Idempotent: a day already loaded is skipped; --force reloads it by overwriting,
    never by adding. Running twice can never double-count sales.
  * All-or-nothing: the load happens in one transaction. If a quality gate fails or
    anything errors, nothing is written except a 'failed' row in pipeline_runs.
  * Ordered: day N+1 is never processed before day N, so stock levels never skip a day.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from . import config
from .db import Database
from .quality import run_all_checks
from .transform import build_alerts, compute_snapshot


class PipelineError(Exception):
    def __init__(self, message: str, failed_checks: dict | None = None):
        super().__init__(message)
        self.failed_checks = failed_checks


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def notify(message: str) -> None:
    """Send a Slack/Discord webhook message if ALERT_WEBHOOK_URL is set. Never raises."""
    url = config.alert_webhook_url()
    if not url:
        return
    try:
        body = json.dumps({"text": message, "content": message}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:  # alerting must never crash the pipeline
        print(f"warning: alert webhook failed: {exc}", file=sys.stderr)


# ---------------------------------------------------------------- init
def init(db: Database, seed_dir: Path | None = None) -> None:
    seed_dir = Path(seed_dir or config.seed_dir())
    db.create_schema()
    suppliers = pd.read_csv(seed_dir / "suppliers.csv")
    products = pd.read_csv(seed_dir / "products.csv", dtype={"sku": str})
    initial = pd.read_csv(seed_dir / "initial_inventory.csv", dtype={"sku": str, "snapshot_date": str})
    with db.transaction():
        db.upsert("suppliers", list(suppliers.columns), suppliers.itertuples(index=False), ["supplier_id"])
        db.upsert("products", list(products.columns), products.itertuples(index=False), ["sku"])
        if db.scalar("SELECT COUNT(*) AS n FROM inventory_snapshots") == 0:
            rows = [(r.snapshot_date, r.sku, int(r.closing_stock), 0, 0, 0, int(r.closing_stock),
                     0.0, None, 0, 0, 0) for r in initial.itertuples(index=False)]
            db.upsert("inventory_snapshots",
                      ["snapshot_date", "sku", "opening_stock", "units_received", "units_sold",
                       "lost_sales", "closing_stock", "avg_daily_sales", "days_of_cover",
                       "below_reorder_point", "waste_risk", "stockout"],
                      rows, ["snapshot_date", "sku"])
    print(f"Initialised: {len(suppliers)} suppliers, {len(products)} products, "
          f"opening stock dated {initial['snapshot_date'].iloc[0]}.")


# ---------------------------------------------------------------- run
def last_loaded_date(db: Database) -> str | None:
    """The latest day with stock levels (the seed opening day counts)."""
    return db.scalar("SELECT MAX(snapshot_date) AS d FROM inventory_snapshots")


def run_day(db: Database, run_date: str | None = None, force: bool = False,
            incoming_dir: Path | None = None, trigger: str = "manual") -> dict:
    """Process one day. Returns a dict describing the run (also logged in pipeline_runs)."""
    incoming_dir = Path(incoming_dir or config.incoming_dir())
    started = _now()
    last = last_loaded_date(db)
    if last is None:
        raise SystemExit("No opening stock found. Run `python -m stockpulse.pipeline init` first.")
    last = str(last)[:10]
    next_day = (date.fromisoformat(last) + timedelta(days=1)).isoformat()
    run_date = run_date or next_day

    result = {"run_date": run_date, "status": "success", "rows_processed": 0,
              "alerts_created": 0, "failed_checks": None, "error_message": None}
    try:
        already_loaded = db.scalar("SELECT COUNT(*) AS n FROM daily_sales WHERE sale_date = ?",
                                   (run_date,)) > 0
        if already_loaded and not force:
            result.update(status="skipped", error_message=f"{run_date} already loaded; use --force to reload")
            return result
        if force and already_loaded and run_date != last:
            raise PipelineError(f"--force can only reload the latest loaded day ({last}); "
                                f"reloading an older day would break the stock chain")
        if not already_loaded and run_date != next_day:
            raise PipelineError(f"out-of-order date {run_date}: next expected day is {next_day} "
                                f"(no gaps, no duplicates)")

        # ---- Extract
        path = incoming_dir / f"sales_{run_date}.csv"
        if not path.exists():
            raise PipelineError(f"sales file not found: {path.name} (file late or missing)")
        sales = pd.read_csv(path, dtype={"sku": str, "sale_date": str})

        # ---- Quality gates (before anything touches the database)
        products = pd.DataFrame(db.query("SELECT * FROM products"))
        report = run_all_checks(sales, set(products["sku"]), run_date)
        if not report.passed:
            raise PipelineError(f"quality gates failed: {report.summary()}", report.failures)
        sales["units_sold"] = sales["units_sold"].astype(int)

        # ---- Transform
        prev_day = (date.fromisoformat(run_date) - timedelta(days=1)).isoformat()
        prev = pd.DataFrame(db.query("SELECT sku, closing_stock FROM inventory_snapshots "
                                     "WHERE snapshot_date = ?", (prev_day,)))
        prev_stock = prev.set_index("sku")["closing_stock"] if not prev.empty else pd.Series(dtype=int)

        # When forcing a reload, undo today's receipts first so they are re-applied once, not twice.
        receipts_filter = "(status = 'open' OR received_date = ?)" if force else "status = 'open'"
        params = (run_date, run_date) if force else (run_date,)
        due = pd.DataFrame(db.query(
            f"SELECT alert_id, sku, suggested_order_qty, expected_delivery_date FROM reorder_alerts "
            f"WHERE {receipts_filter} AND sim_arrival_date <= ? AND alert_date < ?",
            params + (run_date,)))
        received = (due.groupby("sku")["suggested_order_qty"].sum() if not due.empty
                    else pd.Series(dtype=int))

        window_start = (date.fromisoformat(run_date)
                        - timedelta(days=config.AVG_SALES_WINDOW_DAYS)).isoformat()
        history = pd.DataFrame(db.query(
            "SELECT sale_date, sku, units_sold FROM daily_sales WHERE sale_date >= ? AND sale_date < ?",
            (window_start, run_date)), columns=["sale_date", "sku", "units_sold"])

        snapshot = compute_snapshot(sales, products, prev_stock, received, history, run_date)

        # SKUs that already have an order on the way get no second alert.
        open_orders = {r["sku"] for r in db.query(
            "SELECT DISTINCT sku FROM reorder_alerts WHERE status = 'open' AND alert_date < ?",
            (run_date,))}
        if not due.empty:
            open_orders -= set(due["sku"])  # those orders arrive today
        suppliers = pd.DataFrame(db.query("SELECT * FROM suppliers"))
        alerts = build_alerts(snapshot, products, suppliers, open_orders, run_date)

        # ---- Load (one transaction: all or nothing)
        with db.transaction():
            if force:
                db.execute("DELETE FROM reorder_alerts WHERE alert_date = ?", (run_date,))
            db.upsert("daily_sales", ["sale_date", "sku", "units_sold"],
                      sales[["sale_date", "sku", "units_sold"]].itertuples(index=False),
                      ["sale_date", "sku"])
            db.upsert("inventory_snapshots", list(snapshot.columns),
                      snapshot.itertuples(index=False), ["snapshot_date", "sku"])
            for r in due.itertuples(index=False) if not due.empty else []:
                delay = (date.fromisoformat(run_date)
                         - date.fromisoformat(str(r.expected_delivery_date)[:10])).days
                db.execute("UPDATE reorder_alerts SET status = 'received', received_date = ?, "
                           "delay_days = ? WHERE alert_id = ?", (run_date, delay, r.alert_id))
            db.upsert("reorder_alerts", list(alerts.columns),
                      alerts.itertuples(index=False), ["alert_id"])
            result.update(rows_processed=len(sales), alerts_created=len(alerts))
            _log_run(db, result, started, trigger)
        return result

    except PipelineError as exc:
        db.conn.rollback()
        result.update(status="failed", error_message=str(exc), failed_checks=exc.failed_checks)
        return result
    except Exception as exc:  # unexpected bug: still log it, still load nothing
        db.conn.rollback()
        result.update(status="failed", error_message=f"{type(exc).__name__}: {exc}")
        return result
    finally:
        if result["status"] != "success":
            with db.transaction():
                _log_run(db, result, started, trigger)


def _log_run(db: Database, result: dict, started: str, trigger: str) -> None:
    db.execute(
        "INSERT INTO pipeline_runs (run_date, started_at, finished_at, status, trigger_source, "
        "rows_processed, alerts_created, failed_checks, error_message) VALUES (?,?,?,?,?,?,?,?,?)",
        (result["run_date"], started, _now(), result["status"], trigger, result["rows_processed"],
         result["alerts_created"],
         json.dumps(result["failed_checks"]) if result["failed_checks"] else None,
         result["error_message"]))


def _print(result: dict) -> None:
    icon = {"success": "OK  ", "skipped": "SKIP", "failed": "FAIL"}[result["status"]]
    line = f"[{icon}] {result['run_date']}  rows={result['rows_processed']}  alerts={result['alerts_created']}"
    if result["error_message"]:
        line += f"  {result['error_message']}"
    print(line)


# ---------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    r = sub.add_parser("run")
    r.add_argument("--date", help="YYYY-MM-DD (default: next unloaded day)")
    r.add_argument("--force", action="store_true", help="reload the latest loaded day")
    b = sub.add_parser("backfill")
    b.add_argument("--days", type=int, help="number of days to process")
    b.add_argument("--through", help="process up to and including this date")
    sub.add_parser("status")
    a = p.parse_args(argv)

    db = Database()
    trigger = os.environ.get("STOCKPULSE_TRIGGER", "manual")
    try:
        if a.cmd == "init":
            init(db)
            return 0
        if a.cmd == "status":
            for row in db.query("SELECT run_id, run_date, status, rows_processed, alerts_created, "
                                "error_message FROM pipeline_runs ORDER BY run_id DESC LIMIT 10"):
                print(row)
            return 0
        if a.cmd == "run":
            result = run_day(db, a.date, a.force, trigger=trigger)
            _print(result)
            if result["status"] == "failed":
                notify(f":rotating_light: StockPulse pipeline FAILED for {result['run_date']}: "
                       f"{result['error_message']}")
                return 1
            return 0
        if a.cmd == "backfill":
            if a.days is None and not a.through:
                p.error("backfill needs --days N or --through YYYY-MM-DD")
            processed = 0
            while a.days is None or processed < a.days:
                nxt = (date.fromisoformat(str(last_loaded_date(db))[:10]) + timedelta(days=1)).isoformat()
                if a.through and nxt > a.through:
                    break
                result = run_day(db, trigger=f"backfill:{trigger}")
                _print(result)
                if result["status"] == "failed":
                    notify(f":rotating_light: StockPulse backfill stopped at {result['run_date']}: "
                           f"{result['error_message']}")
                    return 1
                processed += 1
            print(f"Backfill complete: {processed} day(s) processed.")
            return 0
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
