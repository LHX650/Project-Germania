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

## Phase 17 Automotive Intelligence Agent

`ai/intelligence/` adds an interactive, evidence-grounded analysis layer. It is
separate from the scheduled report generator and does not write reports,
databases, or Pipeline state. The Agent receives a canonical evidence packet,
checks its SHA-256 digest, and always returns these sections:

- Situation Summary;
- Evidence;
- Key Drivers;
- Competitive Implication;
- Recommended Monitoring Actions;
- Confidence Level.

The default `AI_PROVIDER=local` mode uses deterministic local rules. Optional
OpenAI, Claude, Gemini, or local-model adapters can implement
`ai.intelligence.providers.AgentLLMProvider`. News, search, official brand news,
and industry-report adapters implement
`ExternalIntelligenceProvider`. Provider failures, digest mismatches, missing
sections, and unsupported numbers fail closed to the grounded local draft.

The current Dashboard external provider searches the existing validated content
Feed and makes no live network request. Missing internal evidence returns
`insufficient_data`.

### Optional API providers

The Agent includes dependency-free HTTPS adapters for:

- `AI_PROVIDER=openai` with `OPENAI_API_KEY`;
- `AI_PROVIDER=claude` with `ANTHROPIC_API_KEY`;
- `AI_PROVIDER=gemini` with `GOOGLE_API_KEY`.

`AI_PROVIDER=local` remains the default. Optional model overrides are
`OPENAI_MODEL`, `ANTHROPIC_MODEL`, and `GEMINI_MODEL`. Credentials are read only
from environment variables and are never included in evidence, prompts, logs, or
Dashboard provenance. Missing credentials, timeouts, HTTP errors, invalid JSON,
empty responses, digest mismatches, missing sections, and unsupported numeric
claims all return the grounded local-rules answer.

Every `AgentAnswer` also carries structured Evidence Records with Evidence
Source, Metric Name, Value, Timestamp, and optional Vehicle identity. These are
derived from current Analytics, quantitative models, Peer Benchmark, Market
Alerts, read-only SQLite history, and verified external metadata.

## Phase 18A external automotive intelligence

The provider-neutral external layer defines one `ExternalEvidence` contract for
source, title, HTTPS URL, publication date, category, brand, vehicle, short
summary, and reliability. `NewsProvider`, `SearchProvider`,
`OfficialBrandNewsProvider`, and `IndustryReportProvider` share the same query
contract, so a future News API, Google/Bing adapter, brand RSS/API, or industry
data API can be registered without changing the Agent.

The current adapter remains offline and read-only: it searches the validated
Production or Demo Content Feed. It stores no full article and performs no live
request. When no relevant external record exists, retrieval reports
`insufficient_data`. External context is attributed evidence, not proof that a
news event caused an internal asking-price or listing-inventory change.

Phase 18B adds optional live Production providers for automotive news, official
policy/regulation updates, official brand newsrooms, and industry reports. They
use public RSS/Atom, provider-neutral JSON API, or official public-data
interfaces with a 30-day window, URL deduplication, TTL caching, configurable
0–100 source reliability, and source/provider failure isolation. Demo Mode does
not make live requests. AI output labels retrieved metrics as Internal Data
Evidence and live context as External Market Signals; external items are never
presented as a confirmed cause of listing-price or inventory changes.

## Phase 18C Executive Intelligence Brief

`ai.intelligence.executive_brief` adds a seven-section Germany Automotive
Executive Brief. The same immutable evidence packet drives the local draft,
optional LLM refinement, Dashboard evidence panel, and standalone Markdown
artifact. Provider output must retain the evidence SHA-256, required headings,
supported numeric values, and separation between Internal Market Evidence and
External Market Signals; otherwise generation falls back to local rules.

Generate the artifact without a live network call:

```powershell
.venv\Scripts\python.exe scripts\generate_executive_brief.py --no-live-external
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest ai\tests
.\.venv\Scripts\python.exe -m ruff check ai
.\.venv\Scripts\python.exe -m black --check ai
```
