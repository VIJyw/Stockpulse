"""Each quality gate must catch its failure and pass clean data."""
import pandas as pd

from stockpulse.quality import run_all_checks

DAY = "2026-06-10"
SKUS = {f"S{i}" for i in range(20)}


def clean():
    return pd.DataFrame({"sale_date": DAY, "sku": sorted(SKUS), "units_sold": 3})


def failed(df, day=DAY):
    return set(run_all_checks(df, SKUS, day).failures)


def test_clean_file_passes():
    assert run_all_checks(clean(), SKUS, DAY).passed


def test_missing_sku_or_date():
    df = clean()
    df.loc[0, "sku"] = None
    df.loc[1, "sale_date"] = None
    assert "check_no_missing_keys" in failed(df)


def test_negative_quantity():
    df = clean()
    df.loc[3, "units_sold"] = -5
    assert "check_quantities" in failed(df)


def test_unknown_sku():
    df = clean()
    df.loc[0, "sku"] = "GHOST"
    assert "check_known_skus" in failed(df)


def test_wrong_date_means_gap_or_duplicate():
    assert "check_expected_date" in failed(clean(), day="2026-06-11")


def test_row_count_out_of_range():
    assert "check_row_count" in failed(clean().head(5))


def test_duplicate_rows():
    df = pd.concat([clean(), clean().head(1)])
    assert "check_no_duplicate_skus" in failed(df)


def test_missing_column_short_circuits():
    report = run_all_checks(clean().drop(columns="units_sold"), SKUS, DAY)
    assert list(report.failures) == ["check_required_columns"]
