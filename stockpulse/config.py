"""Central configuration. Everything secret comes from environment variables."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Load a local .env file if present (simple parser, no extra dependency).
_env_file = ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            if _v.strip():
                os.environ.setdefault(_k.strip(), _v.strip())


def database_url() -> str:
    """Postgres URL from DATABASE_URL, or a local SQLite file for development."""
    return os.environ.get("DATABASE_URL") or f"sqlite:///{ROOT / 'stockpulse.db'}"


def incoming_dir() -> Path:
    return Path(os.environ.get("STOCKPULSE_INCOMING_DIR", ROOT / "data" / "incoming"))


def seed_dir() -> Path:
    return Path(os.environ.get("STOCKPULSE_SEED_DIR", ROOT / "data" / "seed"))


def alert_webhook_url() -> str:
    return os.environ.get("ALERT_WEBHOOK_URL", "")


# Business rules
AVG_SALES_WINDOW_DAYS = 14      # trailing window for average daily sales
REVIEW_PERIOD_DAYS = 7          # an order should cover lead time + this many days
ROW_COUNT_TOLERANCE = 0.10      # file must have product_count +/- 10% rows
