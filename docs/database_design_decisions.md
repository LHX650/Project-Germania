# Database Design Decisions

Phase 4 decision log for Project Germania. This file records database design
decisions only. It does not create a database, SQLAlchemy model, Alembic
migration, SQL file, collector, or dashboard.

## Decision 1: Do Not Use One Wide `cars` Table

- **Decision**: Do not use a single wide table for all vehicle, listing, price,
  registration, FX, and quality fields.
- **Context**: The project must preserve source traceability, price history,
  registration periods, listing lifecycle, and derived estimates.
- **Options considered**: One large table; normalized relational tables.
- **Chosen approach**: Use separate reference, observation, analytics, and
  quality tables.
- **Consequences**: Joins are required, but field meaning, constraints, and
  historical records remain clear and auditable.

## Decision 2: Split Listings From Listing Observations

- **Decision**: Store stable listing identity in `marketplace_listings` and
  time-varying price/status history in `marketplace_listing_observations`.
- **Context**: The same AutoScout24 or Mobile.de listing can change price,
  mileage, status, or availability over time.
- **Options considered**: Store current listing only; overwrite listing rows;
  separate identity and observation tables.
- **Chosen approach**: Separate identity and observation history.
- **Consequences**: Historical price changes are preserved and not overwritten.
  Queries for current inventory need both tables.

## Decision 3: Store Official Prices Separately

- **Decision**: Use `official_price_observations` for manufacturer official
  price records.
- **Context**: Official prices have different sources, validity dates, and
  meanings from marketplace asking prices.
- **Options considered**: Store official and marketplace prices in one generic
  price table; store official prices separately.
- **Chosen approach**: Separate official price table.
- **Consequences**: Price semantics remain clear. Cross-price analysis must join
  official and marketplace records explicitly.

## Decision 4: Do Not Store Registration Counts In `vehicles`

- **Decision**: Store registrations in `registration_observations`, not in
  `vehicles`.
- **Context**: Registration counts vary by source, period, geography, and
  metric type.
- **Options considered**: Add current registration count to `vehicles`; use a
  historical observation table.
- **Chosen approach**: Use a registration observation table.
- **Consequences**: Time-series analysis is possible, and KBA new registrations
  remain separate from retail sales, wholesale sales, and deliveries.

## Decision 5: Store Exchange Rates Separately

- **Decision**: Use `exchange_rate_observations` for FX rates.
- **Context**: Historical price conversion must use the rate for the relevant
  date and currency pair.
- **Options considered**: Store exchange rate directly on every price row; store
  authoritative FX observations separately.
- **Chosen approach**: Separate FX observation table.
- **Consequences**: Conversion is traceable and reusable. If converted prices
  are materialized later, they must reference the exact FX observation used.

## Decision 6: Estimated Transaction Price Is Not Confirmed Transaction Price

- **Decision**: Store estimates in `estimated_transaction_prices`, not in a
  table named `transactions`.
- **Context**: Marketplace listing prices are asking prices, and Project
  Germania has no confirmed transaction-price source yet.
- **Options considered**: Store estimates as transactions; store estimates in a
  dedicated derived table; omit estimates entirely.
- **Chosen approach**: Dedicated estimate table with method, version,
  confidence, and input reference.
- **Consequences**: Analysis can use estimates without confusing them with
  observed truth. A future confirmed transaction table requires a reliable
  source and separate design.

## Decision 7: Store Aliases In A Separate Table

- **Decision**: Use `vehicle_aliases` instead of comma-separated alias strings.
- **Context**: Alias matching must avoid unsafe close-model merges such as
  `ID.4` versus `ID.5`, `Seal U` versus `Seal`, and `BMW iX1` versus `BMW X1`.
- **Options considered**: Comma-separated strings in `vehicles`; JSON arrays;
  normalized alias table.
- **Chosen approach**: Normalized alias table with `normalized_alias`
  uniqueness.
- **Consequences**: Matching is auditable and conflicts are preventable. Alias
  maintenance requires additional rows.

## Decision 8: Start With SQLite But Preserve PostgreSQL Compatibility

- **Decision**: Design for SQLite local development while keeping PostgreSQL
  migration feasible.
- **Context**: Early development benefits from simple local setup. Production is
  expected to use PostgreSQL later.
- **Options considered**: PostgreSQL only; SQLite only; compatible relational
  subset.
- **Chosen approach**: Portable schema concepts: integer identity keys,
  normalized association tables, CHECK constraints, and no SQLite-only business
  logic.
- **Consequences**: Some advanced PostgreSQL features, such as native ENUMs and
  partial unique indexes, are deferred until implementation needs them.

## Decision 9: Prefer Soft Delete / `active` For Master Data

- **Decision**: Use `active` flags for sources, brands, vehicles, variants, and
  listings where appropriate.
- **Context**: Historical records must not disappear because a source or vehicle
  is no longer active.
- **Options considered**: Physical delete; soft-disable with `active`; separate
  archive tables.
- **Chosen approach**: Soft-disable master data and listing identities. Use
  physical deletes only for tightly dependent association rows such as source
  categories or aliases.
- **Consequences**: Queries must filter active records when needed, but audit
  history remains safer.

## Decision 10: Do Not Create `confirmed_transactions` In Phase 4

- **Decision**: Do not include a `confirmed_transactions` table in the current
  ER design.
- **Context**: No reliable confirmed transaction source has been identified.
  Listing prices and estimates must not be treated as real transaction prices.
- **Options considered**: Create a placeholder confirmed transactions table;
  defer it until a reliable source exists.
- **Chosen approach**: Defer confirmed transaction storage.
- **Consequences**: The design avoids a misleading empty or speculative table.
  If a reliable source appears later, confirmed transactions should be designed
  separately with strict provenance and legal/compliance review.
