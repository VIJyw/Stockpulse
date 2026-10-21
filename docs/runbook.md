# StockPulse Runbook

Written so someone who has never seen the project can operate it.

## 1. Normal day

Nothing to do. At about 11:00 UTC the **Daily pipeline** workflow processes the next sales file. Confirm health any time:

- `GET /pipeline-status` → `last_run.status` is `success`, `hours_since_last_success` < 30
- Platform Health dashboard → freshness tile green

## 2. Commands

| Task | Command |
|---|---|
| First-time setup | `python -m stockpulse.pipeline init` |
| Process next day | `python -m stockpulse.pipeline run` |
| Catch up N days | `python -m stockpulse.pipeline backfill --days N` |
| Catch up to a date | `python -m stockpulse.pipeline backfill --through 2026-07-20` |
| Reload latest day | `python -m stockpulse.pipeline run --date <latest> --force` |
| Recent run log | `python -m stockpulse.pipeline status` |
| Run from GitHub | Actions → Daily pipeline → Run workflow (optional `backfill_days`) |

Locally, commands use `DATABASE_URL` from `.env`; with no `.env` they use a local SQLite file.

## 3. Alerts and what they mean

| Error in `pipeline_runs.error_message` | Meaning | Action |
|---|---|---|
| `sales file not found ... (file late or missing)` | Today's file hasn't arrived | Wait for or request the file; then `run` or `backfill` |
| `quality gates failed: ...` | File is bad; **nothing was loaded** | Follow §4 (bad data) |
| `out-of-order date` | Someone asked for a day that isn't next | Use `run` with no date, or `backfill` |
| `--force can only reload the latest loaded day` | Tried to rewrite history | Only the latest day can be reloaded safely |
| `OperationalError` / connection errors | Database unreachable or suspended | Check the provider's status page; rerun |
| Any other exception | Code bug | Open an issue, fix via PR, rerun |

## 4. Bad data procedure

1. Read the failed checks: `python -m stockpulse.pipeline status` or the Platform Health dashboard.
2. Confirm nothing loaded: `SELECT COUNT(*) FROM daily_sales WHERE sale_date = '<date>';` should be 0.
3. Quarantine the bad file and get a corrected one from the source.
4. Replace `data/incoming/sales_<date>.csv`, commit and push (the scheduled job reads files from the repo).
5. Backfill: Actions → Daily pipeline → Run workflow with `backfill_days` = number of missed days.
6. Verify with `sql/verification_queries.sql`.

## 5. Bad deploy procedure

1. Detection: **API smoke test** workflow fails, or `/health` / an endpoint returns 5xx.
2. Roll back first, investigate second: in the Render dashboard, roll back to the last good deploy from the deploy history, or `git revert <sha> && git push`.
3. Confirm: `API_BASE_URL=<url> python scripts/smoke_test.py` passes.
4. Fix forward on a branch with a test that would have caught it.

## 6. Scheduled workflow stopped running

If freshness keeps growing and the Actions tab shows no recent runs, GitHub has probably disabled the schedule after 60 days of repo inactivity. Re-enable it on the workflow page, push a commit, then backfill the missed days.

## 7. Data ran out

The replay feed has 90 days. To extend: `python -m stockpulse.generate_data --start <day after last file> --days 60`. This **overwrites seed files** too, so first move existing `data/seed` aside and restore it afterward, or extend in a scratch folder and copy only the new `sales_*.csv` files.

## 8. Rotating the database password

Reset it in Neon/Supabase, then update `DATABASE_URL` in GitHub Secrets, Render environment variables, and your local `.env`. Run `/health` to confirm.
