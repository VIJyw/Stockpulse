"""Smoke test the live API. Exits non-zero if any endpoint is broken.

Usage:  API_BASE_URL=https://stockpulse-api.onrender.com python scripts/smoke_test.py
Free Render services sleep when idle, so the first request can take ~1 minute.
"""
import os
import sys
import time

import requests

BASE = os.environ.get("API_BASE_URL", "http://localhost:5000").rstrip("/")

CHECKS = [
    ("/health", lambda b: b["status"] == "ok"),
    ("/low-stock?limit=5", lambda b: "items" in b and isinstance(b["items"], list)),
    ("/sku/SKU00001", lambda b: b["product"]["sku"] == "SKU00001"),
    ("/pipeline-status", lambda b: "last_run" in b),
    ("/supplier-performance", lambda b: len(b["suppliers"]) > 0),
]


def get(path, attempts=4):
    for i in range(attempts):
        try:
            return requests.get(BASE + path, timeout=90)
        except requests.RequestException:
            if i == attempts - 1:
                raise
            time.sleep(15)


failures = 0
for path, ok in CHECKS:
    try:
        r = get(path)
        good = r.status_code == 200 and ok(r.json())
    except Exception as exc:  # noqa: BLE001
        good, r = False, exc
    print(f"{'PASS' if good else 'FAIL'}  {path}  ({getattr(r, 'status_code', r)})")
    failures += not good

sys.exit(1 if failures else 0)
