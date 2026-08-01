# Phase 12 comparable vehicle benchmarking

## Data boundary

Peer groups are recalculated in memory from two existing, read-only sources:

- `reports/daily_market_intelligence.json`: asking price, active inventory,
  price trend, Opportunity Score, and Phase 11 scores;
- SQLite `vehicles` and `brands`: `vehicle_segment`, `body_type`,
  `default_powertrain`, and `country_of_origin` disclosure.

`country_of_origin` is displayed as a market attribute but is not treated as a
brand-positioning proxy. No vehicle names, competitor lists, segments, or
powertrains are hard-coded into peer membership.

## Staged peer matching

The target vehicle is excluded from its peer-only median. At least two peers
are required. Rules stop at the first level that reaches this minimum:

| Level | Asking-price distance | Segment control | Powertrain control |
|---:|---:|---|---|
| 1 | <= 20% | Exact `vehicle_segment` | Exact |
| 2 | <= 35% | Exact `vehicle_segment` | Exact |
| 3 | <= 20% | Similar segment family | Exact |
| 4 | <= 35% | Similar segment family | Exact |
| 5 | <= 50% | Similar segment family | Exact |
| 6 | <= 35% | Same `body_type` | Exact |
| 7 | <= 50% | Same `body_type` | Exact |
| 8 | <= 35% | Similar segment family | Relaxed |
| 9 | <= 50% | Same `body_type` | Relaxed |

Segment family is derived from the existing taxonomy text by lower-casing and
removing only `electric`, `battery`, and `ev`. This distinguishes an exact
match from a broader taxonomy-family match without mapping individual models.

Missing average asking price, segment, or powertrain returns
`insufficient_data`. A result also remains insufficient when fewer than two
peers are available after level 9.

## Benchmark formulas

For a target value `T` and the median of valid peer-only values `M`:

- Price Gap % = `(T asking price - M asking price) / |M asking price| * 100`;
- Inventory Gap % = `(T active listings - M active listings) / |M active listings| * 100`;
- Price Trend Gap = `T 7-day asking-price change - M 7-day asking-price change`;
- Opportunity Score Gap = `T Opportunity Score - M Opportunity Score`;
- Price Pressure Gap = `T Price Pressure - M Price Pressure`;
- Inventory Pressure Gap = `T Inventory Pressure - M Inventory Pressure`;
- Market Momentum Gap = `T Market Momentum - M Market Momentum`.

Percentage denominators of zero return `null`. Missing target values or a peer
group with no valid values for one metric also return `null`; they are never
filled.

Metric ranks are descending raw-value ranks across the target plus valid peers.
The headline Peer Rank uses Opportunity Score descending:

```text
rank = 1 + count(group value > target value)
percentile = 100 * (group size - rank) / (group size - 1)
```

The top rank is percentile 100 and the bottom rank is percentile 0.

## Interpretation

Advantages and disadvantages require a material gap:

- asking-price gap: 5%;
- 7-day price-trend gap: 1 percentage point;
- Opportunity, Price Pressure, Inventory Pressure, and Momentum: 5 points.

Lower Price Pressure and Inventory Pressure are favorable; higher Opportunity
and Momentum are favorable. Inventory quantity is shown as neutral market
context rather than demand or sales performance.

These are Project Germania marketplace benchmarks. Active listing inventory is
not sales, and asking price is not transaction price.

## Automatic refresh

The Analytics JSON cache is keyed by file `mtime` and size. SQLite control
metadata is independently keyed by database `mtime` and size. Every newly
loaded daily report recomputes peer membership, medians, gaps, ranks, and
percentiles without modifying the pipeline or either data source.
