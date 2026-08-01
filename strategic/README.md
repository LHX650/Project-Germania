# Project Germania Strategic Intelligence

Phase 7 is an independent, read-only strategic layer over existing artifacts:

- `reports/daily_market_intelligence.json`
- `reports/daily_ai_market_report.md`
- source-attributed KBA, RSS/news, and official brand-news signals

It does not change collector, scheduler, database, Analytics, Pipeline, or
Dashboard modules. The CLI loads the public-source configuration from
`config/external_intelligence.yaml`; each provider failure is isolated and the
previous strategic report is preserved until a complete replacement is ready.

## Generate the management report

```powershell
.\.venv\Scripts\python.exe -m strategic
```

The command writes `reports/external_intelligence.json` and
`reports/strategic_market_report.md` atomically. Invalid or inconsistent
upstream input leaves any previous valid strategic report untouched. For a
deliberately offline Analytics/AI-only run:

```powershell
.\.venv\Scripts\python.exe -m strategic --no-external
```

## External provider interfaces

Implement one or more protocols from `strategic.external`:

- `KBADataProvider.fetch_registrations()`
- `NewsDataProvider.fetch_news()`
- `BrandNewsDataProvider.fetch_brand_news()`
- `ExternalMarketDataProvider.fetch_market_data()`

Each available snapshot must include source-attributed signals with a stable ID, title, summary, observation date, implication, and source URL. Provider failure is isolated and displayed as a data gap.

The default provider implementation lives in `external_intelligence/`. It
uses no paid API or credentials, applies bounded timeouts and payload limits,
prefers RSS/Atom discovery, falls back to dated JSON-LD `NewsArticle` objects,
and caches raw responses under `data/cache/external_intelligence/` with TTL,
ETag/Last-Modified revalidation, source metadata, and explicit stale fallback.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest strategic\tests
.\.venv\Scripts\python.exe -m ruff check strategic
.\.venv\Scripts\python.exe -m black --check strategic
```
