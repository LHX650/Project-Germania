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
        subtitle="流水线、采集任务、字段完整性、数据量与外部来源健康状态。",
    )
    _render_operational_status(pipeline, error_message)

    try:
        quality = load_database_quality()
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        st.warning(f"SQLite 数据质量指标当前不可用：{exc}")
        quality = None

    _render_collection_quality(quality)
    _render_database_quality(quality)
    _render_external_sources()


def _render_operational_status(
    pipeline: PipelineStatus | None,
    error_message: str | None,
) -> None:
    st.subheader("Pipeline / Scheduler 状态")
    with st.container(horizontal=True):
        st.metric(
            "Pipeline",
            pipeline.overall_status if pipeline is not None else "不可用",
            border=True,
        )
        st.metric(
            "Latest Run",
            pipeline.run_id if pipeline is not None and pipeline.run_id else "未提供",
            border=True,
        )
        st.metric("Windows Scheduler", "运行状态未提供", border=True)
    st.caption(
        "Dashboard 只读工件不包含 Windows Task Scheduler 运行状态；"
        "页面不会调用或修改计划任务。"
    )
    if pipeline is None:
        st.warning(error_message or "Pipeline 状态工件当前不可用。")
        return
    rows = [
        {
            "阶段": _STAGE_LABELS[stage],
            "状态": pipeline.stages[stage],
            "错误信息": pipeline.errors.get(stage),
        }
        for stage in PIPELINE_STAGES
    ]
    st.dataframe(rows, hide_index=True, width="stretch")


def _render_collection_quality(quality: DatabaseQualitySnapshot | None) -> None:
    st.subheader("采集与匹配质量")
    if quality is None:
        st.info("暂无可验证的采集批次质量数据。")
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
        f"最新 collection run: {quality.latest_run_id or '未提供'} · "
        f"页面 {quality.succeeded_pages}/{quality.requested_pages} · "
        f"任务 {quality.successful_task_count}/{quality.task_count} · "
        f"import rejected {quality.import_rejected_count:,}"
    )


def _render_database_quality(quality: DatabaseQualitySnapshot | None) -> None:
    st.subheader("数据库覆盖与字段完整率")
    if quality is None:
        st.info("暂无数据库覆盖指标。")
        return
    with st.container(horizontal=True):
        st.metric("Listings", f"{quality.listings_count:,}", border=True)
        st.metric("Active listings", f"{quality.active_listings_count:,}", border=True)
        st.metric("Observations", f"{quality.observations_count:,}", border=True)
        st.metric("Price History", f"{quality.price_history_count:,}", border=True)
        st.metric("Quality issues", f"{quality.quality_issue_count:,}", border=True)
    rows = [
        {"字段": field, "完整率(%)": percentage}
        for field, percentage in quality.field_completeness_pct.items()
    ]
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        column_config={
            "完整率(%)": st.column_config.ProgressColumn(
                "完整率(%)",
                min_value=0,
                max_value=100,
                format="%.2f%%",
            )
        },
    )
    st.caption(f"SQLite 最新更新时间：{quality.latest_updated_at or '未提供'}")


def _render_external_sources() -> None:
    st.subheader("外部来源状态")
    try:
        feed = load_content_feed()
    except ContentFeedError as exc:
        st.info(f"External Intelligence Feed 当前不可用：{exc}")
        return
    rows = [
        {
            "来源": source.get("source_name") or source.get("source") or "未命名来源",
            "状态": source.get("status"),
            "缓存": source.get("cache_status"),
            "记录数": source.get("record_count"),
            "更新时间": source.get("updated_at"),
            "限制": source.get("limitation"),
            "来源链接": source.get("source_url"),
        }
        for source in feed.sources
    ]
    if not rows:
        st.info("Feed 没有提供外部来源状态。")
        return
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        column_config={"来源链接": st.column_config.LinkColumn("来源链接")},
    )
    st.caption(f"Content Feed 更新时间：{feed.generated_at:%Y-%m-%d %H:%M UTC}")
