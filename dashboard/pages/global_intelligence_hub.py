"""Global Automotive Intelligence Hub backed by the read-only content feed."""

from __future__ import annotations

from datetime import date

import streamlit as st
from components.page_header import render_page_header
from services.content_feed import (
    ContentFeed,
    ContentFeedError,
    ContentRecord,
    clear_content_feed_cache,
    filter_content,
    load_content_feed,
    match_market_metrics,
)
from services.external_intelligence import (
    build_live_hub_sections,
    live_external_enabled,
    load_live_external_collection,
)
from services.intelligence import DailyMarketIntelligence

from ai.intelligence.providers import ExternalQuery
from external_intelligence.live_providers import LiveExternalCollection

_SELECTED_KEY = "global_intelligence_selected_content"


def render(intelligence: DailyMarketIntelligence | None) -> None:
    """Render the modification-aware content center without database writes."""

    render_page_header(
        title="Global Automotive Intelligence Hub",
        subtitle=(
            "A verified content center for global automotive news, official "
            "reports, and public videos."
        ),
    )
    st.button(
        "Refresh content",
        key="global_intelligence_refresh_content",
        icon=":material/refresh:",
        on_click=_clear_hub_caches,
    )
    try:
        feed = load_content_feed()
    except ContentFeedError as exc:
        st.error(str(exc), icon=":material/error:")
        return
    live_collection: LiveExternalCollection | None = None
    try:
        if live_external_enabled():
            brands = (
                tuple(dict.fromkeys(item.brand for item in intelligence.vehicles))
                if intelligence is not None
                else ()
            )
            vehicles = (
                tuple(f"{item.brand} {item.model}" for item in intelligence.vehicles)
                if intelligence is not None
                else ()
            )
            with st.spinner("Refreshing live external intelligence…"):
                live_collection = _load_live_external(brands, vehicles)
        else:
            st.caption(
                "Live providers are disabled in Demo Mode or by runtime setting; "
                "the bundled validated Content Feed remains available."
            )
    except (OSError, RuntimeError, ValueError) as exc:
        st.warning(
            f"Live external intelligence is unavailable: {exc}. "
            "Showing the last validated Content Feed.",
            icon=":material/cloud_off:",
        )
    render_feed(feed, intelligence, live_collection=live_collection)


def render_feed(
    feed: ContentFeed,
    intelligence: DailyMarketIntelligence | None,
    *,
    live_collection: LiveExternalCollection | None = None,
) -> None:
    """Render either the card grid or one internal detail view."""

    selected_id = st.session_state.get(_SELECTED_KEY)
    selected = next(
        (item for item in feed.items if item.content_id == selected_id),
        None,
    )
    if selected is not None:
        _render_detail(selected, intelligence)
        return

    _render_summary(feed)
    _render_external_intelligence_views(feed, live_collection)
    if not feed.items:
        st.info("insufficient_data")
        return
    filters = _render_filters(feed)
    filtered = filter_content(feed.items, **filters)
    st.caption(f"Showing {len(filtered)} of {len(feed.items)} verified source items")
    if not filtered:
        st.info("No verified content matches the current filters.")
        return
    _render_grid(filtered)


def _render_summary(feed: ContentFeed) -> None:
    with st.container(horizontal=True):
        st.metric("News", feed.counts.get("news", 0), border=True)
        st.metric("Report", feed.counts.get("report", 0), border=True)
        st.metric("Video", feed.counts.get("video", 0), border=True)
        st.metric("Report date", feed.report_date.isoformat(), border=True)
    st.caption(
        f"Feed updated: {feed.generated_at:%Y-%m-%d %H:%M UTC} · "
        "Cache invalidates automatically on file mtime/size changes · "
        "Manual refresh available · Metadata, short summaries, and source links only"
    )


def _render_external_intelligence_views(
    feed: ContentFeed,
    live_collection: LiveExternalCollection | None,
) -> None:
    """Show four source-backed live views above the unchanged content grid."""

    sections = build_live_hub_sections(
        feed.items,
        () if live_collection is None else live_collection.evidence,
    )
    st.subheader("Live External Intelligence")
    columns = st.columns(4)
    section_data = (
        (
            "Latest Automotive News",
            sections.latest_automotive_news,
            "Recent attributed automotive market news.",
        ),
        (
            "Policy Updates",
            sections.policy_updates,
            "Official policy and regulation source metadata.",
        ),
        (
            "Brand Intelligence",
            sections.brand_intelligence,
            "Official or validated brand-attributed updates.",
        ),
        (
            "Industry Signals",
            sections.industry_signals,
            "Industry reports and official public-data context.",
        ),
    )
    for column, (title, items, description) in zip(
        columns,
        section_data,
        strict=True,
    ):
        with column, st.container(border=True):
            st.markdown(f"### {title}")
            st.caption(description)
            st.metric("Available evidence", len(items))
            if not items:
                st.caption("insufficient_data")
                continue
            for item in items[:3]:
                st.markdown(f"**{item.title}**")
                st.caption(f"Source: {item.source}")
                st.caption(
                    f"Date: {item.published_date[:10]} · "
                    f"Category: {item.category.replace('_', ' ')} · "
                    f"Reliability: {item.reliability:.0f}/100"
                )
    if live_collection is not None:
        statuses = " · ".join(
            f"{item.provider_kind}: {item.status}" for item in live_collection.providers
        )
        st.caption(
            f"Live fetch: {live_collection.fetched_at:%Y-%m-%d %H:%M UTC} · "
            f"{statuses}"
        )
        failed = tuple(
            source
            for provider in live_collection.providers
            for source in provider.failed_sources
        )
        if failed:
            st.warning(
                "Isolated live source failures: " + ", ".join(sorted(set(failed))),
                icon=":material/warning:",
            )


@st.cache_data(ttl="15m", max_entries=4, show_spinner=False)
def _load_live_external(
    brands: tuple[str, ...],
    vehicles: tuple[str, ...],
) -> LiveExternalCollection:
    """Cache expensive public-source retrieval independently from filters."""

    return load_live_external_collection(
        ExternalQuery(query="", brands=brands, vehicles=vehicles, limit=48)
    )


def _clear_hub_caches() -> None:
    """Safely clear artifact and live caches for the explicit refresh action."""

    clear_content_feed_cache()
    _load_live_external.clear()


def _render_filters(feed: ContentFeed) -> dict[str, object]:
    items = feed.items
    with st.expander("Content filters", expanded=True):
        first = st.columns((1.6, 1, 1, 1))
        keyword = first[0].text_input(
            "Keyword",
            placeholder="Title, summary, brand, vehicle, or topic",
        )
        content_types = tuple(
            first[1].multiselect(
                "Content type", _options(item.content_type for item in items)
            )
        )
        sources = tuple(
            first[2].multiselect("Source", _options(item.source_name for item in items))
        )
        impact_levels = tuple(
            first[3].multiselect(
                "Impact level", _options(item.impact_level for item in items)
            )
        )
        second = st.columns(5)
        brands = tuple(
            second[0].multiselect(
                "Brand",
                _options(v for item in items for v in item.brands),
            )
        )
        vehicles = tuple(
            second[1].multiselect(
                "Vehicle", _options(v for item in items for v in item.vehicles)
            )
        )
        regions = tuple(
            second[2].multiselect("Region", _options(item.region for item in items))
        )
        topics = tuple(
            second[3].multiselect(
                "Topic",
                _options(v for item in items for v in item.topics),
            )
        )
        date_range = second[4].date_input(
            "Date range",
            value=(min(item.published_at.date() for item in items), feed.report_date),
            max_value=date.today(),
        )
    start_date: date | None = None
    end_date: date | None = None
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    return {
        "keyword": keyword,
        "content_types": content_types,
        "sources": sources,
        "brands": brands,
        "vehicles": vehicles,
        "regions": regions,
        "topics": topics,
        "impact_levels": impact_levels,
        "start_date": start_date,
        "end_date": end_date,
    }


def _render_grid(items: tuple[ContentRecord, ...]) -> None:
    for offset in range(0, len(items), 3):
        columns = st.columns(3)
        for column, item in zip(columns, items[offset : offset + 3], strict=False):
            with column, st.container(border=True, height=460):
                if item.thumbnail_url:
                    st.image(item.thumbnail_url, width="stretch")
                st.caption(
                    f"{item.content_type.upper()} · {item.impact_level.upper()} IMPACT"
                )
                st.subheader(item.title)
                st.caption(f"{item.source_name} · {item.published_at:%Y-%m-%d}")
                st.write(_card_summary(item.summary))
                tags = (*item.brands, *item.vehicles, *item.topics)
                if tags:
                    st.markdown(" ".join(f"`{tag}`" for tag in tags[:6]))
                st.button(
                    "View details",
                    key=f"content_detail_{item.content_id}",
                    width="stretch",
                    icon=":material/open_in_new:",
                    on_click=_select_content,
                    args=(item.content_id,),
                )


def _render_detail(
    item: ContentRecord,
    intelligence: DailyMarketIntelligence | None,
) -> None:
    st.button(
        "Back to content hub",
        icon=":material/arrow_back:",
        on_click=_clear_selected_content,
    )
    st.caption(f"{item.content_type.upper()} · {item.impact_level.upper()} IMPACT")
    st.title(item.title)
    st.caption(f"{item.source_name} · {item.published_at:%Y-%m-%d %H:%M UTC}")
    if item.content_type == "video" and item.video_id:
        st.video(f"https://www.youtube.com/watch?v={item.video_id}")
    with st.container(border=True):
        st.subheader("AI / rules-based summary")
        st.write(item.ai_summary or item.summary)
        st.caption(f"generation mode: {item.summary_mode}")
    with st.container(border=True):
        st.subheader("Related market metrics")
        validation = match_market_metrics(item, intelligence)
        if validation is None:
            st.info("No market data validation available")
        else:
            columns = st.columns(4)
            columns[0].metric("Current listing count", validation.active_listing_count)
            columns[1].metric(
                "7-day price change",
                _percent(validation.price_change_7d_pct),
            )
            columns[2].metric("Inventory change", validation.inventory_change_7d_count)
            columns[3].metric(
                "Opportunity Score",
                f"{validation.opportunity_score:.2f}",
            )
            st.caption(f"Exact vehicle match: {validation.vehicle_name}")
    with st.container(border=True):
        st.subheader("Evidence & metadata")
        st.json(
            {
                "content_id": item.content_id,
                "content_type": item.content_type,
                "source_name": item.source_name,
                "published_at": item.published_at.isoformat(),
                "collected_at": item.collected_at.isoformat(),
                "language": item.language,
                "region": item.region,
                "brands": item.brands,
                "vehicles": item.vehicles,
                "topics": item.topics,
                "impact_level": item.impact_level,
                "evidence_status": item.evidence_status,
            }
        )
        _render_external_link(item)


def _render_external_link(item: ContentRecord) -> None:
    if item.content_type == "report":
        st.link_button(
            "View official report / file",
            item.document_url or item.source_url,
            icon=":material/description:",
        )
    elif item.content_type == "video":
        st.link_button(
            "Watch on YouTube",
            item.source_url,
            icon=":material/play_circle:",
        )
    else:
        st.link_button(
            "Read original article",
            item.source_url,
            icon=":material/article:",
        )


def _options(values: object) -> list[str]:
    return sorted({str(value) for value in values if str(value)})


def _percent(value: float | None) -> str:
    return "Insufficient data" if value is None else f"{value:+.2f}%"


def _card_summary(summary: str, *, limit: int = 260) -> str:
    """Keep the card action visible while the detail retains full evidence."""

    compact = " ".join(summary.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1].rstrip()}…"


def _select_content(content_id: str) -> None:
    """Persist a selected content ID before Streamlit reruns the fragment."""

    st.session_state[_SELECTED_KEY] = content_id


def _clear_selected_content() -> None:
    """Clear the selected content ID before returning to the grid."""

    st.session_state.pop(_SELECTED_KEY, None)
