"""Streamlit rendering tests for the global intelligence content center."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

DASHBOARD_DIR = Path(__file__).resolve().parents[1]


def test_card_grid_detail_and_external_link_render() -> None:
    app = AppTest.from_string(_app_source("news"), default_timeout=10).run()
    _assert_no_remove_child_error(app)
    assert "Verified card title" in [item.value for item in app.subheader]
    summary = "\n".join(str(item.value) for item in app.markdown)
    assert all(
        label in summary
        for label in (
            "Brands Covered",
            "Vehicles Covered",
            "Active Sources",
            "Latest Update",
        )
    )
    assert "Source availability and supporting details" in {
        item.label for item in app.expander
    }
    source = (DASHBOARD_DIR / "pages" / "global_intelligence_hub.py").read_text(
        encoding="utf-8"
    )
    assert 'channels = ("All", "Vehicles", "Brands", "Policy", "Industry")' in source
    assert any(
        "Reliability: Verified Source" in str(item.value) for item in app.caption
    )
    assert [item.label for item in app.button] == ["View details"]

    app.button[0].click().run()
    _assert_no_remove_child_error(app)
    assert [item.value for item in app.title] == ["Verified card title"]
    assert [item.value for item in app.info] == ["No market data validation available"]
    links = app.get("link_button")
    assert [(item.label, item.url) for item in links] == [
        ("Read original article", "https://example.org/news")
    ]
    assert [item.label for item in app.button] == ["Back to content hub"]

    app.button[0].click().run()
    _assert_no_remove_child_error(app)
    assert "Verified card title" in [item.value for item in app.subheader]
    assert [item.label for item in app.button] == ["View details"]


def test_youtube_detail_embeds_public_video() -> None:
    app = AppTest.from_string(_app_source("video"), default_timeout=10).run()
    media = app.get("html")[0].proto.body
    assert "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg" in media
    assert "Public video" in media
    assert "addEventListener('error'" in media
    assert not app.image
    app.button[0].click().run()
    _assert_no_remove_child_error(app)
    assert len(app.get("video")) == 1
    links = app.get("link_button")
    assert [(item.label, item.url) for item in links] == [
        ("Watch on YouTube", "https://www.youtube.com/watch?v=abcdefghijk")
    ]


def test_source_thumbnail_and_no_image_fallback_render() -> None:
    with_image = AppTest.from_string(
        _app_source("news", thumbnail_url="https://cdn.example.org/cover.jpg"),
        default_timeout=10,
    ).run()
    image_markup = with_image.get("html")[0].proto.body
    assert "https://cdn.example.org/cover.jpg" in image_markup
    assert "addEventListener('error'" in image_markup

    fallback = AppTest.from_string(_app_source("news"), default_timeout=10).run()
    fallback_markup = fallback.get("html")[0].proto.body
    assert "No source image" in fallback_markup
    assert "<img" not in fallback_markup


def test_manual_refresh_clears_cache_then_reloads_feed() -> None:
    app = AppTest.from_string(_refresh_app_source(), default_timeout=10).run()
    _assert_no_remove_child_error(app)
    assert [item.label for item in app.button][:2] == [
        "Refresh content",
        "View details",
    ]
    assert "loads=1 clears=0" in [item.value for item in app.caption]

    app.button[0].click().run()

    _assert_no_remove_child_error(app)
    assert "loads=2 clears=1" in [item.value for item in app.caption]


def test_live_policy_evidence_displays_source_date_category_and_reliability() -> None:
    app = AppTest.from_string(_live_app_source(), default_timeout=10).run()

    assert not app.exception
    tables = [item.value for item in app.dataframe]
    live_table = next(table for table in tables if "Reliability" in table.columns)
    assert live_table.to_dict("records") == [
        {
            "Source": "European Commission",
            "Date": "2026-08-07",
            "Category": "Policy Regulation",
            "Reliability": "100/100",
        }
    ]


def test_content_hub_has_no_timed_fragment() -> None:
    source = (DASHBOARD_DIR / "pages" / "global_intelligence_hub.py").read_text(
        encoding="utf-8"
    )

    assert "@st.fragment" not in source
    assert "run_every" not in source


def test_live_refresh_is_background_only_and_cached_feed_renders() -> None:
    app = AppTest.from_string(_isolated_live_app_source(), default_timeout=10).run()

    _assert_no_remove_child_error(app)
    assert "Verified card title" in [item.value for item in app.subheader]
    assert "Cached live item" in [item.value for item in app.subheader]
    assert any("updating in the background" in str(item.value) for item in app.caption)
    provider_table = next(
        item.value
        for item in app.dataframe
        if {"Provider", "Status"}.issubset(item.value.columns)
    )
    assert provider_table.to_dict("records")[0]["Status"] == "Cached"

    source = (DASHBOARD_DIR / "pages" / "global_intelligence_hub.py").read_text(
        encoding="utf-8"
    )
    assert "Refreshing live external intelligence" not in source
    assert "st.spinner" not in source


def test_manual_live_refresh_failure_keeps_cached_and_feed_content() -> None:
    app = AppTest.from_string(_isolated_live_app_source(), default_timeout=10).run()

    app.button[0].click().run()

    _assert_no_remove_child_error(app)
    titles = [item.value for item in app.subheader]
    assert "Verified card title" in titles
    assert "Cached live item" in titles
    assert "force=True calls=2" in [item.value for item in app.caption]


def test_provider_statuses_use_only_supported_availability_labels() -> None:
    from datetime import UTC, datetime

    from pages.global_intelligence_hub import _provider_status_rows

    from external_intelligence.live_providers import (
        LiveExternalCollection,
        LiveProviderResult,
    )
    from external_intelligence.live_refresh import (
        LiveRefreshState,
        ProviderRefreshStatus,
    )

    cached = _external_evidence_fixture()
    collection = LiveExternalCollection(
        fetched_at=datetime(2026, 8, 8, tzinfo=UTC),
        evidence=(cached,),
        providers=(
            LiveProviderResult(
                provider_name="cached",
                provider_kind="cached_kind",
                status="available",
                evidence=(cached,),
                successful_sources=("Cached source",),
                failed_sources=(),
            ),
        ),
    )
    state = LiveRefreshState(
        collection=collection,
        provider_statuses=tuple(
            ProviderRefreshStatus(
                provider_kind=kind,
                status=status,
                successful_sources=("Source",) if status != "failed" else (),
                failed_sources=("Failed",) if status == "failed" else (),
                insufficient_sources=(),
                errors=(),
            )
            for kind, status in (
                ("available_kind", "available"),
                ("partial_kind", "partial"),
                ("unavailable_kind", "failed"),
                ("cached_kind", "failed"),
            )
        ),
        last_attempt_at=datetime(2026, 8, 8, tzinfo=UTC),
        error_message=None,
    )

    rows = _provider_status_rows(collection, state)

    assert [row["Status"] for row in rows] == [
        "Available",
        "Partial",
        "Unavailable",
        "Cached",
    ]


def test_content_cards_define_equal_height_responsive_layout_contract() -> None:
    page_source = (DASHBOARD_DIR / "pages" / "global_intelligence_hub.py").read_text(
        encoding="utf-8"
    )
    style_source = (DASHBOARD_DIR / "theme" / "styles.py").read_text(encoding="utf-8")

    assert 'st.columns(3, gap="small", border=True)' in page_source
    assert "intelligence-content-card" in page_source
    assert "intelligence-card-media-placeholder" in page_source
    assert "intelligence-card-media" in page_source
    assert "unsafe_allow_javascript=True" in page_source
    assert "intelligence-card-summary" in page_source
    assert "intelligence-card-tags" in page_source
    assert "object-fit: cover" in style_source
    assert "-webkit-line-clamp: 3" in style_source
    assert "-webkit-line-clamp: 4" in style_source
    assert "margin-top: auto" in style_source
    assert "@media (max-width: 420px)" in style_source


def test_empty_hub_shows_insufficient_data_without_filter_failure() -> None:
    app = AppTest.from_string(_empty_app_source(), default_timeout=10).run()

    assert not app.exception
    assert "insufficient_data" in {str(item.value) for item in app.info}
    assert not app.text_input


def test_demo_and_production_hub_use_twenty_vehicle_coverage_denominator() -> None:
    for demo_mode in (True, False):
        app = AppTest.from_string(
            _runtime_app_source(demo_mode),
            default_timeout=20,
        ).run()

        assert not app.exception
        summary = "\n".join(str(item.value) for item in app.markdown)
        assert "Vehicles Covered" in summary
        assert "/ 20" in summary
        assert app.segmented_control[0].options == [
            "All",
            "Vehicles",
            "Brands",
            "Policy",
            "Industry",
        ]
        assert {item.label for item in app.multiselect} >= {
            "Brand",
            "Vehicle",
            "Source",
        }


def _app_source(content_type: str, *, thumbnail_url: str | None = None) -> str:
    is_video = content_type == "video"
    source_url = (
        "https://www.youtube.com/watch?v=abcdefghijk"
        if is_video
        else "https://example.org/news"
    )
    return f"""
import sys
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
from datetime import UTC, date, datetime
from pathlib import Path
from pages.global_intelligence_hub import render_feed
from services.content_feed import ContentFeed, ContentRecord
item = ContentRecord(
    content_id="item-id",
    content_type={content_type!r},
    title="Verified card title",
    source_name="Official source",
    source_url={source_url!r},
    published_at=datetime(2026, 7, 31, tzinfo=UTC),
    summary="Short official metadata.",
    language="en",
    region="DE",
    brands=("BMW",),
    vehicles=(),
    topics=("market",),
    impact_level="medium",
    thumbnail_url={thumbnail_url!r},
    document_url=None,
    video_id={"'abcdefghijk'" if is_video else "None"},
    collected_at=datetime(2026, 8, 1, tzinfo=UTC),
    evidence_status="verified_source",
    ai_summary="Local rule summary.",
    summary_mode="local_rule_fallback",
)
feed = ContentFeed(
    report_date=date(2026, 8, 1),
    generated_at=datetime(2026, 8, 1, tzinfo=UTC),
    counts={{
        "news": {0 if is_video else 1},
        "report": 0,
        "video": {1 if is_video else 0},
    }},
    items=(item,),
    sources=(),
    source_path=Path("feed.json"),
)
render_feed(feed, None)
"""


def _refresh_app_source() -> str:
    return f"""
import os
import sys
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
os.environ["LIVE_EXTERNAL_INTELLIGENCE"] = "false"
from datetime import UTC, date, datetime
from pathlib import Path
import streamlit as st
import pages.global_intelligence_hub as hub
from services.content_feed import ContentFeed, ContentRecord
st.session_state.setdefault("test_feed_loads", 0)
st.session_state.setdefault("test_cache_clears", 0)
item = ContentRecord(
    content_id="refresh-item",
    content_type="news",
    title="Verified card title",
    source_name="Official source",
    source_url="https://example.org/news",
    published_at=datetime(2026, 7, 31, tzinfo=UTC),
    summary="Short official metadata.",
    language="en",
    region="DE",
    brands=("BMW",),
    vehicles=(),
    topics=("market",),
    impact_level="medium",
    thumbnail_url=None,
    document_url=None,
    video_id=None,
    collected_at=datetime(2026, 8, 1, tzinfo=UTC),
    evidence_status="verified_source",
    ai_summary="Local rule summary.",
    summary_mode="local_rule_fallback",
)
feed = ContentFeed(
    report_date=date(2026, 8, 1),
    generated_at=datetime(2026, 8, 1, tzinfo=UTC),
    counts={{"news": 1, "report": 0, "video": 0}},
    items=(item,),
    sources=(),
    source_path=Path("feed.json"),
)
def fake_clear():
    st.session_state.test_cache_clears += 1
def fake_load():
    st.session_state.test_feed_loads += 1
    return feed
hub.clear_content_feed_cache = fake_clear
hub.load_content_feed = fake_load
hub.render(None)
st.caption(
    f"loads={{st.session_state.test_feed_loads}} "
    f"clears={{st.session_state.test_cache_clears}}"
)
"""


def _live_app_source() -> str:
    return f"""
import sys
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
from datetime import UTC, date, datetime
from pathlib import Path
from ai.intelligence.models import ExternalEvidence
from external_intelligence.live_providers import (
    LiveExternalCollection,
    LiveProviderResult,
)
from pages.global_intelligence_hub import render_feed
from services.content_feed import ContentFeed
evidence = ExternalEvidence(
    source="European Commission",
    title="Official automotive regulation update",
    url="https://example.org/policy",
    published_date="2026-08-07T09:00:00+00:00",
    category="policy_regulation",
    brand=None,
    vehicle=None,
    content_summary="Official policy metadata.",
    reliability=100,
    fetched_time="2026-08-08T00:00:00+00:00",
    evidence_type="official_policy_update",
    region="EU",
)
provider = LiveProviderResult(
    provider_name="live_policy_regulation",
    provider_kind="policy_regulation",
    status="available",
    evidence=(evidence,),
    successful_sources=("European Commission",),
    failed_sources=(),
)
collection = LiveExternalCollection(
    fetched_at=datetime(2026, 8, 8, tzinfo=UTC),
    evidence=(evidence,),
    providers=(provider,),
)
feed = ContentFeed(
    report_date=date(2026, 8, 8),
    generated_at=datetime(2026, 8, 8, tzinfo=UTC),
    counts={{"news": 0, "report": 0, "video": 0}},
    items=(),
    sources=(),
    source_path=Path("feed.json"),
)
render_feed(feed, None, live_collection=collection)
"""


def _empty_app_source() -> str:
    return f"""
import sys
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
from datetime import UTC, date, datetime
from pathlib import Path
from pages.global_intelligence_hub import render_feed
from services.content_feed import ContentFeed
feed = ContentFeed(
    report_date=date(2026, 8, 8),
    generated_at=datetime(2026, 8, 8, tzinfo=UTC),
    counts={{"news": 0, "report": 0, "video": 0}},
    items=(),
    sources=(),
    source_path=Path("feed.json"),
)
render_feed(feed, None)
"""


def _runtime_app_source(demo_mode: bool) -> str:
    return f"""
import os
import sys
import importlib
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
os.environ["DEMO_MODE"] = {str(demo_mode).lower()!r}
os.environ["LIVE_EXTERNAL_INTELLIGENCE"] = "false"
import pages.global_intelligence_hub as hub
from services.content_feed import load_content_feed
importlib.reload(hub)
fixture_feed = load_content_feed(
    {str(DASHBOARD_DIR.parent / "demo" / "content_feed.json")!r}
)
hub.load_content_feed = lambda: fixture_feed
hub.render(None)
"""


def _isolated_live_app_source() -> str:
    return f"""
import os
import sys
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
os.environ["DEMO_MODE"] = "false"
os.environ["LIVE_EXTERNAL_INTELLIGENCE"] = "true"
from datetime import UTC, date, datetime
from pathlib import Path
import streamlit as st
import pages.global_intelligence_hub as hub
from ai.intelligence.models import ExternalEvidence
from external_intelligence.live_providers import (
    LiveExternalCollection,
    LiveProviderResult,
)
from external_intelligence.live_refresh import LiveRefreshState, ProviderRefreshStatus
from services.content_feed import ContentFeed, ContentRecord
st.session_state.setdefault("refresh_calls", 0)
st.session_state.setdefault("last_force", False)
feed_item = ContentRecord(
    content_id="feed-item",
    content_type="news",
    title="Verified card title",
    source_name="Existing Content Feed",
    source_url="https://example.org/feed",
    published_at=datetime(2026, 8, 7, tzinfo=UTC),
    summary="Existing verified metadata.",
    language="en",
    region="DE",
    brands=("BMW",),
    vehicles=(),
    topics=("market",),
    impact_level="medium",
    thumbnail_url=None,
    document_url=None,
    video_id=None,
    collected_at=datetime(2026, 8, 8, tzinfo=UTC),
    evidence_status="verified_source",
    ai_summary="Existing summary.",
    summary_mode="local_rule_fallback",
)
feed = ContentFeed(
    report_date=date(2026, 8, 8),
    generated_at=datetime(2026, 8, 8, tzinfo=UTC),
    counts={{"news": 1, "report": 0, "video": 0}},
    items=(feed_item,),
    sources=(),
    source_path=Path("feed.json"),
)
evidence = ExternalEvidence(
    source="Cached official source",
    title="Cached live item",
    url="https://example.org/cached",
    published_date="2026-08-07T09:00:00+00:00",
    category="automotive_news",
    brand=None,
    vehicle=None,
    content_summary="Last successful cached metadata.",
    reliability=95,
    fetched_time="2026-08-08T00:00:00+00:00",
    evidence_type="official_industry_news",
    region="EU",
)
provider = LiveProviderResult(
    provider_name="live_automotive_news",
    provider_kind="automotive_news",
    status="available",
    evidence=(evidence,),
    successful_sources=("Cached official source",),
    failed_sources=(),
)
collection = LiveExternalCollection(
    fetched_at=datetime(2026, 8, 8, tzinfo=UTC),
    evidence=(evidence,),
    providers=(provider,),
)
failed_status = ProviderRefreshStatus(
    provider_kind="automotive_news",
    status="failed",
    successful_sources=(),
    failed_sources=("Tesla Blog", "Volkswagen Newsroom", "NIO Newsroom"),
    insufficient_sources=(),
    errors=("isolated provider failures",),
)
def fake_request(query, *, force=False):
    del query
    st.session_state.refresh_calls += 1
    st.session_state.last_force = force
    return LiveRefreshState(
        collection=collection,
        provider_statuses=(failed_status,),
        last_attempt_at=datetime(2026, 8, 8, tzinfo=UTC),
        error_message="isolated provider failures",
        refreshing=True,
    )
hub.load_content_feed = lambda: feed
hub.clear_content_feed_cache = lambda: None
hub.request_live_external_refresh = fake_request
hub.render(None)
st.caption(
    f"force={{st.session_state.last_force}} calls={{st.session_state.refresh_calls}}"
)
"""


def _assert_no_remove_child_error(app: AppTest) -> None:
    assert not app.exception
    assert not any("removeChild" in str(item.value) for item in app.exception)


def _external_evidence_fixture():
    from ai.intelligence.models import ExternalEvidence

    return ExternalEvidence(
        source="Cached source",
        title="Cached item",
        url="https://example.org/cached-item",
        published_date="2026-08-07T00:00:00+00:00",
        category="automotive_news",
        brand=None,
        vehicle=None,
        content_summary="Cached verified metadata.",
        reliability=95,
        fetched_time="2026-08-08T00:00:00+00:00",
        evidence_type="official_industry_news",
        region="EU",
    )
