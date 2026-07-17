# Project Germania Architecture Review

Phase 3.5 review date: 2026-07-18

This review covers configuration, data dictionary, logical data model, naming
conventions, configuration loaders, tests, and README project status. It does
not create database tables, SQLAlchemy models, Alembic migrations, collectors,
crawlers, dashboard code, network connections, API calls, or market data.

## 1. Review范围

Reviewed files:

- `config/vehicles.yaml`
- `config/sources.yaml`
- `src/germania/config/vehicles.py`
- `src/germania/config/vehicle_normalization.py`
- `src/germania/config/sources.py`
- `docs/data_dictionary.md`
- `docs/data_model.md`
- `docs/naming_conventions.md`
- `README.md`
- `README_CN.md`
- `tests/unit/test_vehicle_config.py`
- `tests/unit/test_source_config.py`

Review focus:

- configuration completeness and safe naming;
- alias collision and close-model mismatch risk;
- source category, authority, and collection-method consistency;
- field coverage for region, source, vehicle, version, registration, price,
  currency, date/time, quality, raw traceability, and notes;
- logical entity responsibility and relationship clarity;
- code validation rules versus documented rules;
- readiness for the next database design phase.

## 2. Review结论

The current architecture is consistent enough to proceed to database ER design
after this review. No Critical or High issues were found.

The review confirmed that Project Germania still has no database
implementation, no ORM model, no Alembic migration, no collector, no crawler, no
dashboard, no real website connection, and no real German automotive market
data. The current project state remains configuration and logical design only.

## 3. 已确认正确的设计

- `config/vehicles.yaml` contains 15 research vehicles with stable canonical
  brand and model names.
- Vehicle aliases are exact alias inputs for normalization; no fuzzy matching
  was introduced.
- The protected close-model cases remain separated: `ID.4` is not `ID.5`,
  `Seal U` is not `Seal`, `BMW iX1` is not `BMW X1`, `Model Y` is not
  `Model 3`, and `MG4` is not another MG model.
- `config/sources.yaml` contains 12 planned sources and does not claim any live
  integration.
- KBA remains the preferred source for German registration counts.
- Marketplace listing prices remain clearly separated from confirmed
  transaction prices.
- `estimated_transaction_price` remains a derived analytics field that requires
  input traceability and a method.
- Date and timestamp field names follow `_date` and `_at` rules.
- `registration_count` is documented as a new-registration proxy, not company
  revenue, wholesale sales, retail sales, or deliveries.
- `source_country` was not added because `country_code` already covers the
  current requirement.
- `schema_version` is treated as configuration or data-contract metadata, not as
  a per-record vehicle market field.

## 4. 发现的问题

| issue_id | severity | affected_file | description | impact | recommended_action | resolution_status |
| --- | --- | --- | --- | --- | --- | --- |
| AR-001 | Medium | `config/sources.yaml` | ACEA was configured only with `market_statistics`, while the review requirement expects ACEA to support market statistics and registration context. | Source categories could understate ACEA's intended supporting role. | Add `registrations` while keeping notes clear that ACEA does not replace KBA model-level German data. | fixed |
| AR-002 | Medium | `src/germania/config/vehicles.py`, `tests/unit/test_vehicle_config.py` | Vehicle loader required fields but did not validate `priority_level`, `powertrain`, empty aliases, duplicate aliases, or cross-vehicle alias conflicts. | Invalid configuration could pass loading and later create unsafe matching behavior. | Add explicit enum and alias validation plus unit tests. | fixed |
| AR-003 | Medium | `docs/data_dictionary.md`, `docs/data_model.md` | Several logical model support fields, including entity identifiers, data-source planning fields, Chinese display names, aliases, and estimation-method fields, were used by the logical model but not listed in the data dictionary. | Database design would need to infer meanings later, increasing implementation risk. | Add logical support fields to the data dictionary and clarify they do not create database tables. | fixed |
| AR-004 | Low | `docs/data_model.md` | Marketplace listing history was represented as a self-relation without enough explanatory text. | The database phase could confuse listing identity with dated observations. | Clarify that the physical model may split listing identity and history later. | fixed |
| AR-005 | Low | `README.md`, `README_CN.md` | The project roadmap and status did not include Phase 3.5 or the architecture review document. | GitHub readers could miss the current architecture gate before database work. | Add Phase 3.5 completion and `docs/architecture_review.md` to both READMEs. | fixed |
| AR-006 | Informational | `docs/data_dictionary.md` | The review considered whether `source_country` or per-record `schema_version` should be added. | Adding them now would duplicate `country_code` or mix metadata with business fields. | Keep `country_code`; document `schema_version` as metadata only. | accepted |

## 5. 问题严重等级

- Critical: 0
- High: 0
- Medium: 3
- Low: 2
- Informational: 1

There are no Critical or High issues in the reviewed architecture.

## 6. 已修复的问题

- AR-001: ACEA now includes both `registrations` and `market_statistics` as
  intended planning categories.
- AR-002: Vehicle configuration validation now checks priority, powertrain,
  empty aliases, duplicate aliases, canonical duplicates, and unsafe alias
  collisions.
- AR-003: The data dictionary now includes logical support fields used by the
  configuration and data model.
- AR-004: The logical data model now clarifies marketplace listing history.
- AR-005: Both README files now show Phase 3.5 and reference this review.

## 7. 暂不修复的问题

- AR-006 is accepted as a design decision. `source_country` is not introduced,
  and `schema_version` remains metadata rather than a business field.
- No deferred Critical, High, Medium, or Low issues remain from this review.

## 8. 数据库阶段前置条件

Before database implementation starts:

- keep KBA registrations separate from other sales metrics;
- keep `official_price`, `listed_price`, `estimated_transaction_price`, and
  `transaction_price` separate;
- decide whether MarketplaceListing should be physically split into listing
  identity and listing observation history;
- map all database columns back to `docs/data_dictionary.md`;
- define SQLAlchemy and Alembic only in the database phase;
- preserve raw source fields and traceability metadata;
- keep network collection, Playwright, and dashboard work out of database ER
  design.

## 9. 最终建议

The project is ready for the next phase only as database ER design. The next
phase should stay at the design level first, map every proposed table and column
to the data dictionary, and avoid implementing collectors, Playwright,
Dashboards, real source connections, or real market data ingestion.
