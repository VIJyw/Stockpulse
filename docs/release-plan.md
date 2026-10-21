# StockPulse Release Plan

## Versioning

Semantic versioning `MAJOR.MINOR.PATCH`. MAJOR = breaking change to the API or schema; MINOR = new backward-compatible feature; PATCH = bug fix. Each release is a Git tag plus a GitHub Release with notes copied from `CHANGELOG.md`.

## Release scope

| Version | Contents | Target |
|---|---|---|
| v1.0.0 | Data model, ETL, idempotent loads, quality gates, tests, CI, scheduled pipeline, alerting | End of Sprint 2 |
| v1.1.0 | Flask API (`/health`, `/low-stock`, `/sku/<id>`, `/pipeline-status`) on Render, Postman collection, Tableau dashboards | Mid Sprint 3 |
| v1.2.0 | Supplier lead-time tracking (`/supplier-performance`, `v_supplier_performance`) and perishable-aware suggested order quantity | End of Sprint 3 |

## Go / no-go checklist

| # | Check | Go? |
|---|---|---|
| 1 | All CI tests pass on the release commit | ☐ |
| 2 | Verification queries return zero mismatches on the latest data | ☐ |
| 3 | Last 3 scheduled pipeline runs succeeded | ☐ |
| 4 | Smoke test passes against the deployed API | ☐ |
| 5 | No secrets in the diff (`git diff <last-tag>..HEAD` reviewed) | ☐ |
| 6 | README, API docs, and CHANGELOG updated | ☐ |
| 7 | Rollback steps below confirmed for this release | ☐ |

Any unchecked box = no-go. Record the decision and date in the release notes.

## Release steps

1. Merge the release PR into `main` (CI must pass).
2. Render auto-deploys `main`; wait for "Live", then run `python scripts/smoke_test.py`.
3. Tag: `git tag -a v1.1.0 -m "v1.1.0" && git push origin v1.1.0`.
4. Create a GitHub Release from the tag with the CHANGELOG section as notes.

## Rollback plan

| What broke | Rollback | Time to restore |
|---|---|---|
| API deploy | In the Render dashboard, open the service's deploy history and roll back to the last good deploy; or `git revert <sha>` and push | Minutes |
| Pipeline code | `git revert <sha>`; rerun; if a bad load got through, `run --date <latest> --force` after the fix | Minutes |
| Schema change | Additive changes only within a MINOR release, so old code keeps working; revert code first | Minutes |
| Bad data loaded | Replace file, `run --date <latest> --force` (latest day only) | Minutes |
