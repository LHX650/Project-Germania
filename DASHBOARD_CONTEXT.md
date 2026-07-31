# Dashboard Context

Phase 16 is complete. The checked live SQLite database contains the real Phase 14–16 marketplace dataset.

- Original SQLite location: `C:\Users\卢虹先\.codex\visualizations\2026\07\18\019f76b5-fb74-79c3-af2d-36de38efc7ec\phase_14_5b\project_germania_live.sqlite3`
- Handover-package location: `phase17_input/database/project_germania_live.sqlite3`
- Current Listings: **786**
- Current Price History: **786**
- Existing Brand Summary: `exports/project_germania_marketplace.xlsx` (`Brand_Summary`)
- Existing Vehicle Summary: `exports/project_germania_marketplace.xlsx` (`Vehicle_Summary`)
- Existing Market Monitor: `exports/market_monitor_report.xlsx`
- Existing Quality Report: `exports/project_germania_quality_report.xlsx`

## Tables and Row Counts

| Table | Rows |
| --- | ---: |
| brands | 11 |
| collection_batches | 0 |
| data_quality_issues | 0 |
| data_source_categories | 21 |
| data_sources | 12 |
| estimated_transaction_prices | 0 |
| exchange_rate_observations | 0 |
| marketplace_listing_observations | 0 |
| marketplace_listings | 786 |
| marketplace_price_history | 786 |
| official_price_observations | 0 |
| registration_observations | 0 |
| vehicle_aliases | 81 |
| vehicle_variants | 0 |
| vehicles | 21 |

The checked totals match the expected 786 Listings / 786 Price History; no difference was found.

## Suggested Dashboard Pages

1. Executive Overview
2. Market Analysis
3. Vehicle Analysis
4. Market Monitor
5. Data Quality
6. Search Center

`services/database.py` must be the future Dashboard's **only database access layer**. Dashboard code must remain read-only and must not modify ORM, SQLite schema, Alembic, collection, scraper, or parser code.
