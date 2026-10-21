"""Shared test helpers: a tiny synthetic dataset in a throwaway SQLite database."""
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from stockpulse.db import Database
from stockpulse.generate_data import generate
from stockpulse.pipeline import init

START = date(2026, 6, 1)


def make_env(skus: int = 60, days: int = 10):
    """Return (db, incoming_dir) with seed data loaded and `days` sales files ready."""
    tmp = Path(tempfile.mkdtemp())
    generate(n_skus=skus, days=days, start=START, seed=7,
             seed_dir=tmp / "seed", incoming_dir=tmp / "incoming")
    db = Database(f"sqlite:///{tmp / 'test.db'}")
    init(db, seed_dir=tmp / "seed")
    return db, tmp / "incoming"


def products_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "sku": ["A", "B", "C"],
        "reorder_point": [10, 5, 8],
        "is_perishable": [0, 1, 1],
        "shelf_life_days": [None, 3, 10],
        "lead_time_days": [2, 2, 2],
        "safety_stock": [3, 2, 2],
        "supplier_id": ["S1", "S1", "S1"],
    })


EMPTY_HISTORY = pd.DataFrame(columns=["sale_date", "sku", "units_sold"])
