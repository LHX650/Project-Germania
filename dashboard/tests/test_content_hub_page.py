"""Streamlit rendering tests for the global intelligence content center."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

DASHBOARD_DIR = Path(__file__).resolve().parents[1]


def test_card_grid_detail_and_external_link_render() -> None:
    app = AppTest.from_string(_app_source("news"), default_timeout=10).run()
    _assert_no_remove_child_error(app)
    assert "Verified card title" in [item.value for item in app.subheader]
    markdown = {str(item.value) for item in app.markdown}
    assert "### Latest Automotive News" in markdown
    assert "### Policy Updates" in markdown
    assert "### Brand Intelligence" in markdown
    assert "### Industry Signals" in markdown
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
    app.button[0].click().run()
    _assert_no_remove_child_error(app)
    assert len(app.get("video")) == 1
    links = app.get("link_button")
    assert [(item.label, item.url) for item in links] == [
        ("Watch on YouTube", "https://www.youtube.com/watch?v=abcdefghijk")
    ]


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
    visible = "\n".join(str(item.value) for item in app.caption)
    assert "Source: European Commission" in visible
    assert "Date: 2026-08-07" in visible
    assert "Category: policy regulation" in visible
    assert "Reliability: 100/100" in visible


def test_content_hub_has_no_timed_fragment() -> None:
    source = (DASHBOARD_DIR / "pages" / "global_intelligence_hub.py").read_text(
        encoding="utf-8"
    )

    assert "@st.fragment" not in source
    assert "run_every" not in source


def test_empty_hub_shows_insufficient_data_without_filter_failure() -> None:
    app = AppTest.from_string(_empty_app_source(), default_timeout=10).run()

    assert not app.exception
    assert "insufficient_data" in {str(item.value) for item in app.info}
    assert not app.text_input


def _app_source(content_type: str) -> str:
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
    thumbnail_url=None,
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


def _assert_no_remove_child_error(app: AppTest) -> None:
    assert not app.exception
    assert not any("removeChild" in str(item.value) for item in app.exception)
