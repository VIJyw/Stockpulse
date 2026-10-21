"""Data quality gates. These run BEFORE anything is written to the database.

Every check returns a list of human-readable failures (empty list = pass).
`run_all_checks` runs every gate and reports all failures at once, so the
person on call sees the full picture instead of fixing one error at a time.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import config

REQUIRED_COLUMNS = ["sale_date", "sku", "units_sold"]


@dataclass
class QualityReport:
    failures: dict[str, list[str]] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        return "; ".join(f"{name}: {msgs[0]}" + (f" (+{len(msgs) - 1} more)" if len(msgs) > 1 else "")
                         for name, msgs in self.failures.items())


def check_required_columns(df: pd.DataFrame, **_) -> list[str]:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    return [f"missing column(s): {', '.join(missing)}"] if missing else []


def check_no_missing_keys(df: pd.DataFrame, **_) -> list[str]:
    errors = []
    for col in ("sku", "sale_date"):
        n = int(df[col].isna().sum() + (df[col].astype(str).str.strip() == "").sum())
        if n:
            errors.append(f"{n} row(s) with missing {col}")
    return errors


def check_quantities(df: pd.DataFrame, **_) -> list[str]:
    qty = pd.to_numeric(df["units_sold"], errors="coerce")
    errors = []
    if qty.isna().any():
        errors.append(f"{int(qty.isna().sum())} row(s) with missing or non-numeric units_sold")
    if (qty < 0).any():
        errors.append(f"{int((qty < 0).sum())} row(s) with negative units_sold")
    if ((qty % 1) != 0).any():
        errors.append(f"{int(((qty % 1) != 0).sum())} row(s) with fractional units_sold")
    return errors


def check_known_skus(df: pd.DataFrame, known_skus: set[str], **_) -> list[str]:
    unknown = sorted(set(df["sku"].dropna().astype(str)) - known_skus)
    return [f"{len(unknown)} SKU(s) not in products, e.g. {', '.join(unknown[:3])}"] if unknown else []


def check_no_duplicate_skus(df: pd.DataFrame, **_) -> list[str]:
    dups = int(df["sku"].duplicated().sum())
    return [f"{dups} duplicate SKU row(s) in file"] if dups else []


def check_expected_date(df: pd.DataFrame, expected_date: str, **_) -> list[str]:
    dates = set(df["sale_date"].dropna().astype(str))
    if dates != {expected_date}:
        return [f"file contains date(s) {sorted(dates)[:3]}, expected only {expected_date}"]
    return []


def check_row_count(df: pd.DataFrame, known_skus: set[str], **_) -> list[str]:
    expected = len(known_skus)
    low = int(expected * (1 - config.ROW_COUNT_TOLERANCE))
    high = int(expected * (1 + config.ROW_COUNT_TOLERANCE))
    if not low <= len(df) <= high:
        return [f"{len(df)} rows, expected {low}-{high} (one row per active SKU)"]
    return []


CHECKS = [
    check_no_missing_keys,
    check_quantities,
    check_known_skus,
    check_no_duplicate_skus,
    check_expected_date,
    check_row_count,
]


def run_all_checks(df: pd.DataFrame, known_skus: set[str], expected_date: str) -> QualityReport:
    report = QualityReport()
    column_errors = check_required_columns(df)
    if column_errors:  # nothing else can run without the columns
        report.failures["check_required_columns"] = column_errors
        return report
    for check in CHECKS:
        errors = check(df, known_skus=known_skus, expected_date=expected_date)
        if errors:
            report.failures[check.__name__] = errors
    return report
