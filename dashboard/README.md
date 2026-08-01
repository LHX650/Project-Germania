# Project Germania Dashboard

The Dashboard uses an English-only interface for the international V2 demo,
GitHub showcase, and interview presentation. Navigation, page copy, metrics,
filters, charts, tables, alerts, empty states, and validation messages are
presented in professional automotive market-intelligence terminology. Dynamic
source content retains its original language and evidence metadata.

Phase 11 keeps the Phase 10 eight-page information architecture and upgrades it
with a shared enterprise visual system plus three explainable quantitative
marketplace models. Analytics, AI, Pipeline, external content, and SQLite data
remain read-only and dynamically loaded from their existing artifacts.

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

## 4. Phase 10 information architecture

The visible navigation contains:

- **Executive**: Executive Overview;
- **Market Intelligence**: Global Automotive Intelligence Hub, Vehicle
  Intelligence, Brand Competition, and Price Intelligence;
- **Deep Analysis**: Vehicle Analysis and Search Center;
- **Platform**: Data Quality.

The pages provide:

- Executive Overview with dynamic market KPIs, report-date new listings,
  price and inventory trends, pipeline stages, AI summary, opportunities,
  risks, key vehicles, and the complete AI report;
- Vehicle Intelligence with filters and transparent opportunity scoring;
- Brand Competition inventory, electrification, and coverage metrics;
- Price Intelligence with dynamic price positioning and trend availability;
- Vehicle Analysis with current metrics, price and inventory history,
  price/mileage/registration distributions, opportunity scoring, and related
  verified news or reports;
- Search Center with parameterized Listing query and CSV download;
- Data Quality with pipeline, collection task, matching, completeness, database
  volume, and external-source status;
- URI-enforced read-only SQLite access with query-only protection.

AI Market Insights, Market Monitor, and Market Analysis remain in source and in
the internal renderer registry as fallback routes, but are hidden from the
visible navigation because their capabilities are consolidated into the eight
core pages.

Phase 10 performs no database writes, schema changes, migrations, collector
activity, scheduler activity, Pipeline changes, Analytics changes, or
simulated-data generation. JSON and Markdown readers refresh when their file
mtime/size signature changes. Listing counts are not sales, and asking prices
are not transaction prices.

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
