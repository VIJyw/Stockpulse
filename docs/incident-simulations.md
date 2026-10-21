# Incident Simulations

Run both in Sprint 3 after v1.1.0 is live. Record real timestamps as you go; you'll need them for the postmortems.

## Incident 1: Bad data

**Goal:** prove the quality gates protect decision-makers, and practice recovery with a backfill.

1. Note the next day the pipeline will process: `GET /pipeline-status` → `latest_data_date` + 1.
2. Corrupt that day's file: `python scripts/make_bad_file.py <date>`. This removes 40% of rows, makes 25 quantities negative, and adds 5 unknown SKUs. The original is saved in `data/quarantine/` (gitignored).
3. Commit and push the corrupted file, then trigger **Daily pipeline** manually (or wait for the schedule).
4. **Detect:** workflow fails, GitHub emails you, webhook fires if configured. Screenshot the failure and the Platform Health dashboard.
5. **Verify containment:** `SELECT COUNT(*) FROM daily_sales WHERE sale_date = '<date>';` → 0.
6. Optionally let one more scheduled run fail to show the pipeline stays blocked rather than skipping the day.
7. **Recover:** `python scripts/make_bad_file.py <date> --restore`, commit, push, then run the workflow with `backfill_days` set to the number of missed days.
8. **Verify:** verification queries return zero mismatches; dashboard freshness back to normal.
9. Write the postmortem from `postmortem-template.md`.

## Incident 2: Bad deploy

**Goal:** practice detect → roll back → fix forward.

1. On a branch, introduce a realistic bug in `/low-stock`, for example rename `s.closing_stock` to `s.closing_stok` in its SQL. Note the CI tests catch this, which is the point of CI. To simulate the bug slipping through, temporarily skip the API tests or merge with an admin override, and record that choice honestly in the postmortem.
2. Merge to `main`; Render auto-deploys.
3. **Detect:** the **API smoke test** workflow fails on push, or a manual `scripts/smoke_test.py` run fails on `/low-stock`.
4. **Roll back** on Render to the previous deploy; confirm smoke test passes. Note time to restore.
5. **Fix forward:** `git revert`, restore any skipped tests, merge through normal CI.
6. Write the postmortem.
