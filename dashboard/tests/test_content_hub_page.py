"""Streamlit rendering tests for the global intelligence content center."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

DASHBOARD_DIR = Path(__file__).resolve().parents[1]


def test_card_grid_detail_and_external_link_render() -> None:
    app = AppTest.from_string(_app_source("news"), default_timeout=10).run()
    _assert_no_remove_child_error(app)
    assert [item.value for item in app.subheader] == ["Verified card title"]
    assert [item.label for item in app.button] == ["查看详情"]

    app.button[0].click().run()
    _assert_no_remove_child_error(app)
    assert [item.value for item in app.title] == ["Verified card title"]
    assert [item.value for item in app.info] == ["暂无市场数据验证"]
    links = app.get("link_button")
    assert [(item.label, item.url) for item in links] == [
        ("阅读原文", "https://example.org/news")
    ]
    assert [item.label for item in app.button] == ["返回内容中心"]

    app.button[0].click().run()
    _assert_no_remove_child_error(app)
    assert [item.value for item in app.subheader] == ["Verified card title"]
    assert [item.label for item in app.button] == ["查看详情"]


def test_youtube_detail_embeds_public_video() -> None:
    app = AppTest.from_string(_app_source("video"), default_timeout=10).run()
    app.button[0].click().run()
    _assert_no_remove_child_error(app)
    assert len(app.get("video")) == 1
    links = app.get("link_button")
    assert [(item.label, item.url) for item in links] == [
        ("在 YouTube 观看", "https://www.youtube.com/watch?v=abcdefghijk")
    ]


def test_manual_refresh_clears_cache_then_reloads_feed() -> None:
    app = AppTest.from_string(_refresh_app_source(), default_timeout=10).run()
    _assert_no_remove_child_error(app)
    assert [item.label for item in app.button][:2] == ["刷新内容", "查看详情"]
    assert "loads=1 clears=0" in [item.value for item in app.caption]

    app.button[0].click().run()

    _assert_no_remove_child_error(app)
    assert "loads=2 clears=1" in [item.value for item in app.caption]


def test_content_hub_has_no_timed_fragment() -> None:
    source = (DASHBOARD_DIR / "pages" / "global_intelligence_hub.py").read_text(
        encoding="utf-8"
    )

    assert "@st.fragment" not in source
    assert "run_every" not in source


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
import sys
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
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


def _assert_no_remove_child_error(app: AppTest) -> None:
    assert not app.exception
    assert not any("removeChild" in str(item.value) for item in app.exception)
