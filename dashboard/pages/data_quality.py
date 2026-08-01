"""Read-only operational and data quality control surface."""

from __future__ import annotations

import sqlite3

import streamlit as st
from components.intelligence import format_percentage
from components.page_header import render_page_header
from services.content_feed import ContentFeedError, load_content_feed
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
    """Render pipeline, collection, completeness, and external-source quality."""

    render_page_header(
        title="Data Quality",
        subtitle=(
            "Pipeline stages, collection tasks, field completeness, data volumes, "
            "and external source health."
        ),
    )
    _render_operational_status(pipeline, error_message)

    try:
        quality = load_database_quality()
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        st.warning(f"SQLite data-quality metrics are unavailable: {exc}")
        quality = None

    _render_collection_quality(quality)
    _render_database_quality(quality)
    _render_external_sources()


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
        f"Latest collection run: {quality.latest_run_id or 'Not provided'} · "
        f"Pages {quality.succeeded_pages}/{quality.requested_pages} · "
        f"Tasks {quality.successful_task_count}/{quality.task_count} · "
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
