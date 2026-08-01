"""AI Market Insights page backed by the generated Markdown report."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st
from components.page_header import render_page_header
from services.ai_report import AIMarketReport


def render(
    report: AIMarketReport | None,
    error_message: str | None = None,
) -> None:
    """Render dynamic AI insights without database or collection access."""

    render_page_header(
        title="AI Market Insights",
        subtitle="基于每日 AI Market Report 的德国汽车市场摘要、机会与风险解读。",
    )
    if report is None:
        _render_unavailable(error_message)
        return

    _render_metadata(report)

    with st.container(border=True):
        st.subheader("最新 AI 市场摘要")
        st.markdown(report.market_overview_markdown)

    opportunity_column, risk_column = st.columns(2)
    with opportunity_column, st.container(border=True):
        st.subheader("市场机会")
        st.markdown(report.market_opportunity_markdown)
    with risk_column, st.container(border=True):
        st.subheader("风险提示")
        st.markdown(report.risk_markdown)

    with st.container(border=True):
        st.subheader("重点车型分析")
        st.markdown(report.vehicle_opportunity_markdown)

    with st.expander("查看完整 AI Market Report"):
        st.markdown(report.raw_markdown)

    st.caption(
        "AI 解读来自只读 Markdown 报告；挂牌价格不是成交价格，"
        "挂牌库存不代表销量或新车注册量。"
    )


def _render_metadata(report: AIMarketReport) -> None:
    generated_at = _berlin_time(report)
    provider = report.provider_name or "本地规则分析"
    with st.container(horizontal=True):
        st.metric("Analytics 数据日期", report.analytics_date.isoformat(), border=True)
        st.metric("报告生成时间", generated_at, border=True)
        st.metric("Generation mode", report.generation_mode, border=True)
        st.metric("LLM Provider", provider, border=True)
    st.caption(
        f"来源：{report.source_path.name} · "
        "报告生成时间根据 Markdown 文件最后修改时间显示（Europe/Berlin）。"
    )


def _berlin_time(report: AIMarketReport) -> str:
    try:
        timezone = ZoneInfo("Europe/Berlin")
        suffix = "CEST" if report.generated_at_utc.astimezone(timezone).dst() else "CET"
    except ZoneInfoNotFoundError:
        timezone = report.generated_at_utc.tzinfo
        suffix = "UTC"
    return report.generated_at_utc.astimezone(timezone).strftime(
        f"%Y-%m-%d %H:%M {suffix}"
    )


def _render_unavailable(message: str | None) -> None:
    st.error(
        message or "AI 市场报告当前不可用，请先生成每日 AI Market Report。",
        icon=":material/error:",
    )
    st.code(
        ".\\.venv\\Scripts\\python.exe -m ai "
        "--input reports\\daily_market_intelligence.json "
        "--output reports\\daily_ai_market_report.md",
        language="powershell",
    )
