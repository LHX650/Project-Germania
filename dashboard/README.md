# Project Germania Dashboard

The Dashboard uses an English-only interface for the international V2 demo,
GitHub showcase, and interview presentation. Navigation, page copy, metrics,
filters, charts, tables, alerts, empty states, and validation messages are
presented in professional automotive market-intelligence terminology. Dynamic
source content retains its original language and evidence metadata.

Phase 16 extends the established information architecture with a ninth,
read-only Market Alerts page. It evaluates transparent threshold rules over the
existing Price Pressure, Inventory Pressure, Market Momentum, Opportunity Score,
and Peer Benchmark outputs without creating another scoring model. Analytics,
AI, Pipeline, external content, and SQLite data remain read-only and dynamically
loaded from their existing artifacts.

Phase 18C embeds an **Executive Intelligence Brief** in Executive Overview. It
shows Today's Brief, risk and opportunity summaries, generation provenance, and
separately expandable Internal Market Evidence and External Market Signals. The
Dashboard writes neither the Brief artifact nor the SQLite database.

Phase 18D makes that Brief a daily Pipeline artifact. Executive Overview reads
`daily_executive_intelligence_brief.md` with mtime/size cache invalidation. If a
new Brief cannot be generated, the page keeps rendering the last valid artifact
and displays its report date alongside the current Analytics date. Demo Mode
remains compatible when no bundled Brief exists by using the existing read-only
local generation fallback.

## 1. Create and activate a virtual environment

Run these commands from the project root.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS or Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

## 2. Install the existing project dependencies

The complete repository documentation identifies `pyproject.toml` as the dependency manifest and documents this command:

```powershell
python -m pip install -e ".[dev]"
```

The supplied Phase 17 handover archive does **not** contain `pyproject.toml` or a requirements file, although the handover refers to one. Do not run the editable-install command in this reduced archive; first restore the matching `pyproject.toml` from the complete project repository.

Streamlit is not currently declared in the root package metadata. Install the Dashboard-only runtime dependency without changing the project package:

```powershell
.\.venv\Scripts\python.exe -m pip install -r dashboard\requirements.txt
```

Generate the Phase 5A report before starting the Dashboard:

```powershell
.\.venv\Scripts\python.exe -m germania.analytics --database-path database\project_germania_live.sqlite3 --output reports\daily_market_intelligence.json
```

Generate the Phase 6 AI report:

```powershell
.\.venv\Scripts\python.exe -m ai --input reports\daily_market_intelligence.json --output reports\daily_ai_market_report.md
```

## 3. Run the dashboard

From the project root, use the single supported entry point:

```powershell
streamlit run dashboard/app.py
```

## 4. Phase 16 information architecture

The visible navigation contains:

- **Executive**: Executive Overview;
- **Market Intelligence**: Global Automotive Intelligence Hub, Market Alerts,
  Vehicle Intelligence, Brand Competition, and Price Intelligence;
- **Deep Analysis**: Vehicle Analysis and Search Center;
- **Platform**: Data Quality.

The pages provide:

- Executive Overview with dynamic market KPIs, report-date new listings,
  price and inventory trends, pipeline stages, AI summary, opportunities,
  risks, key vehicles, and the complete AI report;
- Market Alerts with Critical, Warning, Normal, and `insufficient_data` rule
  evaluations, alert ranking, vehicle risk ranking, and archive-backed trends;
- Vehicle Intelligence with filters and transparent opportunity scoring;
- Brand Competition inventory, electrification, and coverage metrics;
- Price Intelligence with dynamic price positioning and trend availability;
- Vehicle Analysis with current metrics, price and inventory history,
  price/mileage/registration distributions, opportunity scoring, and related
  verified news or reports;
- Search Center with parameterized Listing query and CSV download;
- Data Quality with pipeline, collection task, matching, completeness, database
  volume, external-source status, and a read-only Daily Data Update Summary;
- URI-enforced read-only SQLite access with query-only protection.

AI Market Insights, Market Monitor, and Market Analysis remain in source and in
the internal renderer registry as fallback routes, but are hidden from the
visible navigation because their capabilities are consolidated into the core
pages.

Phase 10 performs no database writes, schema changes, migrations, collector
activity, scheduler activity, Pipeline changes, Analytics changes, or
simulated-data generation. JSON and Markdown readers refresh when their file
mtime/size signature changes. Listing counts are not sales, and asking prices
are not transaction prices.

Market Alerts reads the current and archived Analytics JSON plus existing
read-only SQLite peer controls. Missing historical or peer evidence is reported
as `insufficient_data`; the Dashboard does not fabricate prior observations.

## Phase 17 integrated AI Automotive Intelligence Agent

The AI Agent is embedded in the existing information architecture rather than
added as a separate top-level page:

- Executive Overview provides an AI Daily Market Brief with Top Market Changes,
  Main Risks, Opportunities, and a free-question analyst entry;
- Vehicle Analysis provides on-demand Strength, Risk, Peer Comparison, and
  Market Position evidence for the selected vehicle;
- Market Alerts provides an on-demand explanation of the selected Critical or
  Warning rule evaluation, including why it triggered, its related metrics, and
  its potential competitive implication.

Retrieval combines the current Analytics artifact, existing Market Alerts,
controlled Peer Benchmark, and read-only SQLite price/inventory history. The
external provider searches only the validated content Feed by default. Every
answer discloses its generation mode, provider, confidence, and evidence digest.
An unavailable optional provider falls back to local evidence rules. No API key
is required, and no Dashboard path writes to SQLite or generated artifacts.

Phase 17 Finalization adds a structured Evidence Panel to every AI output. The
panel shows Evidence Source, Metric Name, Value, Timestamp, and Vehicle so each
claim can be traced to Analytics, Quantitative Intelligence, Peer Benchmark,
Market Alerts, SQLite history, or an attributed external source. Empty evidence
is displayed as `insufficient_data`.

The Executive analyst offers dynamic Suggested Questions based on vehicles in
the current report. Vehicle Analysis uses a fixed Market Position, Competitive
Strength, Key Risks, Peer Comparison, and Recommended Monitoring structure.
Market Alerts uses Alert Reason, Supporting Evidence, Competitive Impact, and
Recommended Action. These additions do not create a new navigation page.

Phase 18A adds a provider-neutral external-evidence adapter to the same AI
retrieval path. The Global Automotive Intelligence Hub now summarizes the
existing validated Feed as External News Feed, Brand Updates, and Industry
Signals above the unchanged filters and content-card grid. Empty groups and
empty AI retrieval results display `insufficient_data`. The grouping uses only
the Feed's source metadata and does not infer that an external event caused an
internal market signal.

Phase 18B upgrades the existing Hub with Latest Automotive News, Policy Updates,
Brand Intelligence, and Industry Signals. Each item displays Source, Date,
Category, and a configured source-reliability score. Production Mode combines
the last validated Content Feed with recent live public-source metadata; Demo
Mode remains fully static and makes no network request. Live results use a
15-minute bounded Streamlit cache, while the source layer retains its atomic TTL
cache and stale-on-error behavior. The manual refresh action safely clears both
Dashboard caches.

## Phase 8C content center

`Global Automotive Intelligence Hub` reads only
`reports/external_intelligence/content_feed.json`. It presents attributed News,
Report, and Video metadata, supports compound filters and internal detail views,
and invalidates its cache whenever the Feed file mtime/size signature changes.
The page also provides a safe manual refresh button. External links are taken
from the generated artifact; YouTube content is embedded only when a validated
public video ID is present. Market metrics are shown only for an unambiguous
vehicle match to `daily_market_intelligence.json`.

Generate the independent content Feed after the four intelligence artifacts:

```powershell
.\.venv\Scripts\python.exe -m external_intelligence.content_feed
```

## 5. Tests

```powershell
.\.venv\Scripts\python.exe -m pytest dashboard\tests
.\.venv\Scripts\python.exe -m ruff check dashboard
.\.venv\Scripts\python.exe -m black --check dashboard
```

## 6. Phase 11 quantitative models

The Dashboard calculates these models from each newly loaded
`daily_market_intelligence.json` without changing the existing Opportunity
Score:

- Price Pressure Index (`0–100`);
- Inventory Pressure Index (`0–100`);
- Market Momentum Score (`0–100`) with five deterministic bands.

The formulas, weights, normalization thresholds, input-source rules, and
missing-data behavior are documented in
`docs/phase_11_quantitative_intelligence.md`. Scores are Project Germania
marketplace indicators: listing counts are not sales, asking prices are not
transaction prices, and Momentum is not a demand estimate.

## 7. Phase 12 comparable vehicle benchmarking

Vehicle Analysis now provides a dynamic Peer Comparison with verified SQLite
segment, body-type, and powertrain controls. Vehicle Intelligence, Brand
Competition, and Price Intelligence also expose peer-relative tables and
charts before broad market comparisons.

Peer membership starts with a 20% asking-price range, exact segment, and exact
powertrain. It follows declared relaxation levels only when fewer than two
peers are available. Every page discloses the selected level, matching basis,
sample size, peer-only median, gaps, Opportunity-based rank, and percentile.
Missing controls or an undersized group display `insufficient_data`.

The complete formulas and staged matching rules are documented in
`docs/phase_12_comparable_vehicle_benchmarking.md`. The implementation reads
SQLite and generated reports only; it does not modify the database, vehicle
configuration, Analytics formulas, Pipeline, or collection workflow.

## 8. Phase 15A daily update monitoring

Data Quality reads the latest collection run, listing observations, and asking-
price history directly from the active read-only SQLite path. It displays
Listings Scanned, New Listings, Existing Listings Updated, Price Changes and
direction, Inactive / Removed Listings, New Price History Records, Vehicles
Updated, Pipeline Status, Last Successful Collection, and Pipeline Duration.

The 7-day and 30-day views plot daily New, Updated, Price Changed, and Inactive
listing events. `DEMO_MODE=true` resolves the same queries against the bundled
Demo database; Production Mode uses the live database. The service cache is
invalidated by database mtime and size. Missing evidence is shown as
`Insufficient data`; calendar gaps are not filled with synthetic values.

These are marketplace collection and listing-maintenance metrics. Listing
activity is not vehicle sales, and asking-price changes are not transaction-
price changes. This feature performs no database writes and does not invoke or
modify the Collector, Scheduler, Pipeline, Analytics, AI, or Strategic layers.
