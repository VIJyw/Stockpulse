"""Incident 1 helper: corrupt a day's sales file, or restore the original.

  python scripts/make_bad_file.py 2026-07-15            # corrupt (original saved to data/quarantine/)
  python scripts/make_bad_file.py 2026-07-15 --restore  # put the good file back

The corrupted file has negative quantities, unknown SKUs, and 40% of rows missing,
which should trip several quality gates at once.
"""
import argparse
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
INCOMING = ROOT / "data" / "incoming"
QUARANTINE = ROOT / "data" / "quarantine"

p = argparse.ArgumentParser()
p.add_argument("date")
p.add_argument("--restore", action="store_true")
a = p.parse_args()

path = INCOMING / f"sales_{a.date}.csv"
backup = QUARANTINE / f"sales_{a.date}.original.csv"

if a.restore:
    shutil.copy(backup, path)
    print(f"Restored {path.name} from quarantine.")
else:
    QUARANTINE.mkdir(exist_ok=True)
    if not backup.exists():
        shutil.copy(path, backup)
    df = pd.read_csv(backup, dtype={"sku": str, "sale_date": str})
    df = df.sample(frac=0.6, random_state=1).sort_index()          # 40% of rows missing
    df.loc[df.index[:25], "units_sold"] = -df.loc[df.index[:25], "units_sold"] - 1   # negatives
    df.loc[df.index[25:30], "sku"] = [f"SKU9{i:04d}" for i in range(5)]               # unknown SKUs
    df.to_csv(path, index=False)
    print(f"Corrupted {path.name} ({len(df)} rows). Original kept at {backup.relative_to(ROOT)}.")
