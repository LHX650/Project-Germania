# Streamlit Community Cloud deployment

This checklist prepares the public Project Germania V2.0 demo without exposing
or invoking the production data workflow.

## Application settings

| Setting | Value |
| --- | --- |
| Repository | `LHX650/Project-Germania` |
| Branch | `develop-v2-intelligence` |
| Main file path | `dashboard/app.py` |
| Python | 3.12 |

Streamlit Community Cloud installs the root `requirements.txt`, which delegates
to `dashboard/requirements.txt`.

## Demo configuration

Add the following root-level value in the Streamlit secrets editor:

```toml
DEMO_MODE = "true"
```

Root-level Streamlit secrets are exposed to the app as environment variables.
Do not add a production database URL, marketplace credentials, raw-data path,
or API key to the public demo.

## Data boundary

With `DEMO_MODE=true`, Dashboard services resolve only these committed files:

```text
demo/project_germania_demo.sqlite3
demo/daily_market_intelligence.json
demo/daily_ai_market_report.md
demo/external_intelligence.json
demo/content_feed.json
demo/strategic_market_report.md
demo/pipeline_status.json
```

The Dashboard opens SQLite with `mode=ro` and `PRAGMA query_only=ON`. It does not
call the Collector, Scheduler, Pipeline, Analytics, AI, Strategic, or external
provider modules.

## Pre-deployment validation

```powershell
pip install -r dashboard/requirements.txt
$env:DEMO_MODE = "true"
pytest dashboard/tests/test_demo_mode.py -q
streamlit run dashboard/app.py
```

Confirm all eight navigation pages render, the Demo Mode disclosure is visible,
Search Center only returns `DEMO-` listing IDs, official external links open in a
new tab, and no production report or database path appears in the frontend.

## Production deployment

Production remains the default when `DEMO_MODE` is unset or `false`. A production
deployment requires the governed Pipeline to create the real SQLite and report
artifacts outside this public demo workflow.
