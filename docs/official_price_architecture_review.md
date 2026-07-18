# Official Price Architecture Review

Phase 12.5 review date: 2026-07-18

This review covers the current official manufacturer price foundation for
Volkswagen, BMW, Mercedes-Benz, and Audi. It reviews structure, duplication,
reuse, and near-term extension guidance. It does not add brands, connect to
real websites, add Playwright code, change ORM models, change Alembic
migrations, change database schema, or commit Git changes.

## Current Architecture

The official price implementation currently has one complete Volkswagen module
and three manufacturer-specific foundation modules.

- `src/germania/collectors/volkswagen/`
  - Owns the first `OfficialPriceRecord` dataclass.
  - Owns the generic-enough `VolkswagenOfficialPriceImportService`.
  - Owns CSV/HTML batch import support from Phase 12B.
  - Parses local Volkswagen HTML fixture data.
- `src/germania/collectors/bmw/`
  - Parses local BMW HTML fixture data.
  - Sets `source_id="bmw_de"` on `OfficialPriceRecord`.
  - Delegates database import to `VolkswagenOfficialPriceImportService`.
- `src/germania/collectors/mercedes_benz/`
  - Parses local Mercedes-Benz HTML fixture data.
  - Sets `source_id="mercedes_benz_de"` on `OfficialPriceRecord`.
  - Delegates database import to `VolkswagenOfficialPriceImportService`.
- `src/germania/collectors/audi/`
  - Parses local Audi HTML fixture data.
  - Sets `source_id="audi_de"` on `OfficialPriceRecord`.
  - Delegates database import to `VolkswagenOfficialPriceImportService`.

The database write path is shared:

```text
local HTML fixture
-> brand-specific parser
-> OfficialPriceRecord
-> brand wrapper import service
-> VolkswagenOfficialPriceImportService.import_records()
-> DataSourceRepository
-> BrandRepository
-> VehicleRepository
-> VariantRepository
-> OfficialPriceRepository.upsert_official_price_record()
-> official_price_observations
```

Important current behavior:

- Parsers perform no network request.
- Parsers do not call Playwright.
- Parsers do not write to the database.
- Import services do not create brands, vehicles, or variants.
- Idempotency is owned by `OfficialPriceRepository`.
- Monthly leasing and financing payments are filtered by `price_type`.
- Amounts are parsed with `Decimal`, not `float`.

## Duplication Analysis

The current implementation has intentional duplication in three places.

| Area | Current duplication | Stability | Review |
| --- | --- | --- | --- |
| Parser DOM helpers | The four parsers each contain similar `_Node`, `_DOMParser`, field extraction, date parsing, boolean parsing, currency parsing, and German decimal parsing helpers. | Medium | Stable for current fixtures, but not yet proven against real manufacturer HTML differences. |
| Accepted price-type filtering | Each parser accepts `official_starting_price` and `official_base_price` and ignores leasing or finance payment cards. | High | This is a stable business rule and should stay consistent across brands. |
| Thin import wrappers | BMW, Mercedes-Benz, and Audi each wrap parser-specific `import_html()` and delegate `import_records()` to the Volkswagen import service. | High | Duplication is shallow and keeps each brand module easy to inspect. |
| Unit tests | Each brand repeats parser, Decimal, monthly-payment filtering, first import, second import, unknown vehicle, missing price, and table-write coverage. | High | Repetition is acceptable because every brand fixture must prove the same safety rules. |
| Config and exports | Each brand repeats source constants and `__all__` exports. | High | Expected for brand-local module identity. |

The largest duplication is the parser implementation. However, extracting it
now would create a common parser contract before real Audi, BMW, Mercedes-Benz,
and Volkswagen page structures have been validated. The current data attributes
are a fixture protocol, not yet a proven source protocol.

## Refactor Decision

No code refactor is recommended in Phase 12.5.

Reasons:

- Parser independence is an explicit project constraint.
- The shared import and repository path already removes the highest-risk
  duplication: database matching and writes.
- The remaining parser duplication is large but still early-stage and may
  diverge once real HTML structures are inspected manually.
- A common base collector would be premature and is explicitly out of scope.
- The import wrapper duplication is small and readable.
- Test duplication makes brand-specific safety coverage easy to audit.

The preferred posture is to keep current code as-is until at least one of these
conditions is met:

- two or more real manufacturer page structures prove they can share the same
  extraction primitives without brand-specific exceptions;
- a fifth or sixth brand repeats the same fixture protocol unchanged;
- a future batch importer needs a source-neutral official price parser or
  import service name;
- type ownership around `OfficialPriceRecord` becomes confusing enough to
  block development.

## Completed Refactoring

No refactoring was performed in Phase 12.5.

The review intentionally leaves the Python implementation unchanged:

- no ORM changes;
- no Alembic changes;
- no schema changes;
- no repository changes;
- no parser interface changes;
- no import-service behavior changes;
- no new brand collector;
- no Playwright or network code.

## Future Refactor Candidates

These are candidates only. They should be implemented later only if the
duplication remains stable.

1. Move the record model to a source-neutral module.

   Current state: `OfficialPriceRecord` lives in
   `germania.collectors.volkswagen.models`, even though BMW, Mercedes-Benz, and
   Audi also use it.

   Possible future target:
   `germania.collectors.official_prices.models`.

   Keep backward-compatible imports from the Volkswagen module if this move is
   ever done.

2. Add a tiny shared import service alias.

   Current state: brand wrappers delegate to
   `VolkswagenOfficialPriceImportService`, whose implementation is generic but
   whose name is Volkswagen-specific.

   Possible future target:
   `OfficialPriceImportService`, implemented as a source-neutral alias or
   moved class, with existing Volkswagen imports preserved.

3. Extract only low-level parser helpers.

   If real HTML reviews confirm stable behavior, move only safe primitives such
   as German decimal parsing, ISO date parsing, boolean parsing, text cleanup,
   and tiny DOM traversal into a private helper module.

   Do not extract brand-specific field mapping or source URL behavior unless
   those rules are proven identical.

4. Extract test fixtures for seed data only.

   The brand tests repeat temporary SQLite setup and seed-data creation. A small
   test helper could reduce duplication later. Keep brand-specific assertions in
   each test module.

## Guidance For Future Brands

### Skoda

- Keep a dedicated `src/germania/collectors/skoda/` module.
- Use source id `skoda_de` from `config/sources.yaml`.
- Preserve exact canonical model matching for Enyaq.
- Be careful with brand spelling and aliases. Do not rely on fuzzy matching to
  bridge diacritics or transliteration differences.
- Keep leasing and financing payments out of official price records.
- Start with local HTML fixtures only.

### Tesla

- Keep a dedicated `src/germania/collectors/tesla/` module.
- Use source id `tesla_de`.
- Tesla pages may mix base price, inventory price, delivery fees, incentives,
  and estimated savings. Do not import incentive-adjusted or estimated-savings
  figures as official vehicle price.
- Prefer explicit fixture fields for price type, raw price text, valid date,
  and source URL.
- Avoid Playwright until a compliance review says it is necessary and allowed.

### BYD

- Keep a dedicated `src/germania/collectors/byd/` module.
- Use source id `byd_de`.
- Watch for model-name ambiguity between Seal, Seal U, Atto 3, and Yuan PLUS.
- Do not create vehicles automatically if the canonical model is missing.
- Keep promotional offers, financing payments, and leasing payments separate
  from official starting price.
- Start with local HTML fixtures only.

## Final Recommendation

Keep the current architecture for the next brand foundation phase. The shared
database import path is already centralized where correctness matters most.
Maintain brand-specific parsers until real source structures provide stronger
evidence for a small shared parser helper.
