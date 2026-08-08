# Phase 18B — Live External Automotive Intelligence

## Scope

Phase 18B adds an independent live evidence layer for the Dashboard and the
interactive AI retrieval path. It does not change the Collector, Parser,
Matching, Import Service, Scheduler, Pipeline, database schema, or database
write logic.

Production Mode enables live providers by default. Set
`LIVE_EXTERNAL_INTELLIGENCE=false` to disable them. Demo Mode always disables
network providers and continues to use the bundled validated Content Feed.

## Provider architecture

All providers implement the existing `ExternalIntelligenceProvider.search()`
contract and return the unified `ExternalEvidence` model. Four concrete
categories are configured:

- Automotive News Provider;
- Policy / Regulation Provider;
- Official Brand News Provider;
- Industry Report Provider.

The transport layer supports RSS/Atom, RSS autodiscovery with JSON-LD or dated
semantic-HTML fallback, provider-neutral JSON APIs, and official public-data
pages. Requests require HTTPS, use bounded timeouts and response sizes, perform
no authentication bypass, and use the existing atomic TTL cache with stale
fallback.

Each provider isolates failures at source level. Providers are also collected
independently, so one unavailable source or category does not remove evidence
returned by another.

## Configured public sources

| Category | Source | Interface |
| --- | --- | --- |
| Automotive news | [ACEA News](https://www.acea.auto/news/) | RSS autodiscovery / official page metadata |
| Policy and regulation | [European Commission DG MOVE News](https://transport.ec.europa.eu/news-events/news_en) | Official RSS |
| Brand intelligence | Volkswagen, BMW, Mercedes-Benz, Audi, Tesla and BYD official newsrooms | RSS autodiscovery / official page metadata |
| Industry reports | [ACEA Publications](https://www.acea.auto/nav/?content=publications) | Official page metadata |
| Official public data | [KBA monthly new-registration publications](https://www.kba.de/DE/Statistik/Fahrzeuge/Neuzulassungen/MonatlicheNeuzulassungen/monatl_neuzulassungen_node.html) | Official public-data page |

Source URLs, provider categories, TTLs, regions, evidence types, and reliability
scores are maintained in `config/live_external_intelligence.yaml`. No news,
policy, report, URL, or content item is generated when a source has no valid
record.

## Unified evidence

Every live record includes:

- source, title, URL and publication date;
- category, brand, vehicle and short content summary;
- reliability score from 0 to 100;
- fetched time, evidence type and region.

Only records published within the latest 30-day window are accepted. Future
timestamps and non-HTTPS evidence URLs are rejected. URL deduplication is
applied within each provider and again across providers.

## Reliability policy

Reliability is source-class scoring, not a truth probability:

- `100`: official government, regulator, or public-data source;
- `95`: official manufacturer newsroom;
- `90`: official automotive industry association;
- `70`: validated stale-cache fallback;
- below `70`: excluded from AI evidence.

The score does not prove that a report is complete or that a statement caused
an internal market change. External records are displayed and cited as
`External Market Signals`; SQLite, Analytics, Market Alerts, and Peer Benchmark
remain `Internal Data Evidence`.

## Caching and refresh

The Hub caches live collection results in memory for 15 minutes and the source
payload cache observes each configured TTL. The existing **Refresh content**
button clears both the Content Feed reader cache and the live in-memory cache.
Source failures leave the validated Content Feed available and are displayed as
isolated provider status rather than being converted into synthetic cards.
