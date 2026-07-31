# Phase 17 Handover

## 1. Project Overview

- Project name: Project Germania（德国汽车市场价格与销量智能监测平台）
- Current phase: Phase 16 completed; this file is the lightweight Phase 17 handover.
- Architecture: YAML configuration → AutoScout24 collector/loader → parser → idempotent import service/repository → SQLAlchemy + SQLite → statistics, Excel/CSV export, quality report, and market monitor scripts.

## 2. Completed Functions

- Collection: bounded single-page, batch, and configuration-driven multi-model AutoScout24 workflows with shared Playwright resources and immutable raw HTML.
- Parser: real AutoScout24 result-card parsing with missing-field warnings.
- Import: idempotent Listing upsert and append-only price history when price changes.
- SQLite: 786 current marketplace listings and 786 price-history rows in the checked database.
- Export: formatted Marketplace Excel workbook plus Listings, Price History, Brand Summary, and Vehicle Summary CSV files.
- Quality Report: completeness, missing values, duplicate IDs, missing history, price/mileage anomalies, and brand/model consistency.
- Market Monitor: cutoff-based comparison of baseline and later collection windows; inferred removal is not a confirmed sale or permanent delisting.

## 3. Important Project Paths

- `config/`: source, canonical vehicle, and marketplace collection task YAML.
- `scripts/`: supported command-line entry points for collection, statistics, exports, quality reporting, and market monitoring.
- `src/germania/`: collectors, parsers, import/repository/database code, reporting, quality, and monitoring modules.
- `tests/`: unit and integration tests using fixtures and temporary SQLite databases.
- `exports/`: generated Excel/CSV outputs; ignored by Git.
- `database/`: repository placeholder (`.gitkeep`) only. The actively used SQLite file is outside the repository; the handover package copies it to `phase17_input/database/`.

## 4. SQLite Database

- Original checked location: `C:\Users\卢虹先\.codex\visualizations\2026\07\18\019f76b5-fb74-79c3-af2d-36de38efc7ec\phase_14_5b\project_germania_live.sqlite3`
- Repository-relative path: none (the source database is on another drive).
- Handover-package relative path: `phase17_input/database/project_germania_live.sqlite3`
- File name: `project_germania_live.sqlite3`

Schema checked read-only with SQLite `PRAGMA table_info` and `PRAGMA foreign_key_list`:

- `brands` (11 rows) — fields: `brand_id, canonical_brand, chinese_brand, manufacturer, country_of_origin, active, created_at, updated_at`; PK: `brand_id`; FK: none.
- `collection_batches` (0 rows) — fields: `collection_batch_id, data_source_id, batch_id, record_type, collection_method, collection_job_id, started_at, completed_at, status, record_count, success_count, failure_count, source_file_name, raw_file_path, raw_payload_reference, parser_version, checksum, notes, created_at`; PK: `collection_batch_id`; FK: `data_source_id → data_sources.data_source_id`.
- `data_quality_issues` (0 rows) — fields: `data_quality_issue_id, entity_type, entity_id, issue_code, severity, description, resolution_status, detected_at, resolved_at, resolution_notes, created_at, updated_at`; PK: `data_quality_issue_id`; FK: none.
- `data_source_categories` (21 rows) — fields: `data_source_category_id, data_source_id, data_category`; PK: `data_source_category_id`; FK: `data_source_id → data_sources.data_source_id`.
- `data_sources` (12 rows) — fields: `data_source_id, source_id, source_name, source_type, country_code, base_url, update_frequency, authority_level, active, collection_method, notes, created_at, updated_at`; PK: `data_source_id`; FK: none.
- `estimated_transaction_prices` (0 rows) — fields: `estimated_transaction_price_id, marketplace_listing_id, marketplace_listing_observation_id, vehicle_variant_id, estimated_transaction_price, currency, estimation_method, estimation_version, confidence_level, input_reference, estimated_at, valid_date, notes, created_at`; PK: `estimated_transaction_price_id`; FK: `marketplace_listing_id → marketplace_listings.marketplace_listing_id`, `marketplace_listing_observation_id → marketplace_listing_observations.marketplace_listing_observation_id`, `vehicle_variant_id → vehicle_variants.vehicle_variant_id`.
- `exchange_rate_observations` (0 rows) — fields: `exchange_rate_observation_id, data_source_id, base_currency, quote_currency, exchange_rate, exchange_rate_date, observed_at, collected_at, source_url, data_quality_status, validation_status, notes, created_at`; PK: `exchange_rate_observation_id`; FK: `data_source_id → data_sources.data_source_id`.
- `marketplace_listing_observations` (0 rows) — fields: `marketplace_listing_observation_id, marketplace_listing_id, collection_batch_id, listed_price, currency, price_includes_vat, observed_at, collected_at, listing_status, mileage_km, source_url, data_quality_status, validation_status, duplicate_key, notes, created_at`; PK: `marketplace_listing_observation_id`; FK: `marketplace_listing_id → marketplace_listings.marketplace_listing_id`, `collection_batch_id → collection_batches.collection_batch_id`.
- `marketplace_listings` (786 rows) — fields: `marketplace_listing_id, data_source_id, external_listing_id, vehicle_id, vehicle_variant_id, brand_name, model_name, variant_name, title, current_price_amount, currency, registration_year, model_year, first_registration_date, fuel_type, transmission, power_kw, vehicle_condition, body_type, color, mileage_km, owner_count, seller_type, seller_name, country_code, state, seller_city, seller_postcode, listing_url, first_seen_at, last_seen_at, last_collected_at, source_updated_at, active, notes, created_at, updated_at`; PK: `marketplace_listing_id`; FK: `data_source_id → data_sources.data_source_id`, `vehicle_id → vehicles.vehicle_id`, `vehicle_variant_id → vehicle_variants.vehicle_variant_id`.
- `marketplace_price_history` (786 rows) — fields: `marketplace_price_history_id, marketplace_listing_id, price_amount, currency, observed_at, collected_at, source_updated_at, listing_url, notes, created_at`; PK: `marketplace_price_history_id`; FK: `marketplace_listing_id → marketplace_listings.marketplace_listing_id`.
- `official_price_observations` (0 rows) — fields: `official_price_observation_id, vehicle_variant_id, data_source_id, collection_batch_id, official_price, currency, price_includes_vat, valid_date, effective_from, effective_to, observed_at, collected_at, source_url, source_record_id, raw_brand, raw_model, raw_variant_name, data_quality_status, validation_status, notes, created_at, updated_at`; PK: `official_price_observation_id`; FK: `vehicle_variant_id → vehicle_variants.vehicle_variant_id`, `data_source_id → data_sources.data_source_id`, `collection_batch_id → collection_batches.collection_batch_id`.
- `registration_observations` (0 rows) — fields: `registration_observation_id, data_source_id, brand_id, vehicle_id, vehicle_variant_id, canonical_brand, canonical_model, raw_brand, raw_model, registration_count, fuel_type, market_share, sales_value, sales_metric_type, registration_period, registration_scope, region, country_code, state, valid_date, observed_at, collected_at, source_url, source_record_id, source_file_name, source_page_number, data_quality_status, validation_status, notes, created_at, updated_at`; PK: `registration_observation_id`; FK: `data_source_id → data_sources.data_source_id`, `brand_id → brands.brand_id`, `vehicle_id → vehicles.vehicle_id`, `vehicle_variant_id → vehicle_variants.vehicle_variant_id`.
- `vehicle_aliases` (81 rows) — fields: `vehicle_alias_id, vehicle_id, alias_text, normalized_alias, alias_language, alias_type, created_at`; PK: `vehicle_alias_id`; FK: `vehicle_id → vehicles.vehicle_id`.
- `vehicle_variants` (0 rows) — fields: `vehicle_variant_id, vehicle_id, model_year, generation, trim_name, variant_name, edition_name, drivetrain, transmission, powertrain, fuel_type, battery_capacity_kwh, engine_power_kw, engine_power_ps, effective_from, effective_to, active, created_at, updated_at`; PK: `vehicle_variant_id`; FK: `vehicle_id → vehicles.vehicle_id`.
- `vehicles` (21 rows) — fields: `vehicle_id, brand_id, canonical_model, chinese_model, vehicle_segment, body_type, default_powertrain, priority_level, active, created_at, updated_at`; PK: `vehicle_id`; FK: `brand_id → brands.brand_id`.

## 5. Existing Reports

- Marketplace Export: `exports/project_germania_marketplace.xlsx`
- Quality Report: `exports/project_germania_quality_report.xlsx`
- Market Monitor: `exports/market_monitor_report.xlsx`

## 6. Phase 17 Rules

Dashboard code may only read existing data.

Do not modify ORM, SQLite schema, Alembic, collection, scraper, or parser code.

Suggested technologies: Streamlit, Plotly, AG Grid, and SQLite. These are suggestions, not confirmation that the packages are installed.

## 7. Existing Dependencies

Dependency file: `pyproject.toml`.

Potentially relevant existing runtime dependencies:

- `SQLAlchemy>=2.0` — database access.
- `openpyxl>=3.1` — existing Excel report generation/reading.

`Streamlit`, `Plotly`, and AG Grid are not declared in the checked dependency file. No dependencies were installed during handover.

## 8. Basic Run Information

Existing documented entry points include:

```powershell
python scripts/show_database_summary.py --database-url $env:GERMANIA_DATABASE_URL
python scripts/show_vehicle.py --brand Volkswagen --model Golf --database-url $env:GERMANIA_DATABASE_URL
python scripts/export_marketplace.py --database-url $env:GERMANIA_DATABASE_URL --output-dir exports
python scripts/data_quality_report.py --database-url $env:GERMANIA_DATABASE_URL --output-dir exports
python scripts/market_monitor.py --database-url $env:GERMANIA_DATABASE_URL --cutoff 2026-07-19T03:02:00Z --output-dir exports
```

Collection entry points also exist under `scripts/`, but Phase 17 Dashboard work must not invoke them.
