# External Intelligence Providers

Phase 8B adds an independent public-data adapter layer. It does not write to
the Project Germania database and is not part of the marketplace Collector.

## Outputs

`reports/external_intelligence.json` uses one versioned schema with:

- official KBA FZ10 registrations: period, brand, model, registrations, fuel
  type, country, source URL, and retrieval time;
- general news: source, publication time, dynamically recognized tracked
  brands/models, country, and source tags;
- official brand news for Volkswagen, BMW, Mercedes-Benz, Audi, Tesla, and
  BYD with the same news fields;
- source/cache state: update time, TTL, source URL, record count, cache status,
  and limitations.

Sources and TTLs are configured in `config/external_intelligence.yaml`. The
KBA adapter first discovers the exact monthly workbook through the public
GovData catalog and retains a configurable KBA URL template as a fallback.
Vehicle recognition is bounded by the vehicle and brand names supplied by the
current Analytics report; the Provider does not create new model facts.

## Phase 8C public content Feed

`python -m external_intelligence.content_feed` converts the attributed news in
`reports/external_intelligence.json` and public report/video provider metadata
into `reports/external_intelligence/content_feed.json`. Source definitions live
in `config/content_sources.yaml`.

- GovData/KBA report metadata is read from its public CKAN catalog and retains
  the official catalog and document URLs.
- YouTube content is read from a public channel Atom Feed. No media is
  downloaded and no API key is required.
- Only metadata, a bounded short summary, and public source links are stored.
- Invalid or non-HTTPS URLs, future timestamps, duplicate URLs, and malformed
  YouTube IDs are rejected.
- An expired valid cache is marked `stale_cache` when refresh fails. With no
  valid cache, the source is marked `failed` and no card is invented.

## Cache policy

The cache key is derived from source ID and URL. A fresh entry avoids a second
download. Expired entries are conditionally revalidated when validators are
available. If refresh fails, a valid old payload may be used with
`stale_fallback`; corrupt payloads are never accepted.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest external_intelligence\tests strategic\tests
.\.venv\Scripts\python.exe -m ruff check external_intelligence strategic
.\.venv\Scripts\python.exe -m black --check external_intelligence strategic
```
