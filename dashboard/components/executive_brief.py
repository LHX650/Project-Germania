"""Streamlit renderer for the evidence-grounded Executive Intelligence Brief."""

from __future__ import annotations

import streamlit as st
from services.executive_brief import (
    ExecutiveBriefArtifact,
    ExecutiveBriefArtifactError,
    build_executive_intelligence_brief,
    executive_brief_signature,
    load_executive_brief_artifact,
)
from services.intelligence import DailyMarketIntelligence

from ai.intelligence.executive_brief import ExecutiveBrief


def render_executive_intelligence_brief(
    report: DailyMarketIntelligence | None,
) -> None:
    """Render Today's Brief, risk/opportunity cards, and traceable evidence."""

    st.subheader("Executive Intelligence Brief")
    try:
        artifact = load_executive_brief_artifact()
    except ExecutiveBriefArtifactError:
        artifact = None
    if artifact is not None:
        _render_artifact(artifact, report)
        return

    if report is None:
        brief = build_executive_intelligence_brief(None)
    else:
        signature = executive_brief_signature(report)
        state_key = "executive_intelligence_brief"
        cached = st.session_state.get(state_key)
        if not isinstance(cached, dict) or cached.get("signature") != signature:
            with st.spinner("Building the grounded executive brief..."):
                brief = build_executive_intelligence_brief(report)
            st.session_state[state_key] = {
                "signature": signature,
                "brief": brief,
            }
        else:
            brief = cached["brief"]

    with st.container(border=True):
        st.markdown("**Today's Brief**")
        st.write(brief.executive_summary)
        st.caption(
            f"Report date: {brief.report_date or 'insufficient_data'} | "
            f"Generation mode: {brief.generation_mode} | "
            f"Provider: {brief.provider_name} | "
            f"Evidence SHA-256: {brief.evidence_sha256[:12]}..."
        )

    with st.container(horizontal=True):
        with st.container(border=True):
            st.markdown("**Risk Summary**")
            _render_bullets(brief.critical_risks[:4])
        with st.container(border=True):
            st.markdown("**Opportunity Summary**")
            _render_bullets(brief.top_opportunities[:4])

    with st.expander("Brief sections"):
        st.markdown("**Top Market Changes**")
        _render_bullets(brief.top_market_changes)
        st.markdown("**Competitive Movements**")
        _render_bullets(brief.competitive_movements)
        st.markdown("**External News & Policy Signals**")
        _render_bullets(brief.external_news_policy_signals)
        st.markdown("**Recommended Monitoring Actions**")
        _render_bullets(brief.recommended_monitoring_actions)

    with st.expander("Evidence"):
        _render_evidence(brief)


def _render_artifact(
    artifact: ExecutiveBriefArtifact,
    report: DailyMarketIntelligence | None,
) -> None:
    """Render the last valid automated artifact, including its declared date."""

    if report is not None and artifact.report_date != report.report_date:
        st.warning(
            "The latest valid Executive Brief is preserved from "
            f"{artifact.report_date.isoformat()}, while Analytics is dated "
            f"{report.report_date.isoformat()}."
        )
    with st.container(border=True):
        st.markdown("**Today's Brief**")
        st.markdown(artifact.sections["Executive Summary"])
        st.caption(
            f"Report date: {artifact.report_date.isoformat()} | "
            f"Generated: {artifact.generated_at:%Y-%m-%d %H:%M UTC} | "
            f"Generation mode: {artifact.generation_mode} | "
            f"Provider: {artifact.provider_name} | "
            f"Evidence SHA-256: {artifact.evidence_sha256[:12]}..."
        )
    with st.container(horizontal=True):
        with st.container(border=True):
            st.markdown("**Risk Summary**")
            st.markdown(artifact.sections["Critical Risks"])
        with st.container(border=True):
            st.markdown("**Opportunity Summary**")
            st.markdown(artifact.sections["Top Opportunities"])
    with st.expander("Brief sections"):
        for heading in (
            "Top Market Changes",
            "Competitive Movements",
            "External News & Policy Signals",
            "Recommended Monitoring Actions",
        ):
            st.markdown(f"**{heading}**")
            st.markdown(artifact.sections[heading])
    with st.expander("Evidence"):
        st.markdown("**Internal Market Evidence**")
        st.markdown(artifact.sections["Internal Market Evidence"])
        st.markdown("**External Market Signals**")
        st.markdown(artifact.sections["External Market Signals"])
        st.caption(
            "Internal Market Evidence and External Market Signals remain separate. "
            "Listing inventory is not vehicle sales, asking prices are not "
            "transaction prices, and external signals do not establish causation."
        )
        st.markdown("**Data Coverage**")
        st.markdown(artifact.sections["Data Coverage"])


def _render_evidence(brief: ExecutiveBrief) -> None:
    st.markdown("**Internal Market Evidence**")
    if not brief.internal_evidence:
        st.info("insufficient_data")
    else:
        st.dataframe(
            [
                {
                    "Evidence Source": item.evidence_source,
                    "Metric Name": item.metric_name,
                    "Value": item.value,
                    "Timestamp": item.timestamp,
                    "Vehicle": item.vehicle_key,
                }
                for item in brief.internal_evidence
            ],
            hide_index=True,
            width="stretch",
            height=min(420, 36 + 35 * min(len(brief.internal_evidence), 11)),
        )
    st.markdown("**External Market Signals**")
    if not brief.external_evidence:
        st.info("insufficient_data")
    else:
        st.dataframe(
            [
                {
                    "Source": item.source,
                    "Title": item.title,
                    "URL": item.url,
                    "Published": item.published_date,
                    "Category": item.category.replace("_", " ").title(),
                    "Reliability": item.reliability,
                    "Region": item.region,
                }
                for item in brief.external_evidence
            ],
            column_config={
                "URL": st.column_config.LinkColumn("Source URL"),
                "Reliability": st.column_config.ProgressColumn(
                    "Reliability",
                    min_value=0,
                    max_value=100,
                    format="%.0f",
                ),
            },
            hide_index=True,
            width="stretch",
        )
    st.caption(
        "Internal Market Evidence and External Market Signals remain separate. "
        "Listing inventory is not vehicle sales, asking prices are not transaction "
        "prices, and external signals do not establish causation."
    )
    if brief.data_gaps:
        st.markdown("**Data Coverage**")
        _render_bullets(brief.data_gaps)


def _render_bullets(items: tuple[str, ...]) -> None:
    for item in items:
        st.write(f"- {item}")
