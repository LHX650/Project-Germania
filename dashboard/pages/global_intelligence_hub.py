"""Global Intelligence page backed by the read-only content feed."""

from __future__ import annotations

from datetime import date
from html import escape

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
    resolve_thumbnail_url,
)
from services.external_intelligence import (
    ContentCoverageSummary,
    calculate_content_coverage,
    content_category,
    live_external_enabled,
    merge_external_content,
    request_live_external_refresh,
)
from services.intelligence import DailyMarketIntelligence

from ai.intelligence.providers import ExternalQuery
from external_intelligence.live_providers import LiveExternalCollection
from external_intelligence.live_refresh import LiveRefreshState
from external_intelligence.vehicle_catalog import (
    MonitoredVehicle,
    load_monitored_vehicles,
)

_SELECTED_KEY = "global_intelligence_selected_content"
_FORCE_REFRESH_KEY = "global_intelligence_force_live_refresh"


def render(intelligence: DailyMarketIntelligence | None) -> None:
    """Render the modification-aware content center without database writes."""

    render_page_header(
        title="Global Intelligence",
        subtitle=(
            "Review verified automotive news, policy updates, brand activity, "
            "industry reports, and public videos."
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
    try:
        monitored_vehicles = load_monitored_vehicles()
    except (OSError, ValueError) as exc:
        st.warning(
            f"Monitored vehicle coverage is unavailable: {exc}",
            icon=":material/warning:",
        )
        monitored_vehicles = ()
    live_collection: LiveExternalCollection | None = None
    live_state: LiveRefreshState | None = None
    try:
        if live_external_enabled():
            brands = tuple(dict.fromkeys(item.brand for item in monitored_vehicles))
            vehicles = tuple(item.display_name for item in monitored_vehicles)
            force_refresh = bool(st.session_state.pop(_FORCE_REFRESH_KEY, False))
            live_state = request_live_external_refresh(
                ExternalQuery(query="", brands=brands, vehicles=vehicles, limit=48),
                force=force_refresh,
            )
            live_collection = live_state.collection
            if live_state.refreshing:
                st.caption(
                    "Live sources are updating in the background. Existing verified "
                    "content and the last successful cache remain available."
                )
            elif live_state.error_message and live_collection is not None:
                st.caption(
                    "The latest live-source check was incomplete. The last successful "
                    "cached intelligence remains available."
                )
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
    render_feed(
        feed,
        intelligence,
        live_collection=live_collection,
        live_state=live_state,
        monitored_vehicles=monitored_vehicles,
    )


def render_feed(
    feed: ContentFeed,
    intelligence: DailyMarketIntelligence | None,
    *,
    live_collection: LiveExternalCollection | None = None,
    live_state: LiveRefreshState | None = None,
    monitored_vehicles: tuple[MonitoredVehicle, ...] | None = None,
) -> None:
    """Render either the card grid or one internal detail view."""

    catalog = (
        load_monitored_vehicles() if monitored_vehicles is None else monitored_vehicles
    )
    items = merge_external_content(
        feed.items,
        () if live_collection is None else live_collection.evidence,
    )
    selected_id = st.session_state.get(_SELECTED_KEY)
    selected = next(
        (item for item in items if item.content_id == selected_id),
        None,
    )
    if selected is not None:
        _render_detail(selected, intelligence)
        return

    coverage = calculate_content_coverage(items, catalog)
    _render_summary(feed, coverage, len(catalog))
    channel = _render_external_intelligence_views(
        items,
        live_collection,
        live_state,
        coverage,
    )
    if not items:
        st.info("insufficient_data")
        return
    channel_items = _channel_items(items, channel)
    filters = _render_filters(items, feed.report_date)
    filtered = filter_content(channel_items, **filters)
    st.caption(
        f"Showing {len(filtered)} of {len(channel_items)} verified source items "
        f"in {channel}"
    )
    if not filtered:
        st.info(
            "insufficient_data — no reliable recent content matches this "
            "category and filter selection."
        )
        return
    _render_grid(filtered)


def _render_summary(
    feed: ContentFeed,
    coverage: ContentCoverageSummary,
    monitored_vehicle_count: int,
) -> None:
    latest_update = (
        coverage.latest_update.strftime("%Y-%m-%d %H:%M UTC")
        if coverage.latest_update is not None
        else "insufficient_data"
    )
    summary_items = (
        ("Brands Covered", len(coverage.brands_covered)),
        (
            "Vehicles Covered",
            f"{len(coverage.vehicles_covered)} / {monitored_vehicle_count}",
        ),
        ("Active Sources", len(coverage.active_sources)),
        ("Latest Update", latest_update),
    )
    status_markup = "".join(
        "<div class='executive-status-item'>"
        f"<span>{escape(str(label))}</span>"
        f"<strong>{escape(str(value))}</strong>"
        "</div>"
        for label, value in summary_items
    )
    st.markdown(
        f"<div class='executive-status-bar'>{status_markup}</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Validated Feed date {feed.report_date.isoformat()} · "
        "Refreshes automatically when the Feed file changes · "
        "Metadata, short summaries, and source links only"
    )


def _render_external_intelligence_views(
    items: tuple[ContentRecord, ...],
    live_collection: LiveExternalCollection | None,
    live_state: LiveRefreshState | None,
    coverage: ContentCoverageSummary,
) -> str:
    """Render the five business channels and supporting source availability."""

    channels = ("All", "Vehicles", "Brands", "Policy", "Industry")
    st.subheader("Intelligence feed")
    channel = st.segmented_control(
        "Intelligence channel",
        options=channels,
        default="All",
        key="global_intelligence_channel",
    )
    counts = " · ".join(
        f"{name}: {len(_channel_items(items, name))}" for name in channels
    )
    st.caption(counts)
    with st.expander("Source availability and supporting details"):
        coverage_rows = [
            {
                "Vehicle": row.vehicle.display_name,
                "Brand": row.vehicle.brand,
                "Coverage": row.status,
                "Items": row.item_count,
                "Latest content": (
                    row.latest_published_at.date().isoformat()
                    if row.latest_published_at is not None
                    else "insufficient_data"
                ),
            }
            for row in coverage.vehicles
        ]
        if coverage_rows:
            st.dataframe(
                coverage_rows,
                hide_index=True,
                width="stretch",
                column_config={"Vehicle": st.column_config.TextColumn(pinned=True)},
            )
        st.caption(
            "Coverage includes only exact configured brand or vehicle matches. "
            "No unrelated content is used to fill missing coverage."
        )
        if live_collection is not None:
            live_rows = [
                {
                    "Source": item.source,
                    "Date": item.published_date[:10],
                    "Category": item.category.replace("_", " ").title(),
                    "Reliability": f"{item.reliability}/100",
                }
                for item in live_collection.evidence
            ]
            if live_rows:
                st.dataframe(
                    live_rows,
                    hide_index=True,
                    width="stretch",
                    column_config={"Source": st.column_config.TextColumn(pinned=True)},
                )
        provider_rows = _provider_status_rows(live_collection, live_state)
        if provider_rows:
            st.dataframe(
                provider_rows,
                hide_index=True,
                width="stretch",
                column_config={"Provider": st.column_config.TextColumn(pinned=True)},
            )
            statuses = " · ".join(
                f"{item['Provider']}: {item['Status']}" for item in provider_rows
            )
            checked_at = (
                live_collection.fetched_at
                if live_collection is not None
                else live_state.last_attempt_at if live_state is not None else None
            )
            checked_text = (
                checked_at.strftime("%Y-%m-%d %H:%M UTC")
                if checked_at is not None
                else "insufficient_data"
            )
            st.caption(f"Live source check: {checked_text} · {statuses}")
        status_items = (
            live_state.provider_statuses
            if live_state is not None and live_state.provider_statuses
            else live_collection.providers if live_collection is not None else ()
        )
        if status_items:
            failed = tuple(
                source
                for provider in status_items
                for source in provider.failed_sources
            )
            if failed:
                st.warning(
                    "Unavailable sources: " + ", ".join(sorted(set(failed))),
                    icon=":material/warning:",
                )
            insufficient_sources = tuple(
                source
                for provider in status_items
                for source in provider.insufficient_sources
            )
            if insufficient_sources:
                st.info(
                    "No reliable recent automotive content: "
                    + ", ".join(sorted(set(insufficient_sources)))
                )
    return str(channel or "All")


def _channel_items(
    items: tuple[ContentRecord, ...],
    channel: str,
) -> tuple[ContentRecord, ...]:
    """Apply a presentation-only channel view over validated Feed items."""

    if channel == "All":
        return items
    return tuple(item for item in items if content_category(item) == channel)


def _clear_hub_caches() -> None:
    """Reload the Feed and request one safe background live refresh."""

    clear_content_feed_cache()
    st.session_state[_FORCE_REFRESH_KEY] = True


def _provider_status_rows(
    collection: LiveExternalCollection | None,
    state: LiveRefreshState | None,
) -> list[dict[str, str]]:
    """Map technical outcomes to the four supported availability labels."""

    cached_kinds = {
        item.provider_kind
        for item in (() if collection is None else collection.providers)
        if item.evidence
    }
    statuses = (
        state.provider_statuses
        if state is not None and state.provider_statuses
        else collection.providers if collection is not None else ()
    )
    rows = []
    for item in statuses:
        raw_status = item.status.casefold()
        if (
            state is not None
            and state.refreshing
            and item.provider_kind in cached_kinds
        ):
            label = "Cached"
        elif raw_status == "available":
            label = "Available"
        elif raw_status == "partial":
            label = "Partial"
        elif item.provider_kind in cached_kinds:
            label = "Cached"
        else:
            label = "Unavailable"
        rows.append(
            {
                "Provider": item.provider_kind.replace("_", " ").title(),
                "Status": label,
                "Available sources": ", ".join(item.successful_sources) or "—",
                "Unavailable sources": ", ".join(item.failed_sources) or "—",
            }
        )
    return rows


def _render_filters(
    items: tuple[ContentRecord, ...],
    report_date: date,
) -> dict[str, object]:
    with st.expander("Content filters", expanded=False):
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
            value=(min(item.published_at.date() for item in items), report_date),
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
        columns = st.columns(3, gap="small", border=True)
        for column, item in zip(columns, items[offset : offset + 3], strict=False):
            with column:
                st.markdown(
                    '<span class="intelligence-content-card" '
                    'aria-hidden="true"></span>',
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"{item.content_type.upper()} · "
                    f"{item.impact_level.upper()} IMPACT"
                )
                _render_card_media(item)
                st.subheader(item.title)
                st.caption(
                    f"{item.source_name} · {item.published_at:%Y-%m-%d} · "
                    f"Reliability: {item.evidence_status.replace('_', ' ').title()}"
                )
                st.markdown(
                    '<div class="intelligence-card-summary">'
                    f"{escape(_compact_text(item.summary))}"
                    "</div>",
                    unsafe_allow_html=True,
                )
                tags = (*item.brands, *item.vehicles, *item.topics)
                st.markdown(
                    _render_card_tags(tags[:6]),
                    unsafe_allow_html=True,
                )
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
        st.subheader("Intelligence summary")
        st.write(item.ai_summary or item.summary)
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
    with st.expander("Source and supporting information"):
        st.subheader("Content metadata")
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
                "summary_mode": item.summary_mode,
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


def _render_card_media(item: ContentRecord) -> None:
    """Render a fixed-ratio image with a browser-safe placeholder fallback."""

    image_url = resolve_thumbnail_url(item)
    media_icon = "play_circle" if item.content_type == "video" else "article"
    media_label = "Public video" if item.content_type == "video" else "No source image"
    placeholder = _media_placeholder(
        media_icon, media_label, hidden=image_url is not None
    )
    if image_url is None:
        st.html(f'<div class="intelligence-card-media">{placeholder}</div>')
        return
    safe_url = escape(image_url, quote=True)
    safe_title = escape(item.title, quote=True)
    st.html(
        '<div class="intelligence-card-media">'
        f'<img src="{safe_url}" alt="{safe_title}" loading="lazy" '
        'decoding="async" referrerpolicy="strict-origin-when-cross-origin">'
        f"{placeholder}</div>"
        "<script>(() => {"
        "const script=document.currentScript;"
        "const root=script?.previousElementSibling;"
        "const image=root?.querySelector('img');"
        "const fallback=root?.querySelector('.intelligence-card-media-placeholder');"
        "if(!image||!fallback){return;}"
        "const showFallback=()=>{image.hidden=true;"
        "image.setAttribute('aria-hidden','true');fallback.hidden=false;};"
        "image.addEventListener('error',showFallback,{once:true});"
        "if(image.complete&&image.naturalWidth===0){showFallback();}"
        "})();</script>",
        unsafe_allow_javascript=True,
    )


def _media_placeholder(icon: str, label: str, *, hidden: bool) -> str:
    hidden_attribute = " hidden" if hidden else ""
    return (
        f'<div class="intelligence-card-media-placeholder"{hidden_attribute} '
        f'role="img" aria-label="{escape(label, quote=True)}">'
        '<span class="material-symbols-rounded">'
        f"{escape(icon)}</span><span>{escape(label)}</span></div>"
    )


def _options(values: object) -> list[str]:
    return sorted({str(value) for value in values if str(value)})


def _percent(value: float | None) -> str:
    return "Insufficient data" if value is None else f"{value:+.2f}%"


def _compact_text(value: str) -> str:
    """Normalize card copy while retaining the complete detail-page evidence."""

    return " ".join(value.split())


def _render_card_tags(tags: tuple[str, ...]) -> str:
    """Render escaped tags in a height-constrained card region."""

    if not tags:
        return '<div class="intelligence-card-tags" aria-label="No tags"></div>'
    chips = "".join(
        f'<span class="intelligence-card-tag">{escape(tag)}</span>' for tag in tags
    )
    return f'<div class="intelligence-card-tags">{chips}</div>'


def _select_content(content_id: str) -> None:
    """Persist a selected content ID before Streamlit reruns the fragment."""

    st.session_state[_SELECTED_KEY] = content_id


def _clear_selected_content() -> None:
    """Clear the selected content ID before returning to the grid."""

    st.session_state.pop(_SELECTED_KEY, None)
