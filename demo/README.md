# Project Germania public demo data

This directory contains the public, synthetic, anonymized, read-only data bundle
for Project Germania V2.0.

The vehicle and brand names are public market labels. All listing IDs, sellers,
locations, observations, asking prices, inventory counts, scores, summaries,
pipeline identifiers, and derived trends in this directory are synthetic demo
values. They must not be interpreted as current market facts, sales, transaction
prices, or production collection output.

The external content cards use a small set of public official URLs so link and
video rendering can be demonstrated. Only metadata and short original summaries
are bundled; no full article text is copied.

## Contents

```text
project_germania_demo.sqlite3
daily_market_intelligence.json
daily_ai_market_report.md
external_intelligence.json
content_feed.json
strategic_market_report.md
pipeline_status.json
```

The SQLite file uses the existing Project Germania SQLAlchemy metadata. The
builder creates a separate database and never opens, copies, or modifies the
production database.

## Run the demo

PowerShell:

```powershell
$env:DEMO_MODE = "true"
streamlit run dashboard/app.py
```

Bash:

```bash
DEMO_MODE=true streamlit run dashboard/app.py
```

Unset `DEMO_MODE` or set it to `false` to restore the default Production Mode.

## Rebuild

```powershell
$env:PYTHONPATH = "src"
python demo/build_demo_data.py
```

Rebuilding only replaces files inside this `demo/` directory.
