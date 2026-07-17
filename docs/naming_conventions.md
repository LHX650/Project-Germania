# Naming Conventions

This document defines naming rules for Project Germania fields, configuration
keys, and future database columns. It does not create database objects.

## General Rules

- Python fields and future database columns must use `snake_case`.
- Standard brand and model names come from `config/vehicles.yaml`.
- Raw source fields must use the `raw_` prefix, such as `raw_brand` and
  `raw_model`.
- Amount fields must use Decimal semantics. Do not use float for prices.
- Date-only fields use the `_date` suffix.
- Timestamp fields use the `_at` suffix.
- Boolean fields use prefixes such as `is_`, `has_`, and `includes_`.
- Count fields use the `_count` suffix.
- Distance fields use the `_km` suffix.
- Amount fields must not hard-code currency in the field name. Use `currency`
  and exchange-rate fields instead.

## Avoid Ambiguous Names

Do not use vague names such as:

- `price`
- `sales`
- `date`
- `type`

Use explicit names instead:

- `official_price`
- `listed_price`
- `registration_count`
- `observed_at`
- `seller_type`

## Source and Raw Data Naming

- Use `source_id` for configured source identifiers.
- Use `source_name` for human-readable source names.
- Use `source_url` for exact page or file origins.
- Use `source_listing_id` for marketplace listing identifiers.
- Use `source_file_name` for downloaded or imported source files.
- Use `raw_file_path` and `raw_payload_reference` to point to immutable raw data.

## Vehicle Naming

- Use `canonical_brand` and `canonical_model` for normalized names.
- Use `raw_brand` and `raw_model` for source text.
- Do not write vehicle names directly into multiple Python modules.
- Do not guess close model matches. For example, `ID.4` is not `ID.5`, `Seal U`
  is not `Seal`, and `BMW iX1` is not `BMW X1`.

## Price Naming

- Use `official_price` for manufacturer list or suggested retail prices.
- Use `listed_price` for marketplace or dealer asking prices.
- Use `estimated_transaction_price` only for model- or rule-derived estimates.
- Use `transaction_price` only for confirmed transaction prices from reliable
  sources.
- Use `price_status` to identify whether a price is official, listed,
  estimated, confirmed transaction, or unknown.

## Sales and Registration Naming

- Use `registration_count` for KBA or other authoritative new-registration
  counts.
- Use `sales_metric_type` to identify the metric basis.
- Use `sales_value` only when the source provides a sales metric that cannot be
  directly represented by `registration_count`.
- Do not mix registrations, deliveries, retail sales, and wholesale sales
  without explicit methodology.
