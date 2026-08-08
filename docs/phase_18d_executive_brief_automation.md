# Phase 18D — Executive Brief Automation

## Pipeline flow

```text
daily_market_monitor.py (Collection -> Analytics)
    -> AI Report
    -> External Intelligence
    -> Content Feed
    -> Executive Brief
    -> Strategic Report
```

The orchestration layer invokes the existing Executive Brief generator only
when Analytics and AI are completed and External Intelligence plus Content Feed
are `completed` or `partially_completed`. It reads the generated evidence
artifacts and does not perform a second live external-provider fetch.

## Artifact and status

The stage atomically writes:

`reports/daily_executive_intelligence_brief.md`

The previous Brief is included in the Pipeline archive created before each run.
`reports/pipeline_status.json` records:

- `executive_brief_status`
- `executive_brief_error_message`
- `timestamps.executive_brief_started_at`
- `timestamps.executive_brief_completed_at`

## Failure isolation

A generation exception records a failed Executive Brief stage but does not
change the successful Collection or Analytics result and does not prevent the
Strategic stage from running. The overall Pipeline status becomes
`partially_completed` when Strategic succeeds. Because the generator writes via
temporary-file replacement, a failed generation cannot overwrite the last
valid Brief.

Executive Overview reads the persisted Brief as a read-only artifact. When its
date differs from the latest Analytics date, the Dashboard explicitly displays
both dates so a preserved report cannot be mistaken for a current one. Older
Pipeline status artifacts without the new stage remain readable as
`not_available`.

## Isolation boundary

Phase 18D does not modify Collector, Parser, Matching, Import, database schema or
writes, Analytics formulas, Scheduler timing, or the daily collection entry
point. Demo Mode continues to use its public read-only bundle and local fallback
when no automated Brief artifact is bundled.
