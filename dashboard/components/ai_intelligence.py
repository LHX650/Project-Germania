"""Reusable Streamlit renderers for the integrated intelligence agent."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict

import streamlit as st
from services.ai_agent import answer_question
from services.intelligence import DailyMarketIntelligence, vehicle_key
from services.market_alerts import MarketAlert, MarketAlertReport
from services.runtime import get_dashboard_data_paths

from ai.intelligence.models import AgentAnswer


def render_daily_market_brief(report: DailyMarketIntelligence) -> None:
    """Render an automatically refreshed, evidence-based management brief."""

    st.subheader("AI Daily Market Brief")
    signature = _report_signature(report)
    state_key = "ai_daily_market_brief"
    cached = st.session_state.get(state_key)
    if not isinstance(cached, dict) or cached.get("signature") != signature:
        with st.spinner("Building the evidence-based daily brief..."):
            answer = answer_question(
                (
                    f"Daily market brief for {report.report_date.isoformat()}: "
                    "top market changes, main risks, and opportunities."
                ),
                report,
            )
        st.session_state[state_key] = {"signature": signature, "answer": answer}
    else:
        answer = cached["answer"]

    columns = st.columns(3)
    with columns[0], st.container(border=True):
        st.markdown("**Top Market Changes**")
        st.write(answer.situation_summary)
    with columns[1], st.container(border=True):
        st.markdown("**Main Risks**")
        for item in answer.key_drivers[:3]:
            st.write(f"- {item}")
    with columns[2], st.container(border=True):
        st.markdown("**Opportunities**")
        st.write(answer.competitive_implication)
    with st.expander("Evidence, monitoring actions, and confidence"):
        _render_answer_sections(answer, include_summary=False)


def render_free_analyst(report: DailyMarketIntelligence | None) -> None:
    """Render a compact free-question analyst entry inside Executive Overview."""

    st.subheader("AI Automotive Intelligence Analyst")
    st.caption(
        "Ask about current vehicle pressure, opportunities, market risks, or a "
        "vehicle comparison. Answers use read-only Project Germania evidence."
    )
    st.markdown("**Suggested Questions**")
    suggested_question: str | None = None
    with st.container(horizontal=True):
        for index, suggestion in enumerate(_suggested_questions(report)):
            if st.button(
                suggestion,
                key=f"ai_suggested_question::{index}",
                icon=":material/quick_phrases:",
            ):
                suggested_question = suggestion
    with st.form("ai_automotive_intelligence_question"):
        question = st.text_input(
            "Question",
            placeholder="Why is a selected vehicle under pressure?",
        )
        submitted = st.form_submit_button("Analyze with current evidence")
    requested_question = suggested_question or (question if submitted else None)
    if requested_question is not None:
        if not requested_question.strip():
            st.warning("Enter a market-intelligence question.")
        else:
            with st.spinner("Retrieving current evidence..."):
                st.session_state["ai_automotive_intelligence_answer"] = answer_question(
                    requested_question, report
                )
    answer = st.session_state.get("ai_automotive_intelligence_answer")
    if isinstance(answer, AgentAnswer):
        render_agent_answer(answer)


def render_vehicle_ai_insight(
    report: DailyMarketIntelligence,
    *,
    brand: str,
    model: str,
) -> None:
    """Render on-demand intelligence for one selected vehicle."""

    st.subheader("AI Vehicle Insight")
    key = vehicle_key(brand, model)
    state_key = f"ai_vehicle_insight::{key}"
    if st.button(
        "Generate AI Insight",
        key=f"generate_ai_vehicle_insight::{key}",
        type="primary",
    ):
        with st.spinner("Retrieving vehicle, peer, alert, and history evidence..."):
            st.session_state[state_key] = answer_question(
                f"Why is {key} under pressure and what is its competitive position?",
                report,
                selected_vehicle_key=key,
            )
    answer = st.session_state.get(state_key)
    if not isinstance(answer, AgentAnswer):
        st.caption(
            "Generate an evidence-based view of Strength, Risk, Peer Comparison, "
            "and Market Position."
        )
        return
    with st.container(border=True):
        st.markdown("**1. Market Position**")
        st.write(answer.situation_summary)
        _render_metric_references(
            answer,
            ("Vehicle Opportunity Score", "Market Momentum Score"),
        )
    with st.container(border=True):
        st.markdown("**2. Competitive Strength**")
        st.write(answer.competitive_implication)
        _render_metric_references(answer, ("Vehicle Opportunity Score",))
    with st.container(border=True):
        st.markdown("**3. Key Risks**")
        for item in answer.key_drivers[:3]:
            st.write(f"- {item}")
        _render_metric_references(
            answer,
            ("Price Pressure Index", "Inventory Pressure Index"),
        )
    with st.container(border=True):
        st.markdown("**4. Peer Comparison**")
        peer_lines = tuple(item for item in answer.evidence if "peer rank" in item)
        st.write(peer_lines[0] if peer_lines else "insufficient_data")
        _render_metric_references(
            answer,
            ("Peer Status", "Peer Rank", "Peer Percentile", "Peer Sample Size"),
        )
    with st.container(border=True):
        st.markdown("**5. Recommended Monitoring**")
        for item in answer.recommended_monitoring_actions:
            st.write(f"- {item}")
    _render_evidence_panel(answer)
    with st.expander("View complete evidence-based answer"):
        _render_answer_sections(answer, include_evidence_panel=False)


def render_alert_explainer(
    report: DailyMarketIntelligence,
    alert_report: MarketAlertReport,
) -> None:
    """Render an on-demand explanation of an existing Alert rule evaluation."""

    st.subheader("Explain Alert")
    active = tuple(
        item for item in alert_report.alerts if item.level in {"Critical", "Warning"}
    )
    if not active:
        st.info("No Critical or Warning alert is currently available to explain.")
        return
    labels = tuple(_alert_label(item) for item in active)
    selected_label = st.selectbox(
        "Alert to explain",
        labels,
        key="ai_alert_to_explain",
    )
    selected = active[labels.index(selected_label)]
    state_key = f"ai_alert_explanation::{selected_label}"
    if st.button("Explain Alert", key="generate_ai_alert_explanation"):
        with st.spinner("Retrieving alert and related market evidence..."):
            st.session_state[state_key] = answer_question(
                f"Explain alert for {selected.vehicle_key}: {selected.alert_type}",
                report,
                selected_vehicle_key=selected.vehicle_key,
                selected_alert=selected,
            )
    answer = st.session_state.get(state_key)
    if not isinstance(answer, AgentAnswer):
        return
    with st.container(border=True):
        st.markdown("**Alert Reason**")
        st.write(selected.trigger_reason)
    with st.container(border=True):
        st.markdown("**Supporting Evidence**")
        for name, value in selected.related_metrics.items():
            rendered = "insufficient_data" if value is None else value
            st.write(f"- {name.replace('_', ' ').title()}: {rendered}")
    with st.container(border=True):
        st.markdown("**Competitive Impact**")
        st.write(answer.competitive_implication)
    with st.container(border=True):
        st.markdown("**Recommended Action**")
        for item in answer.recommended_monitoring_actions:
            st.write(f"- {item}")
    _render_evidence_panel(answer)
    with st.expander("View complete evidence-based explanation"):
        _render_answer_sections(answer, include_evidence_panel=False)


def render_agent_answer(answer: AgentAnswer) -> None:
    """Render all required answer sections and provenance."""

    with st.container(border=True):
        _render_answer_sections(answer)


def _render_answer_sections(
    answer: AgentAnswer,
    *,
    include_summary: bool = True,
    include_evidence_panel: bool = True,
) -> None:
    if include_summary:
        st.markdown("**Situation Summary**")
        st.write(answer.situation_summary)
    st.markdown("**Evidence**")
    for item in answer.evidence:
        st.write(f"- {item}")
    st.markdown("**Key Drivers**")
    for item in answer.key_drivers:
        st.write(f"- {item}")
    st.markdown("**Competitive Implication**")
    st.write(answer.competitive_implication)
    st.markdown("**Recommended Monitoring Actions**")
    for item in answer.recommended_monitoring_actions:
        st.write(f"- {item}")
    st.markdown("**Confidence Level**")
    st.write(answer.confidence_level)
    if include_evidence_panel:
        _render_evidence_panel(answer)
    st.caption(
        f"Generation mode: {answer.generation_mode} · Provider: "
        f"{answer.provider_name} · Evidence SHA-256: {answer.evidence_sha256[:12]}…"
    )


def _render_evidence_panel(answer: AgentAnswer) -> None:
    st.markdown("**Evidence Panel**")
    if not answer.evidence_records:
        st.info("insufficient_data")
        return
    rows = [
        {
            "Evidence Source": item.evidence_source,
            "Metric Name": item.metric_name,
            "Value": item.value,
            "Timestamp": item.timestamp,
            "Vehicle": item.vehicle_key,
        }
        for item in answer.evidence_records
    ]
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        height=min(420, 36 + 35 * min(len(rows), 11)),
    )
    st.caption(
        "Evidence is read-only. Listing inventory is not vehicle sales, and "
        "asking prices are not transaction prices."
    )


def _render_metric_references(
    answer: AgentAnswer,
    metric_names: tuple[str, ...],
) -> None:
    lookup = {item.metric_name: item for item in answer.evidence_records}
    with st.container(horizontal=True):
        for metric_name in metric_names:
            record = lookup.get(metric_name)
            value = record.value if record is not None else "insufficient_data"
            st.metric(metric_name, value, border=True)


def _suggested_questions(
    report: DailyMarketIntelligence | None,
) -> tuple[str, ...]:
    if report is None or not report.vehicles:
        return (
            "What evidence is currently available?",
            "What are the main market risks?",
        )
    scored = tuple(report.quantitative_scores)
    pressure = max(
        scored,
        key=lambda item: (
            (item.price_pressure.score or 0) + (item.inventory_pressure.score or 0)
        ),
    )
    ranked = sorted(
        report.vehicles,
        key=lambda item: item.opportunity_score.score,
        reverse=True,
    )
    comparison = (
        f"Compare {vehicle_key(ranked[0].brand, ranked[0].model)} and "
        f"{vehicle_key(ranked[1].brand, ranked[1].model)}."
        if len(ranked) >= 2
        else f"Assess {vehicle_key(ranked[0].brand, ranked[0].model)}."
    )
    return (
        f"Why is {pressure.vehicle_key} under pressure?",
        "Which vehicles have the highest opportunity?",
        comparison,
        "What are the main market risks?",
    )


def _alert_label(alert: MarketAlert) -> str:
    return f"{alert.level} · {alert.vehicle_key} · {alert.alert_type}"


def _report_signature(report: DailyMarketIntelligence) -> str:
    content_feed = get_dashboard_data_paths().content_feed
    try:
        stat = content_feed.stat()
        content_stat: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        content_stat = None
    payload = {
        "date": report.report_date.isoformat(),
        "content_feed_signature": content_stat,
        "ai_provider": os.getenv("AI_PROVIDER", "local").strip().casefold(),
        "vehicles": [
            {
                "vehicle": vehicle_key(item.brand, item.model),
                "metrics": asdict(item.metrics),
                "opportunity": item.opportunity_score.score,
            }
            for item in report.vehicles
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
