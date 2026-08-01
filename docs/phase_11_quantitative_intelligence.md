# Phase 11 quantitative intelligence models

Phase 11 adds three Project Germania models derived from the existing daily
Analytics report. They describe marketplace asking-price and listing-inventory
signals only. They are not sales, demand, registration, or transaction-price
models.

All components are normalized to `0–100`. Final scores are rounded to two
decimal places. An unavailable required input produces `score: null` and
`status: insufficient_data`; optional missing components are excluded and the
published weights are renormalized across the remaining components.

## Price Pressure Index

```text
Price Pressure =
  35% × 7-day price decline pressure
+ 15% × 30-day price decline pressure
+ 30% × inventory growth pressure
+ 20% × asking-price dispersion pressure
```

- 7-day decline: `clamp(-price_change_7d_pct / 10 × 100, 0, 100)`.
- 30-day decline: `clamp(-price_change_30d_pct / 15 × 100, 0, 100)`.
- Inventory growth: `clamp(max(change_signal_pct, 0) / 25 × 100, 0, 100)`.
- Price dispersion: `clamp((maximum-minimum)/average × 100, 0, 100)`.

The 7-day price change and at least two other components are required. The
30-day component is optional. Dispersion is cross-sectional asking-price spread,
not historical price volatility or transaction-price volatility.

## Inventory Pressure Index

```text
Inventory Pressure =
  35% × peer-normalized inventory level
+ 30% × inventory growth pressure
+ 20% × new-listing intensity
+ 15% × low market activity
```

- Inventory level is min-max normalized across vehicles in the same report; if
  every vehicle has the same inventory it receives a neutral `50`.
- New-listing intensity is `new_listings_count_7d / current_inventory × 100`,
  clamped to `0–100`.
- Low market activity is `100 - Opportunity Score market_activity component`.

When the Analytics inventory percentage is unavailable, the model uses
`inventory_change_7d_count/current_inventory × 100` and identifies it as a
current-inventory share signal. It is not presented as a historical growth rate.
All four components are required.

## Market Momentum Score

```text
Market Momentum =
  25% × new-listing activity
+ 20% × price opportunity trend
+ 15% × inventory availability trend
+ 30% × existing Opportunity Score
+ 10% × existing market activity
```

- Price opportunity trend is `clamp(50 - 5 × price_change_pct, 0, 100)`.
  When both horizons exist, 7-day and 30-day scores are blended `70/30`.
- Inventory availability trend is
  `clamp(50 + 0.5 × inventory_change_signal_pct, 0, 100)`.
- The existing Opportunity Score and its weights are not modified.

This is buyer-side marketplace opportunity momentum, not sales or demand
momentum. Price trend is optional; the other four components are required.

Bands:

- `80–100`: Strong Positive
- `60–<80`: Positive
- `40–<60`: Neutral
- `20–<40`: Negative
- `0–<20`: Strong Negative

## Automatic refresh

The Dashboard's modification-aware Analytics reader recalculates these models
whenever `reports/daily_market_intelligence.json` changes. No Pipeline,
Scheduler, collector, database schema, database write logic, or vehicle
configuration is changed by Phase 11.
