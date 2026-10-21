# StockPulse Project Charter

| Field | Value |
|---|---|
| Project | StockPulse: automated inventory data platform |
| Sponsor / PM / Engineer | Vijay Walunj |
| Version | 1.0 (fill in date approved) |
| Duration | 6 weeks, three 2-week sprints |
| Status | Draft → Approved |

## 1. Background

The inventory analytics I built during my Wollaston's internship worked, but it was manual: each day someone ran SQL queries and refreshed a Tableau workbook by hand. If that person was out, busy, or made a mistake, store managers made reorder decisions on stale or wrong numbers. StockPulse rebuilds that workflow as an automated, monitored platform on a synthetic dataset of 2,500 grocery SKUs.

## 2. Purpose

Replace a manual, person-dependent reporting process with a scheduled pipeline that loads daily sales, updates stock, validates the data, flags reorders and waste risk, and publishes results through an API and dashboards, with no human needed on a normal day.

## 3. Objectives (measurable)

| # | Objective | Measure of success |
|---|---|---|
| O1 | **Timeliness:** fresh data every morning without manual steps | Pipeline completes by 12:00 UTC on ≥ 95% of scheduled days |
| O2 | **Reliability:** bad data never reaches decision-makers | 100% of seeded bad-data incidents blocked by quality gates; zero partial loads |
| O3 | **Key-person risk removed:** anyone can operate it | A runbook lets a new person run, recover, and backfill without the author |
| O4 | **Correctness:** numbers reconcile | Verification queries return zero stock-chain or formula mismatches |
| O5 | **Access:** results available to apps and people | API endpoints respond < 2 s when warm; two Tableau dashboards published |
| O6 | **Operational maturity** | Three semantic-versioned releases and two incident postmortems completed |

## 4. Scope

**In scope:** synthetic data generator (2,500 SKUs, 8 suppliers, 90 days); six-table Postgres model; Python ETL with idempotent loads; data quality gates; pytest suite and CI; scheduled GitHub Actions pipeline; failure alerting; Flask API on Render; Operations and Platform Health dashboards in Tableau; release plan, runbook, risk log, two incident simulations with postmortems; README, demo video.

**Out of scope:** real retailer data or POS integration; placing real purchase orders; user authentication on the API; multi-store support; forecasting models beyond a trailing average; paid infrastructure.

## 5. Deliverables

Repository `stockpulse` with code and tests; live API URL; two published dashboards; `/docs` containing this charter, TDD, Jira backlog, risk log, release plan and notes, runbook, postmortems, retrospective; 3-minute demo video.

## 6. Milestones

| Milestone | Target | Exit criteria |
|---|---|---|
| M0 Plan approved | End of week 1 | Charter, TDD, Jira epics, sprint plan done |
| M1 Sprint 1 done | End of week 2 | Data model live, ETL runs locally for 10 consecutive days, numbers verified |
| M2 Sprint 2 done / **v1.0.0** | End of week 4 | Quality gates, tests, CI, scheduled pipeline, alerting |
| M3 **v1.1.0** | Week 5 | API deployed, dashboards published |
| M4 **v1.2.0** + incidents | Week 6 | Enhancement shipped, two incidents simulated, postmortems written |
| M5 Portfolio ready | Final week | README, demo video, resume bullet |

## 7. Stakeholders (simulated)

| Stakeholder | Interest | What they need |
|---|---|---|
| Store managers | Avoid stockouts and waste | Operations dashboard, `/low-stock` |
| Category/purchasing team | Order the right quantity | Suggested order quantity, supplier performance |
| TPM / platform owner | Platform is trustworthy | Platform Health dashboard, alerts, runbook |
| Recruiters / interviewers | Evidence of TPM judgment | README, docs, postmortems, demo |

## 8. Constraints and assumptions

Free tiers only (GitHub Actions, Neon or Supabase, Render, Tableau student license); free-tier terms may change and must be confirmed at sign-up. Part-time effort (~10 hours/week). Data is synthetic, so business results are illustrative, not real outcomes.

## 9. Top risks

See `risk-log.md` for the full register. Headline risks: scheduled jobs starting late; GitHub disabling schedules after 60 days of repo inactivity; free-tier database or API sleeping or hitting limits; secrets leaked into the repo; scope creep beyond six weeks.

## 10. Approval

| Role | Name | Date |
|---|---|---|
| Sponsor | Vijay Walunj | |
