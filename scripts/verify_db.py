"""Run sql/verification_queries.sql against DATABASE_URL and flag mismatches.

Usage:  python scripts/verify_db.py
Uses DATABASE_URL from .env (never printed). Exits non-zero if an "expect 0 rows" query returns rows.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from stockpulse.db import Database  # noqa: E402

text = (ROOT / "sql" / "verification_queries.sql").read_text()

# A statement ends on a line whose code part (before any "--" comment) ends with ";".
chunks, cur = [], []
for line in text.splitlines():
    cur.append(line)
    if line.split("--", 1)[0].rstrip().endswith(";"):
        chunks.append("\n".join(cur))
        cur = []

db = Database()
if db.dialect != "postgres":
    sys.exit("DATABASE_URL is not set: these queries use PostgreSQL syntax.")

failures = 0
for chunk in chunks:
    titles = [l for l in chunk.splitlines() if re.match(r"--\s*\d+\.", l.strip())]
    sql = "\n".join(l.split("--", 1)[0] for l in chunk.splitlines()).strip().rstrip(";")
    if not sql:
        continue
    rows = db.query(sql)
    title = titles[0].strip("- ").strip() if titles else "(query)"
    flag = ""
    if "expect 0 rows" in chunk:
        flag = "  -> PASS (0 mismatches)" if not rows else "  -> FAIL"
        failures += bool(rows)
    print(f"\n=== {title}   [{len(rows)} rows]{flag}")
    for r in rows[:40]:
        print("   ", r)
    if len(rows) > 40:
        print(f"    ... {len(rows) - 40} more")
db.close()
sys.exit(1 if failures else 0)
