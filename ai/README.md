# Project Germania AI Market Intelligence

This package converts the validated Phase 5A Analytics JSON into a grounded Markdown market report. It does not read or write the database, call collectors, modify the Scheduler, or require a paid API.

## Local rules report

```powershell
.\.venv\Scripts\python.exe -m ai --input reports\daily_market_intelligence.json --output reports\daily_ai_market_report.md
```

The default mode is deterministic `local_rules`. Optional LLM implementations can implement `ai.providers.LLMProvider`. Provider failures, digest mismatches, missing sections, or unsupported numeric claims automatically fall back to local rules.

## Opt-in three-stage wrapper

The existing production Scheduler remains unchanged. To run the complete sequence manually through a new opt-in entry point:

```powershell
.\.venv\Scripts\python.exe -m ai.automated_pipeline -- --database-path database\project_germania_live.sqlite3
```

The wrapper invokes the existing daily monitor unchanged, preserves its exit code and logs, and generates the AI report only when its structured `analytics_status` is `completed`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest ai\tests
.\.venv\Scripts\python.exe -m ruff check ai
.\.venv\Scripts\python.exe -m black --check ai
```
