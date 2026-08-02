"""Read-only operational and data quality control surface."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta

import streamlit as st
from components.intelligence import format_percentage
from components.page_header import render_page_header
from services.content_feed import ContentFeedError, load_content_feed
from services.daily_updates import (
    DailyUpdatePoint,
    DailyUpdateSummary,
    load_daily_update_summary,
)
from services.database import DatabaseQualitySnapshot, load_database_quality
from services.pipeline_status import PIPELINE_STAGES, PipelineStatus

_STAGE_LABELS = {
    "collection": "Collection",
    "analytics": "Analytics",
    "ai": "AI Report",
    "external_intelligence": "External Intelligence",
    "content_feed": "Content Feed",
    "strategic": "Strategic Report",
}


def render(
    pipeline: PipelineStatus | None = None,
    error_message: str | None = None,
) -> None:
    """Render daily updates, pipeline, collection, and database quality."""

    render_page_header(
        title="Data Quality",
        subtitle=(
            "Daily marketplace updates, Pipeline stages, collection quality, "
            "database coverage, and external source health."
        ),
    )

    try:
        daily_updates = load_daily_update_summary()
        daily_update_error = None
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        daily_updates = None
        daily_update_error = str(exc)

    _render_daily_update_summary(
        daily_updates,
        pipeline,
        daily_update_error=daily_update_error,
        pipeline_error=error_message,
    )
    _render_update_history(daily_updates)
    _render_operational_status(pipeline, error_message)

    try:
        quality = load_database_quality()
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        st.warning(f"SQLite data-quality metrics are unavailable: {exc}")
        quality = None

    _render_collection_quality(quality)
    _render_database_quality(quality)
    _render_external_sources()


def _render_daily_update_summary(
    summary: DailyUpdateSummary | None,
    pipeline: PipelineStatus | None,
    *,
    daily_update_error: str | None,
    pipeline_error: str | None,
) -> None:
    st.subheader("Daily Data Update Summary")
    if daily_update_error is not None:
        st.warning(f"Daily update metrics are unavailable: {daily_update_error}")

    with st.container(horizontal=True):
        st.metric(
            "Listings Scanned",
            _metric_count(summary, "listings_scanned"),
            border=True,
        )
        st.metric(
            "New Listings",
            _metric_count(summary, "new_listings"),
            border=True,
        )
        st.metric(
            "Existing Listings Updated",
            _metric_count(summary, "existing_listings_updated"),
            border=True,
        )
        st.metric(
            "Price Changes",
            _metric_count(summary, "price_changes"),
            border=True,
        )
        st.metric(
            "Inactive / Removed Listings",
            _metric_count(summary, "inactive_listings"),
            border=True,
        )

    with st.container(horizontal=True):
        st.metric(
            "Price Decreases",
            _metric_count(summary, "price_decreases"),
            border=True,
        )
        st.metric(
            "Price Increases",
            _metric_count(summary, "price_increases"),
            border=True,
        )
        st.metric(
            "New Price History Records",
            _metric_count(summary, "new_price_history_records"),
            border=True,
        )
        st.metric(
            "Vehicles Updated",
            _metric_count(summary, "vehicles_updated"),
            border=True,
        )

    with st.container(horizontal=True):
        st.metric(
            "Pipeline Status",
            _pipeline_status_label(pipeline),
            border=True,
        )
        st.metric(
            "Last Successful Collection",
            _last_successful_update(summary, pipeline),
            border=True,
        )
        st.metric(
            "Pipeline Duration",
            _pipeline_duration(pipeline),
            border=True,
        )

    if pipeline is None and pipeline_error:
        st.caption(f"Pipeline artifact: {pipeline_error}")
    run_id = summary.run_id if summary is not None else None
    st.caption(
        f"Latest collection run: {run_id or 'Insufficient data'}. "
        "Scanned is the sum of collection-batch record counts. New and existing "
        "updated listings are distinct listing observations in that run; updated "
        "means an existing listing was refreshed, not that a sale occurred. Price "
        "changes compare consecutive asking-price history records and exclude each "
        "listing's initial price record. Asking prices are not transaction prices."
    )


def _render_update_history(summary: DailyUpdateSummary | None) -> None:
    st.subheader("Update History")
    selected_days = st.segmented_control(
        "History window",
        options=(7, 30),
        default=7,
        format_func=lambda value: f"{value} days",
        key="data_quality_update_history_days",
    )
    points = _history_window(summary, int(selected_days or 7))
    if not points:
        st.info("Insufficient data for the selected update-history window.")
        return

    rows = [
        {
            "Date": point.update_date,
            "New": point.new_listings,
            "Updated": point.existing_listings_updated,
            "Price Changed": point.price_changes,
            "Inactive": point.inactive_listings,
        }
        for point in points
    ]
    st.line_chart(
        rows,
        x="Date",
        y=("New", "Updated", "Price Changed", "Inactive"),
        height=320,
    )
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption(
        "Daily UTC update events from SQLite. Missing calendar days are not "
        "backfilled, and listing activity must not be interpreted as vehicle sales."
    )


def _render_operational_status(
    pipeline: PipelineStatus | None,
    error_message: str | None,
) -> None:
    st.subheader("Pipeline / Scheduler status")
    with st.container(horizontal=True):
        st.metric(
            "Pipeline",
            pipeline.overall_status if pipeline is not None else "Unavailable",
            border=True,
        )
        st.metric(
            "Latest Run",
            (
                pipeline.run_id
                if pipeline is not None and pipeline.run_id
                else "Not provided"
            ),
            border=True,
        )
    st.metric("Windows Scheduler", "Runtime status not provided", border=True)
    st.caption(
        "Read-only Dashboard artifacts do not include Windows Task Scheduler "
        "runtime status. This page does not invoke or modify scheduled tasks."
    )
    if pipeline is None:
        st.warning(error_message or "The pipeline status artifact is unavailable.")
        return
    rows = [
        {
            "Stage": _STAGE_LABELS[stage],
            "Status": pipeline.stages[stage],
            "Error": pipeline.errors.get(stage),
        }
        for stage in PIPELINE_STAGES
    ]
    st.dataframe(rows, hide_index=True, width="stretch")


def _render_collection_quality(quality: DatabaseQualitySnapshot | None) -> None:
    st.subheader("Collection and matching quality")
    if quality is None:
        st.info("No verifiable collection-batch quality data is available.")
        return
    with st.container(horizontal=True):
        st.metric(
            "Page success rate",
            format_percentage(quality.page_success_rate_pct),
            border=True,
        )
        st.metric(
            "Task success rate",
            format_percentage(quality.task_success_rate_pct),
            border=True,
        )
        st.metric("matched", f"{quality.matched_count:,}", border=True)
        st.metric("rejected", f"{quality.rejected_count:,}", border=True)
        st.metric("low_confidence", f"{quality.low_confidence_count:,}", border=True)
    st.caption(
        f"Latest collection run: {quality.latest_run_id or 'Not provided'} | "
        f"Pages {quality.succeeded_pages}/{quality.requested_pages} | "
        f"Tasks {quality.successful_task_count}/{quality.task_count} | "
        f"import rejected {quality.import_rejected_count:,}"
    )


def _render_database_quality(quality: DatabaseQualitySnapshot | None) -> None:
    st.subheader("Database coverage and field completeness")
    if quality is None:
        st.info("No database coverage metrics are available.")
        return
    with st.container(horizontal=True):
        st.metric("Listings", f"{quality.listings_count:,}", border=True)
        st.metric("Active listings", f"{quality.active_listings_count:,}", border=True)
        st.metric("Observations", f"{quality.observations_count:,}", border=True)
        st.metric("Price History", f"{quality.price_history_count:,}", border=True)
        st.metric("Quality issues", f"{quality.quality_issue_count:,}", border=True)
    rows = [
        {"Field": field, "Completeness (%)": percentage}
        for field, percentage in quality.field_completeness_pct.items()
    ]
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        column_config={
            "Completeness (%)": st.column_config.ProgressColumn(
                "Completeness (%)",
                min_value=0,
                max_value=100,
                format="%.2f%%",
            )
        },
    )
    st.caption(f"Latest SQLite update: {quality.latest_updated_at or 'Not provided'}")


def _render_external_sources() -> None:
    st.subheader("External source status")
    try:
        feed = load_content_feed()
    except ContentFeedError as exc:
        st.info(f"The External Intelligence Feed is unavailable: {exc}")
        return
    rows = [
        {
            "Source": source.get("source_name")
            or source.get("source")
            or "Unnamed source",
            "Status": source.get("status"),
            "Cache": source.get("cache_status"),
            "Records": source.get("record_count"),
            "Updated at": source.get("updated_at"),
            "Limitation": source.get("limitation"),
            "Source URL": source.get("source_url"),
        }
        for source in feed.sources
    ]
    if not rows:
        st.info("The feed does not provide external source status records.")
        return
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        column_config={"Source URL": st.column_config.LinkColumn("Source URL")},
    )
    st.caption(f"Content Feed updated: {feed.generated_at:%Y-%m-%d %H:%M UTC}")


def _metric_count(summary: DailyUpdateSummary | None, field: str) -> str:
    if summary is None:
        return "Insufficient data"
    value = getattr(summary, field)
    return "Insufficient data" if value is None else f"{value:,}"


def _pipeline_status_label(pipeline: PipelineStatus | None) -> str:
    if pipeline is None:
        return "Insufficient data"
    return pipeline.overall_status.replace("_", " ").title()


def _last_successful_update(
    summary: DailyUpdateSummary | None,
    pipeline: PipelineStatus | None,
) -> str:
    if pipeline is not None and pipeline.stages.get("collection") in {
        "completed",
        "demo_fixture",
    }:
        completed = pipeline.timestamps.get("collection_completed_at")
        if completed is not None:
            return completed.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    if summary is None or summary.last_successful_update_at is None:
        return "Insufficient data"
    return _format_database_timestamp(summary.last_successful_update_at)


def _pipeline_duration(pipeline: PipelineStatus | None) -> str:
    if pipeline is None:
        return "Insufficient data"
    started = pipeline.timestamps.get("pipeline_started_at")
    completed = pipeline.timestamps.get("pipeline_completed_at")
    if started is None or completed is None or completed < started:
        return "Insufficient data"
    seconds = int((completed - started).total_seconds())
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    return f"{minutes}m {seconds}s"


def _history_window(
    summary: DailyUpdateSummary | None,
    days: int,
) -> tuple[DailyUpdatePoint, ...]:
    if summary is None or not summary.history:
        return ()
    anchor = date.fromisoformat(summary.history[-1].update_date)
    first_day = anchor - timedelta(days=days - 1)
    return tuple(
        point
        for point in summary.history
        if date.fromisoformat(point.update_date) >= first_day
    )


def _format_database_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
