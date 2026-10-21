"""Transform step: pure functions with no database access, so they are easy to test.

Core formulas
  new stock      = yesterday's closing stock + deliveries received - units sold
  days of cover  = closing stock / average daily sales (trailing window)
  reorder flag   = closing stock <= reorder point
  waste risk     = perishable AND days of cover > shelf life (stock will spoil before it sells)
"""
from __future__ import annotations

import hashlib
import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import config


def compute_snapshot(sales: pd.DataFrame, products: pd.DataFrame, prev_stock: pd.Series,
                     received: pd.Series, sales_history: pd.DataFrame, run_date: str,
                     window: int = config.AVG_SALES_WINDOW_DAYS) -> pd.DataFrame:
    """Build one inventory snapshot row per SKU for `run_date`.

    sales          today's file: sku, units_sold (customer demand recorded at the till)
    products       sku, reorder_point, is_perishable, shelf_life_days
    prev_stock     yesterday's closing stock, indexed by sku
    received       units delivered today, indexed by sku
    sales_history  earlier daily_sales rows (sale_date, sku, units_sold) for the trailing average
    """
    p = products.set_index("sku")
    demand = sales.set_index("sku")["units_sold"].astype(int).reindex(p.index, fill_value=0)
    opening = prev_stock.reindex(p.index, fill_value=0).astype(int)
    recv = received.reindex(p.index, fill_value=0).astype(int)

    available = opening + recv
    sold = np.minimum(demand, available)          # you can't sell stock you don't have
    lost = demand - sold
    closing = available - sold

    # Trailing average of demand, including today. Use demand (not capped sales)
    # so that stockouts don't make an item look slower than it really is.
    cutoff = (date.fromisoformat(run_date) - timedelta(days=window - 1)).isoformat()
    hist = sales_history[(sales_history["sale_date"].astype(str) >= cutoff)
                         & (sales_history["sale_date"].astype(str) < run_date)]
    days_seen = hist["sale_date"].nunique() + 1
    hist_total = hist.groupby("sku")["units_sold"].sum().reindex(p.index, fill_value=0)
    avg = (hist_total + demand) / days_seen

    cover = pd.Series(np.where(avg > 0, closing / avg.where(avg > 0, 1), np.nan), index=p.index)
    below_rp = closing <= p["reorder_point"]
    shelf = pd.to_numeric(p["shelf_life_days"], errors="coerce")
    waste = (p["is_perishable"].astype(int) == 1) & (closing > 0) & (
        cover.isna() | (cover > shelf.fillna(np.inf)))

    return pd.DataFrame({
        "snapshot_date": run_date,
        "sku": p.index,
        "opening_stock": opening.values,
        "units_received": recv.values,
        "units_sold": sold.values,
        "lost_sales": lost.values,
        "closing_stock": closing.values,
        "avg_daily_sales": avg.round(3).values,
        "days_of_cover": cover.round(2).values,
        "below_reorder_point": below_rp.astype(int).values,
        "waste_risk": waste.astype(int).values,
        "stockout": (closing == 0).astype(int).values,
    }).reset_index(drop=True)


def suggested_order_qty(avg_daily_sales: float, lead_time_days: int, reorder_point: int,
                        closing_stock: int,
                        review_days: int = config.REVIEW_PERIOD_DAYS) -> int:
    """Order-up-to policy.

    Target level = reorder point + expected demand over (lead time + review period).
    When the delivery lands, stock is back above the reorder point with roughly
    `review_days` of extra cover, so the SKU doesn't immediately re-alert.
    """
    target = reorder_point + avg_daily_sales * (lead_time_days + review_days)
    return max(1, int(math.ceil(target - closing_stock)))


def review_days_for(is_perishable: int, shelf_life_days) -> int:
    """Perishables get a shorter review period so we don't order more than will sell before spoiling."""
    if int(is_perishable) == 1 and shelf_life_days is not None and shelf_life_days == shelf_life_days:
        return max(1, min(config.REVIEW_PERIOD_DAYS, int(shelf_life_days) // 2))
    return config.REVIEW_PERIOD_DAYS


def simulated_delay(sku: str, run_date: str, on_time_prob: float) -> int:
    """Deterministic 'did the truck arrive late?' so reruns give identical results."""
    h = int(hashlib.sha256(f"{sku}|{run_date}".encode()).hexdigest()[:8], 16)
    u = (h % 10_000) / 10_000
    if u < on_time_prob:
        return 0
    return 1 + (h // 10_000) % 4   # 1-4 days late


def build_alerts(snapshot: pd.DataFrame, products: pd.DataFrame, suppliers: pd.DataFrame,
                 open_order_skus: set[str], run_date: str) -> pd.DataFrame:
    """Create a reorder alert for each SKU below its reorder point with no order already open."""
    cols = ["alert_id", "alert_date", "sku", "supplier_id", "stock_at_alert", "reorder_point",
            "suggested_order_qty", "expected_delivery_date", "sim_arrival_date", "status",
            "received_date", "delay_days"]
    need = snapshot[(snapshot["below_reorder_point"] == 1) & (~snapshot["sku"].isin(open_order_skus))]
    if need.empty:
        return pd.DataFrame(columns=cols)
    m = need.merge(products, on="sku").merge(
        suppliers[["supplier_id", "promised_lead_time_days", "sim_on_time_prob"]], on="supplier_id")
    d = date.fromisoformat(run_date)
    rows = []
    for r in m.itertuples(index=False):
        delay = simulated_delay(r.sku, run_date, r.sim_on_time_prob)
        rows.append({
            "alert_id": f"{r.sku}-{run_date}",
            "alert_date": run_date,
            "sku": r.sku,
            "supplier_id": r.supplier_id,
            "stock_at_alert": int(r.closing_stock),
            "reorder_point": int(r.reorder_point),
            "suggested_order_qty": suggested_order_qty(
                r.avg_daily_sales, r.lead_time_days, r.reorder_point, r.closing_stock,
                review_days_for(r.is_perishable, r.shelf_life_days)),
            "expected_delivery_date": (d + timedelta(days=int(r.promised_lead_time_days))).isoformat(),
            "sim_arrival_date": (d + timedelta(days=int(r.promised_lead_time_days) + delay)).isoformat(),
            "status": "open",
            "received_date": None,
            "delay_days": None,
        })
    return pd.DataFrame(rows, columns=cols)
