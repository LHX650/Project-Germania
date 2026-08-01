# Project Germania Intelligence Pipeline

The production orchestration entry point runs:

```text
daily_market_monitor.py (Collection -> Analytics)
    -> AI Report
    -> External Intelligence
    -> Content Feed
    -> Strategic Report
```

The existing daily monitor remains the owner of Collection and Analytics. The
orchestration layer delegates to it without importing or changing collector,
parser, matching, import, database-write, or analytics-calculation logic.

## Run

Pass existing daily-monitor arguments after `--`:

```powershell
.\.venv\Scripts\python.exe -m pipeline -- --database-path database\project_germania_live.sqlite3
```

Outputs:

- `reports/daily_market_intelligence.json`
- `reports/daily_ai_market_report.md`
- `reports/external_intelligence.json`
- `reports/external_intelligence/content_feed.json`
- `reports/strategic_market_report.md`
- `reports/pipeline_status.json`
- prior versions under `reports/archive/{pipeline_id}/`

The status file is atomically rewritten after every orchestration boundary and
records each stage's status, timestamp, and error. Downstream stages are skipped
after an unusable upstream failure. A partially available external evidence set
continues through Content Feed and Strategic reporting while retaining its
`partially_completed` status. Every existing artifact and the previous status
are archived before collection begins; stage writers replace outputs atomically.

External providers use public sources and their governed stale cache. They do
not disable TLS verification or synthesize unavailable evidence.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest pipeline\tests
.\.venv\Scripts\python.exe -m ruff check pipeline
.\.venv\Scripts\python.exe -m black --check pipeline
```
