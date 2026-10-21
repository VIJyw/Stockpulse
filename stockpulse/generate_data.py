"""Generate a synthetic grocery dataset for StockPulse.

Outputs:
  data/seed/suppliers.csv          8 suppliers with promised lead times
  data/seed/products.csv           N SKUs (default 2,500) across 10 categories
  data/seed/initial_inventory.csv  opening stock on the day before the first sales day
  data/incoming/sales_YYYY-MM-DD.csv  one file per day ("daily replay" feed)

Demand patterns: weekend spikes, summer seasonality by category, and faster
moving perishables. Fully reproducible with --seed.

Usage:
  python -m stockpulse.generate_data                      # 2,500 SKUs, 90 days
  python -m stockpulse.generate_data --skus 200 --days 30 --start 2026-06-01
"""
from __future__ import annotations

import argparse
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

# category: (share of SKUs, perishable, shelf life range, base demand median, unit cost range, items)
CATEGORIES = {
    "Produce":        (0.12, True,  (4, 10),  9.0, (0.5, 4),  ["Bananas", "Apples", "Spinach", "Tomatoes", "Avocados", "Carrots", "Berries", "Lettuce"]),
    "Dairy":          (0.10, True,  (7, 21),  7.0, (1, 6),    ["Milk", "Yogurt", "Cheddar", "Butter", "Cream", "Eggs", "Kefir", "Mozzarella"]),
    "Bakery":         (0.06, True,  (2, 5),   6.0, (1.5, 6),  ["Sourdough", "Bagels", "Croissants", "Muffins", "Baguette", "Rolls"]),
    "Meat & Seafood": (0.08, True,  (3, 7),   4.0, (4, 18),   ["Chicken Breast", "Ground Beef", "Salmon", "Pork Chops", "Shrimp", "Turkey"]),
    "Frozen":         (0.10, False, None,     3.0, (2, 9),    ["Pizza", "Peas", "Ice Cream", "Dumplings", "Waffles", "Fries"]),
    "Pantry":         (0.18, False, None,     2.5, (0.8, 7),  ["Pasta", "Rice", "Beans", "Olive Oil", "Cereal", "Flour", "Peanut Butter", "Soup"]),
    "Beverages":      (0.12, False, None,     4.0, (0.8, 8),  ["Sparkling Water", "Orange Juice", "Cola", "Iced Tea", "Coffee", "Sports Drink"]),
    "Snacks":         (0.10, False, None,     3.5, (1, 5),    ["Chips", "Pretzels", "Granola Bars", "Popcorn", "Crackers", "Trail Mix"]),
    "Household":      (0.08, False, None,     1.2, (2, 15),   ["Paper Towels", "Dish Soap", "Detergent", "Trash Bags", "Sponges"]),
    "Personal Care":  (0.06, False, None,     1.0, (2, 12),   ["Shampoo", "Toothpaste", "Body Wash", "Deodorant", "Lotion"]),
}
# Summer seasonality amplitude by category (+ means demand rises toward mid-summer).
SEASONAL_AMPLITUDE = {"Beverages": 0.25, "Produce": 0.10, "Frozen": 0.15, "Snacks": 0.08}
# Mon..Sun multipliers: weekend spike.
WEEKDAY_FACTOR = [0.88, 0.85, 0.90, 0.95, 1.12, 1.35, 1.25]
BRANDS = ["Harbor", "Green Acre", "Northside", "Bayview", "Golden Field", "Summit", "Maple Lane", "Coastal"]
SIZES = ["Small", "Regular", "Large", "Family Size", "Value Pack"]

SUPPLIERS = [
    # id, name, promised lead time (days), real on-time probability (simulation only)
    ("SUP01", "FreshFarm Distributors", 2, 0.92),
    ("SUP02", "Atlantic Dairy Co.", 2, 0.95),
    ("SUP03", "Bay State Bakeries", 1, 0.97),
    ("SUP04", "Northeast Proteins", 3, 0.85),
    ("SUP05", "ColdChain Foods", 4, 0.80),
    ("SUP06", "Pantry Wholesale", 5, 0.90),
    ("SUP07", "Beverage Partners", 4, 0.75),
    ("SUP08", "HomeGoods Supply", 7, 0.70),
]
CATEGORY_SUPPLIERS = {
    "Produce": ["SUP01"], "Dairy": ["SUP02"], "Bakery": ["SUP03"],
    "Meat & Seafood": ["SUP04"], "Frozen": ["SUP05"], "Pantry": ["SUP06", "SUP05"],
    "Beverages": ["SUP07"], "Snacks": ["SUP06", "SUP07"],
    "Household": ["SUP08"], "Personal Care": ["SUP08"],
}


def build_products(n_skus: int, rng: np.random.Generator) -> pd.DataFrame:
    lead = {s[0]: s[2] for s in SUPPLIERS}
    counts = {c: int(round(v[0] * n_skus)) for c, v in CATEGORIES.items()}
    counts["Pantry"] += n_skus - sum(counts.values())  # fix rounding so total == n_skus
    rows, i = [], 1
    for cat, (_, perishable, shelf, median, cost, items) in CATEGORIES.items():
        for _ in range(counts[cat]):
            base = float(rng.lognormal(math.log(median), 0.6))
            supplier = str(rng.choice(CATEGORY_SUPPLIERS[cat]))
            lt = lead[supplier]
            # Safety stock ~ z * sigma * sqrt(lead time); Poisson sigma ~ sqrt(demand), inflated for weekend swings.
            safety = int(math.ceil(1.65 * math.sqrt(base * lt) * 1.3 + 0.25 * base))
            rows.append({
                "sku": f"SKU{i:05d}",
                "name": f"{rng.choice(BRANDS)} {rng.choice(items)} {rng.choice(SIZES)}",
                "category": cat,
                "supplier_id": supplier,
                "is_perishable": int(perishable),
                "shelf_life_days": int(rng.integers(shelf[0], shelf[1] + 1)) if perishable else None,
                "unit_cost": round(float(rng.uniform(*cost)), 2),
                "lead_time_days": lt,
                "safety_stock": safety,
                "reorder_point": int(math.ceil(base * lt + safety)),
                "_base_demand": base,
            })
            i += 1
    return pd.DataFrame(rows)


def build_sales(products: pd.DataFrame, start: date, days: int,
                rng: np.random.Generator) -> dict[date, pd.DataFrame]:
    files = {}
    base = products["_base_demand"].to_numpy()
    amp = products["category"].map(SEASONAL_AMPLITUDE).fillna(0.0).to_numpy()
    for d in range(days):
        day = start + timedelta(days=d)
        season = 1 + amp * math.sin(math.pi * d / max(days - 1, 1))  # peaks mid-period
        lam = base * WEEKDAY_FACTOR[day.weekday()] * season
        units = rng.poisson(lam)
        files[day] = pd.DataFrame({"sale_date": day.isoformat(),
                                   "sku": products["sku"], "units_sold": units})
    return files


def generate(n_skus: int = 2500, days: int = 90, start: date = date(2026, 6, 1),
             seed: int = 42, seed_dir: Path | None = None,
             incoming_dir: Path | None = None) -> None:
    seed_dir = Path(seed_dir or config.seed_dir())
    incoming_dir = Path(incoming_dir or config.incoming_dir())
    seed_dir.mkdir(parents=True, exist_ok=True)
    incoming_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    suppliers = pd.DataFrame(SUPPLIERS, columns=["supplier_id", "name",
                                                 "promised_lead_time_days", "sim_on_time_prob"])
    products = build_products(n_skus, rng)

    # Opening stock: enough for lead time plus 2-12 days, so some SKUs start close to reorder.
    opening = products["reorder_point"] + (products["_base_demand"]
                                           * rng.uniform(2, 12, len(products))).round().astype(int)
    initial = pd.DataFrame({"snapshot_date": (start - timedelta(days=1)).isoformat(),
                            "sku": products["sku"], "closing_stock": opening})

    suppliers.to_csv(seed_dir / "suppliers.csv", index=False)
    products.drop(columns="_base_demand").to_csv(seed_dir / "products.csv", index=False)
    initial.to_csv(seed_dir / "initial_inventory.csv", index=False)
    for day, df in build_sales(products, start, days, rng).items():
        df.to_csv(incoming_dir / f"sales_{day.isoformat()}.csv", index=False)
    print(f"Generated {len(products)} SKUs, {len(suppliers)} suppliers, {days} daily sales files "
          f"({start} to {start + timedelta(days=days - 1)}).")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--skus", type=int, default=2500)
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--start", type=date.fromisoformat, default=date(2026, 6, 1))
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    generate(a.skus, a.days, a.start, a.seed)


if __name__ == "__main__":
    main()
