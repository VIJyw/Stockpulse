"""Unit tests for the transform formulas."""
import math

import pandas as pd

from helpers import EMPTY_HISTORY, products_frame
from stockpulse.transform import build_alerts, compute_snapshot, simulated_delay, suggested_order_qty

DAY = "2026-06-10"


def snapshot(sales_units, prev, received=None, history=EMPTY_HISTORY):
    sales = pd.DataFrame({"sku": ["A", "B", "C"], "units_sold": sales_units})
    return compute_snapshot(sales, products_frame(), pd.Series(prev, index=["A", "B", "C"]),
                            pd.Series(received or {}, dtype=int), history, DAY).set_index("sku")


def test_new_stock_is_yesterday_minus_sales_plus_deliveries():
    s = snapshot([4, 1, 2], [20, 10, 10], received={"A": 6})
    assert s.loc["A", "closing_stock"] == 20 + 6 - 4
    assert s.loc["B", "closing_stock"] == 9


def test_sales_capped_at_available_stock_and_stockout_flagged():
    s = snapshot([30, 1, 1], [20, 10, 10])
    assert s.loc["A", "units_sold"] == 20
    assert s.loc["A", "lost_sales"] == 10
    assert s.loc["A", "closing_stock"] == 0 and s.loc["A", "stockout"] == 1


def test_days_of_cover_uses_trailing_average():
    history = pd.DataFrame({"sale_date": ["2026-06-09"] * 3, "sku": ["A", "B", "C"],
                            "units_sold": [6, 2, 2]})
    s = snapshot([4, 2, 2], [40, 10, 10], history=history)
    assert s.loc["A", "avg_daily_sales"] == 5.0           # (6 + 4) / 2 days
    assert s.loc["A", "days_of_cover"] == 36 / 5.0


def test_days_of_cover_is_null_when_nothing_sells():
    s = snapshot([0, 1, 1], [20, 10, 10])
    assert math.isnan(s.loc["A", "days_of_cover"])


def test_reorder_flag_at_or_below_reorder_point():
    s = snapshot([10, 1, 1], [20, 10, 10])               # A closes at 10 == reorder point
    assert s.loc["A", "below_reorder_point"] == 1
    assert s.loc["C", "below_reorder_point"] == 0         # C closes at 9 > 8


def test_waste_risk_only_for_perishables_with_cover_beyond_shelf_life():
    s = snapshot([1, 1, 1], [20, 10, 10])
    assert s.loc["A", "waste_risk"] == 0                  # not perishable
    assert s.loc["B", "waste_risk"] == 1                  # 9 days cover > 3-day shelf life
    assert s.loc["C", "waste_risk"] == 0                  # 9 days cover <= 10-day shelf life


def test_suggested_order_qty_restores_stock_above_reorder_point():
    qty = suggested_order_qty(avg_daily_sales=5, lead_time_days=2, reorder_point=13,
                              closing_stock=10, review_days=7)
    assert qty == 13 + 5 * 9 - 10
    assert suggested_order_qty(1, 1, 1, 1000) == 1        # never zero or negative


def test_no_duplicate_alert_when_order_already_open():
    s = snapshot([10, 9, 1], [20, 10, 10]).reset_index()
    suppliers = pd.DataFrame({"supplier_id": ["S1"], "promised_lead_time_days": [2],
                              "sim_on_time_prob": [1.0]})
    alerts = build_alerts(s, products_frame(), suppliers, {"A"}, DAY)
    assert list(alerts["sku"]) == ["B"]
    assert alerts.iloc[0]["expected_delivery_date"] == "2026-06-12"


def test_simulated_delay_is_deterministic():
    assert simulated_delay("A", DAY, 0.5) == simulated_delay("A", DAY, 0.5)
    assert simulated_delay("A", DAY, 1.0) == 0
