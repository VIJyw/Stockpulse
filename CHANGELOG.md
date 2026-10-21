# Changelog

All notable changes follow [Semantic Versioning](https://semver.org). Fill in release dates when you tag.

## [1.2.0] - YYYY-MM-DD
### Added
- `/supplier-performance` endpoint and `v_supplier_performance` view: deliveries, on-time rate, average delay per supplier.
- Perishable-aware suggested order quantity (shorter review period for short shelf life items).

## [1.1.0] - YYYY-MM-DD
### Added
- Flask API: `/health`, `/low-stock`, `/sku/<sku>`, `/pipeline-status`.
- Render deployment with auto-deploy from `main`; Postman collection; API smoke test workflow.
- Tableau Operations and Platform Health dashboards.

## [1.0.0] - YYYY-MM-DD
### Added
- Six-table data model and synthetic data generator (2,500 SKUs, 90 days).
- Daily ETL with idempotent loads, seven data quality gates, all-or-nothing transactions.
- pytest suite, CI on pull requests, scheduled pipeline (GitHub Actions), failure alerting.
