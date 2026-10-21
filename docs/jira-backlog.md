# StockPulse Jira Backlog and Sprint Plan

Import `jira-import.csv` with Jira's CSV import (menu locations vary by Jira version, so search Jira help for "import issues from CSV"), or create the issues by hand from the tables below. You may need to map columns during import depending on your project type.

## Epics

| Epic | Goal |
|---|---|
| Data Foundation | Model, synthetic data, database ready |
| Pipeline & Quality | Reliable, idempotent, validated, scheduled ETL |
| API & Dashboard | Results available to apps and people |
| Release & Operations | Ship safely, recover from incidents, document |

## Sprint 1 (28 points)

**Sprint goal:** Data model and ETL pipeline running locally

| Story | Epic | Points | Acceptance criteria |
|---|---|---|---|
| Write project charter and TDD | Data Foundation | 3 | Charter and TDD reviewed and committed in /docs |
| Set up repo, Neon database, and secrets handling | Data Foundation | 2 | Repo created; .env gitignored; connection string never in code |
| Design six-table data model | Data Foundation | 3 | schema.sql reviewed; keys and grains documented in TDD |
| Build synthetic data generator | Data Foundation | 5 | 2,500 SKUs, 8 suppliers, 90 daily files with weekend and seasonal patterns |
| Implement init command to create schema and load seed data | Data Foundation | 2 | `pipeline init` creates tables/views and loads suppliers, products, opening stock |
| Implement extract/transform/load for one day | Pipeline & Quality | 8 | Stock, days of cover, reorder and waste flags computed and loaded |
| Make loads idempotent | Pipeline & Quality | 3 | Rerunning a day is skipped; --force reload leaves totals unchanged |
| Verify 10 consecutive days with SQL | Pipeline & Quality | 2 | verification_queries.sql returns zero mismatches |

## Sprint 2 (16 points)

**Sprint goal:** Quality gates, tests, CI, scheduling → v1.0.0

| Story | Epic | Points | Acceptance criteria |
|---|---|---|---|
| Add data quality gates | Pipeline & Quality | 5 | Seven gates; any failure loads nothing and is logged |
| Write pytest suite for transforms and gates | Pipeline & Quality | 3 | At least 10 tests passing locally |
| Set up CI workflow and protect main | Pipeline & Quality | 2 | Tests run on every PR; main requires passing CI |
| Schedule daily pipeline in GitHub Actions | Pipeline & Quality | 3 | Cron + manual trigger; DATABASE_URL from GitHub Secrets |
| Add failure alerting | Pipeline & Quality | 2 | GitHub email on failure; optional webhook message |
| Release v1.0.0 | Release & Operations | 1 | Go/no-go checklist passed; tag and release notes published |

## Sprint 3 (32 points)

**Sprint goal:** API, dashboards, releases v1.1.0–v1.2.0, incidents

| Story | Epic | Points | Acceptance criteria |
|---|---|---|---|
| Build Flask API with four core endpoints | API & Dashboard | 5 | /health, /low-stock, /sku/<id>, /pipeline-status return documented JSON |
| Postman collection and API docs | API & Dashboard | 2 | Collection committed; README documents every endpoint |
| Deploy API to Render with auto-deploy | API & Dashboard | 2 | Live URL; DATABASE_URL set as Render env var |
| Operations dashboard in Tableau | API & Dashboard | 5 | Low stock, cover by category, waste risk, supplier on-time |
| Platform health dashboard in Tableau | API & Dashboard | 3 | Success rate, run history, failed checks, data freshness |
| Release v1.1.0 | Release & Operations | 1 | API and dashboards live; release notes published |
| Supplier performance + suggested order qty (v1.2.0) | Release & Operations | 3 | /supplier-performance live; release notes published |
| Incident 1: bad data simulation and postmortem | Release & Operations | 3 | Gates block file; backfill done; blameless postmortem written |
| Incident 2: bad deploy simulation and postmortem | Release & Operations | 3 | Smoke test detects break; rollback done; postmortem written |
| Runbook and risk log | Release & Operations | 2 | A new person can run, recover, and backfill from the runbook |
| README, demo video, retrospective | Release & Operations | 3 | README polished; 3-minute video linked; retro written |

## Definition of Done

Code merged to `main` through a PR with passing CI; tests added or updated; docs updated where behavior changed; acceptance criteria demonstrated.
