# Phase 18C — Executive Intelligence Brief

## Purpose

Phase 18C turns the current read-only Internal and External Intelligence into a
daily, evidence-grounded Germany Automotive Executive Brief. It does not add a
new Dashboard page and does not modify Collector, Parser, Matching, Import,
Scheduler, core Pipeline, database schema, or existing Analytics models.

## Brief structure

Every Markdown artifact contains:

1. Executive Summary
2. Top Market Changes
3. Critical Risks
4. Top Opportunities
5. Competitive Movements
6. External News & Policy Signals
7. Recommended Monitoring Actions
8. Internal Market Evidence register
9. External Market Signals register
10. Data Coverage disclosures

Internal Market Evidence includes current Analytics, Opportunity Score,
Price/Inventory Pressure, Market Momentum, Market Alerts, Peer Benchmark, and
available read-only history. External Market Signals include only validated
news, policy, official brand, and industry-report metadata returned by the
existing provider layer.

## Grounding and safety

- The evidence packet has a canonical SHA-256 digest.
- The deterministic local generator is always available.
- OpenAI, Claude, or Gemini can refine the grounded draft through the existing
  provider interface and environment configuration.
- A provider response is rejected when its evidence digest differs, a required
  section is missing, it introduces a number absent from the evidence, or it
  states that an external signal caused an internal market change.
- Any rejected or unavailable provider falls back to the local-rule Brief.
- Missing inputs remain `insufficient_data`.
- Listing inventory is not described as sales, and asking prices are not
  described as transaction prices.

## Dashboard integration

Executive Overview now contains an **Executive Intelligence Brief** region with:

- Today's Brief
- Risk Summary
- Opportunity Summary
- compact full-section detail
- expandable Internal Market Evidence and External Market Signals
- report date, generation mode, provider, and evidence SHA-256

The region is cached against the current Analytics, external artifact, and
Content Feed file signatures. Demo Mode reads only the bundled Demo artifacts
and never enables live providers. Production keeps the existing provider
failure isolation and read-only database access.

## Markdown artifact

Generate the current production artifact without live network access:

```powershell
.venv\Scripts\python.exe scripts\generate_executive_brief.py `
  --no-live-external
```

Default output:

```text
reports/daily_executive_intelligence_brief.md
```

Generate from Demo inputs without changing the Demo bundle:

```powershell
.venv\Scripts\python.exe scripts\generate_executive_brief.py `
  --demo-mode `
  --output reports/demo_executive_intelligence_brief.md
```

The writer uses a temporary sibling file and atomic replace so a failed write
does not overwrite the previous valid Brief. The command is an independent
reporting entry point; Phase 18C intentionally does not alter the prohibited
core Pipeline or Scheduler.
