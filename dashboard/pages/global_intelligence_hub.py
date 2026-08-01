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
from services.intelligence import DailyMarketIntelligence

_SELECTED_KEY = "global_intelligence_selected_content"


def render(intelligence: DailyMarketIntelligence | None) -> None:
    """Render the modification-aware content center without database writes."""

    render_page_header(
        title="Global Automotive Intelligence Hub",
        subtitle="全球汽车新闻、官方报告与公开视频的可验证内容中心。",
    )
    st.button(
        "刷新内容",
        key="global_intelligence_refresh_content",
        icon=":material/refresh:",
        on_click=clear_content_feed_cache,
    )
    try:
        feed = load_content_feed()
    except ContentFeedError as exc:
        st.error(str(exc), icon=":material/error:")
        return
    render_feed(feed, intelligence)


def render_feed(
    feed: ContentFeed,
    intelligence: DailyMarketIntelligence | None,
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
    filters = _render_filters(feed)
    filtered = filter_content(feed.items, **filters)
    st.caption(f"显示 {len(filtered)} / {len(feed.items)} 条真实来源内容")
    if not filtered:
        st.info("当前筛选条件下没有可验证内容。")
        return
    _render_grid(filtered)


def _render_summary(feed: ContentFeed) -> None:
    with st.container(horizontal=True):
        st.metric("News", feed.counts.get("news", 0), border=True)
        st.metric("Report", feed.counts.get("report", 0), border=True)
        st.metric("Video", feed.counts.get("video", 0), border=True)
        st.metric("报告日期", feed.report_date.isoformat(), border=True)
    st.caption(
        f"Feed 更新：{feed.generated_at:%Y-%m-%d %H:%M UTC} · "
        "缓存按文件 mtime/size 自动失效 · 可手动刷新 · "
        "仅展示元数据、短摘要与原始链接"
    )


def _render_filters(feed: ContentFeed) -> dict[str, object]:
    items = feed.items
    with st.expander("筛选内容", expanded=True):
        first = st.columns((1.6, 1, 1, 1))
        keyword = first[0].text_input(
            "关键词",
            placeholder="标题、摘要、品牌、车型或主题",
        )
        content_types = tuple(
            first[1].multiselect(
                "内容类型", _options(item.content_type for item in items)
            )
        )
        sources = tuple(
            first[2].multiselect("来源", _options(item.source_name for item in items))
        )
        impact_levels = tuple(
            first[3].multiselect(
                "影响等级", _options(item.impact_level for item in items)
            )
        )
        second = st.columns(5)
        brands = tuple(
            second[0].multiselect(
                "品牌",
                _options(v for item in items for v in item.brands),
            )
        )
        vehicles = tuple(
            second[1].multiselect(
                "车型", _options(v for item in items for v in item.vehicles)
            )
        )
        regions = tuple(
            second[2].multiselect("区域", _options(item.region for item in items))
        )
        topics = tuple(
            second[3].multiselect(
                "主题",
                _options(v for item in items for v in item.topics),
            )
        )
        date_range = second[4].date_input(
            "时间范围",
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
                    "查看详情",
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
        "返回内容中心",
        icon=":material/arrow_back:",
        on_click=_clear_selected_content,
    )
    st.caption(f"{item.content_type.upper()} · {item.impact_level.upper()} IMPACT")
    st.title(item.title)
    st.caption(f"{item.source_name} · {item.published_at:%Y-%m-%d %H:%M UTC}")
    if item.content_type == "video" and item.video_id:
        st.video(f"https://www.youtube.com/watch?v={item.video_id}")
    with st.container(border=True):
        st.subheader("AI / 规则摘要")
        st.write(item.ai_summary or item.summary)
        st.caption(f"generation mode: {item.summary_mode}")
    with st.container(border=True):
        st.subheader("关联市场指标")
        validation = match_market_metrics(item, intelligence)
        if validation is None:
            st.info("暂无市场数据验证")
        else:
            columns = st.columns(4)
            columns[0].metric("当前挂牌量", validation.active_listing_count)
            columns[1].metric(
                "7日价格变化",
                _percent(validation.price_change_7d_pct),
            )
            columns[2].metric("库存变化", validation.inventory_change_7d_count)
            columns[3].metric(
                "Opportunity Score",
                f"{validation.opportunity_score:.2f}",
            )
            st.caption(f"精确关联车型：{validation.vehicle_name}")
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
            "查看官方报告 / 文件",
            item.document_url or item.source_url,
            icon=":material/description:",
        )
    elif item.content_type == "video":
        st.link_button(
            "在 YouTube 观看",
            item.source_url,
            icon=":material/play_circle:",
        )
    else:
        st.link_button(
            "阅读原文",
            item.source_url,
            icon=":material/article:",
        )


def _options(values: object) -> list[str]:
    return sorted({str(value) for value in values if str(value)})


def _percent(value: float | None) -> str:
    return "数据不足" if value is None else f"{value:+.2f}%"


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
