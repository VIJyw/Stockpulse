# StockPulse Risk Register

Scoring: Likelihood (L) and Impact (I) from 1 (low) to 5 (high). Score = L × I. Review at every sprint planning.

| ID | Risk | L | I | Score | Mitigation | Contingency | Owner | Status |
|---|---|---|---|---|---|---|---|---|
| R1 | GitHub scheduled jobs start late during busy periods, so "11:00 UTC" really means "around 11:00" | 4 | 2 | 8 | Target "by 12:00 UTC" in objectives, not an exact minute; show freshness on dashboard | Trigger manually with `workflow_dispatch` | Vijay | Open |
| R2 | GitHub disables scheduled workflows in public repos after 60 days with no repository activity, silently stopping the demo before interviews | 4 | 4 | 16 | Calendar reminder to push a small commit every few weeks; freshness tile on Platform Health dashboard; demo video as backup | Re-enable the workflow in the Actions tab, then `backfill` | Vijay | Open |
| R3 | Free-tier database limits (storage, compute hours, auto-suspend) change or are exceeded | 3 | 4 | 12 | Confirm current limits at sign-up; 90 days × 2,500 SKUs is small; monitor size | Switch to Supabase or the other provider; schema is portable | Vijay | Open |
| R4 | Render free service sleeps when idle, so first request is slow during a live demo | 5 | 2 | 10 | Warm it up with `/health` before demos; smoke test pings every 6 hours; demo video | Show recorded video | Vijay | Open |
| R5 | Database connection string leaked in code or commit history | 2 | 5 | 10 | `.env` gitignored; secrets only in GitHub Secrets/Render; review diffs before push | Rotate the password in Neon immediately; purge history | Vijay | Open |
| R6 | Corrupt or partial daily file loads bad numbers | 3 | 5 | 15 | Seven quality gates; all-or-nothing transaction | Incident procedure + backfill (runbook) | Vijay | Mitigated |
| R7 | Pipeline run twice for same day double-counts sales, causing wrong reorder decisions | 3 | 5 | 15 | Skip-if-loaded check, upserts, concurrency group in workflow, tests | `--force` reload restores correct values | Vijay | Mitigated |
| R8 | Bad API deploy breaks endpoints for consumers | 3 | 3 | 9 | CI on PRs, protected `main`, post-deploy smoke test | Render rollback or `git revert` (runbook) | Vijay | Open |
| R9 | Scope creep (forecasting, auth, multi-store) delays delivery past 6 weeks | 3 | 3 | 9 | Out-of-scope list in charter; backlog for "later" ideas | Cut v1.2.0 enhancement | Vijay | Open |
| R10 | Tableau student license delayed | 2 | 3 | 6 | Request in week 1 | Build dashboards in Tableau Public with an extract | Vijay | Open |
| R11 | Replay data runs out after 90 days | 3 | 2 | 6 | Generator supports more days; documented in runbook | Regenerate with `--days` and a later `--start` | Vijay | Open |
| R12 | Synthetic data presented as real results in interviews | 2 | 4 | 8 | Label the dataset as synthetic in README and resume bullet | n/a | Vijay | Mitigated |
