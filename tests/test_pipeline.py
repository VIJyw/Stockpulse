"""End-to-end pipeline tests on SQLite: idempotency, all-or-nothing, backfill."""
import pandas as pd

from helpers import make_env
from stockpulse.pipeline import run_day


def totals(db):
    return (db.scalar("SELECT COALESCE(SUM(units_sold), 0) AS n FROM daily_sales"),
            db.scalar("SELECT COUNT(*) AS n FROM inventory_snapshots"),
            db.scalar("SELECT COALESCE(SUM(closing_stock), 0) AS n FROM inventory_snapshots"),
            db.scalar("SELECT COUNT(*) AS n FROM reorder_alerts"))


def test_runs_days_in_order_and_logs_each_run():
    db, incoming = make_env()
    for expected in ["2026-06-01", "2026-06-02", "2026-06-03"]:
        result = run_day(db, incoming_dir=incoming)
        assert result["status"] == "success" and result["run_date"] == expected
    assert db.scalar("SELECT COUNT(*) AS n FROM pipeline_runs WHERE status = 'success'") == 3


def test_running_same_day_twice_never_double_counts():
    db, incoming = make_env()
    for _ in range(5):
        run_day(db, incoming_dir=incoming)
    before = totals(db)
    skipped = run_day(db, "2026-06-05", incoming_dir=incoming)
    assert skipped["status"] == "skipped"
    forced = run_day(db, "2026-06-05", force=True, incoming_dir=incoming)
    assert forced["status"] == "success"
    assert totals(db) == before


def test_bad_file_loads_nothing_and_logs_failure():
    db, incoming = make_env()
    run_day(db, incoming_dir=incoming)
    path = incoming / "sales_2026-06-02.csv"
    good = pd.read_csv(path)
    bad = good.copy()
    bad.loc[0, "units_sold"] = -3
    bad.to_csv(path, index=False)
    before = totals(db)

    result = run_day(db, incoming_dir=incoming)
    assert result["status"] == "failed" and "check_quantities" in result["failed_checks"]
    assert totals(db) == before
    assert db.scalar("SELECT status FROM pipeline_runs ORDER BY run_id DESC LIMIT 1") == "failed"

    good.to_csv(path, index=False)                  # file fixed -> backfill the missed day
    assert run_day(db, incoming_dir=incoming)["status"] == "success"


def test_missing_file_is_reported_as_late():
    db, incoming = make_env(days=2)
    run_day(db, incoming_dir=incoming)
    run_day(db, incoming_dir=incoming)
    result = run_day(db, incoming_dir=incoming)
    assert result["status"] == "failed" and "not found" in result["error_message"]


def test_out_of_order_date_rejected():
    db, incoming = make_env()
    result = run_day(db, "2026-06-04", incoming_dir=incoming)
    assert result["status"] == "failed" and "out-of-order" in result["error_message"]
