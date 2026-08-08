"""Public Demo Mode path isolation, bundle, and eight-page AppTest coverage."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

import pytest
from services.ai_report import clear_ai_report_cache, load_daily_ai_market_report
from services.content_feed import clear_content_feed_cache, load_content_feed
from services.daily_updates import (
    clear_daily_update_summary_cache,
    load_daily_update_summary,
)
from services.database import (
    get_connection,
    load_database_quality,
    search_listings,
)
from services.intelligence import (
    clear_intelligence_cache,
    load_daily_market_intelligence,
)
from services.pipeline_status import (
    clear_pipeline_status_cache,
    load_pipeline_status,
)
from services.runtime import (
    DashboardConfigurationError,
    demo_mode_enabled,
    get_dashboard_data_paths,
)
from streamlit.testing.v1 import AppTest

from germania.db import Base

DASHBOARD_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DASHBOARD_DIR.parent
DEMO_DIR = PROJECT_ROOT / "demo"
PAGE_NAMES = (
    "Executive Overview",
    "Market Alerts",
    "Vehicle Intelligence",
    "Vehicle Analysis",
    "Brand Competition",
    "Price Intelligence",
    "Global Intelligence",
    "Data Quality",
    "Listing Explorer",
)
VISIBLE_ELEMENT_TYPES = (
    "title",
    "header",
    "subheader",
    "markdown",
    "caption",
    "info",
    "warning",
    "error",
    "success",
    "metric",
    "button",
    "link_button",
    "download_button",
    "text_input",
    "number_input",
    "selectbox",
    "multiselect",
    "checkbox",
    "radio",
    "expander",
    "dataframe",
    "json",
)
CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def test_demo_mode_defaults_to_production_and_validates_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert demo_mode_enabled() is False
    production = get_dashboard_data_paths()
    assert production.demo_mode is False
    assert production.database == (
        PROJECT_ROOT / "database" / "project_germania_live.sqlite3"
    )

    monkeypatch.setenv("DEMO_MODE", "true")
    demo = get_dashboard_data_paths()
    assert demo.demo_mode is True
    assert demo.database == DEMO_DIR / "project_germania_demo.sqlite3"
    assert demo.content_feed == DEMO_DIR / "content_feed.json"

    with pytest.raises(DashboardConfigurationError, match="DEMO_MODE"):
        demo_mode_enabled("not-a-boolean")


def test_demo_bundle_is_structurally_valid_and_hash_grounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    _clear_demo_caches()
    paths = get_dashboard_data_paths()
    report = load_daily_market_intelligence()
    ai_report = load_daily_ai_market_report()
    content_feed = load_content_feed()
    pipeline = load_pipeline_status()
    quality = load_database_quality()
    updates = load_daily_update_summary()

    assert len(report.vehicles) == 6
    assert len(report.brands) == 6
    assert report.active_inventory_count == 64
    assert report.methodology["production_data"] is False
    assert ai_report.generation_mode == "demo_local_rules"
    assert (
        ai_report.evidence_sha256
        == hashlib.sha256(paths.market_intelligence.read_bytes()).hexdigest()
    )
    assert content_feed.counts == {"news": 1, "report": 1, "video": 1}
    assert pipeline.overall_status == "completed_demo"
    assert pipeline.stages["executive_brief"] == "not_available"
    assert quality.listings_count == 64
    assert quality.observations_count == 192
    assert quality.price_history_count == 128
    assert updates.run_id == "demo-run-20260731-public"
    assert updates.listings_scanned == 64
    assert updates.new_listings == 8
    assert updates.existing_listings_updated == 56
    assert updates.price_changes == 64
    assert updates.price_decreases == 64
    assert updates.price_increases == 0
    assert updates.inactive_listings == 0
    assert updates.new_price_history_records == 64
    assert updates.vehicles_updated == 6


def test_demo_database_matches_schema_and_blocks_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    paths = get_dashboard_data_paths()
    with get_connection() as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            if row[0] != "sqlite_sequence"
        }
        assert tables == set(Base.metadata.tables)
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("UPDATE marketplace_listings SET active = 0")

    results = search_listings(active_only=False, limit=100)
    assert len(results) == 64
    assert all(item.external_listing_id.startswith("DEMO-") for item in results)
    assert all(
        item.listing_url is not None
        and "github.com/LHX650/Project-Germania" in item.listing_url
        for item in results
    )
    assert paths.database != PROJECT_ROOT / "database" / "project_germania_live.sqlite3"


def test_demo_bundle_contains_no_local_or_production_paths() -> None:
    forbidden = (
        str(PROJECT_ROOT),
        "project_germania_live.sqlite3",
        "data/raw",
        "data\\raw",
        "reports/archive",
        "reports\\archive",
    )
    for path in DEMO_DIR.iterdir():
        if path.suffix not in {".json", ".md", ".py"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert all(value not in text for value in forbidden), path.name


def test_dashboard_interface_source_contains_no_chinese_text() -> None:
    checked = tuple(
        path
        for path in DASHBOARD_DIR.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".md"}
        and "tests" not in path.parts
        and "__pycache__" not in path.parts
    )

    assert checked
    for path in checked:
        assert not CJK_PATTERN.search(path.read_text(encoding="utf-8")), path


@pytest.mark.parametrize("page_name", PAGE_NAMES)
def test_all_dashboard_pages_render_from_demo_bundle(
    page_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    _clear_demo_caches()
    app = AppTest.from_string(_demo_app_source(page_name), default_timeout=20).run()

    assert not app.exception, (page_name, app.exception)
    assert any(page_name in str(item.value) for item in app.markdown)
    assert any("Demo Mode" in str(item.value) for item in app.info)
    if page_name == "Data Quality":
        metric_labels = {item.label for item in app.metric}
        assert {
            "Listings Scanned",
            "New Listings",
            "Existing Listings Updated",
            "Price Changes",
            "Inactive / Removed Listings",
            "New Price History Records",
            "Vehicles Updated",
            "Pipeline Status",
            "Last Successful Collection",
            "Pipeline Duration",
        } <= metric_labels
        assert "Update History" in {item.value for item in app.subheader}
    _assert_english_only_ui(app, page_name)


def _demo_app_source(page_name: str) -> str:
    return f"""
import sys
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
import streamlit as st
import pages.global_intelligence_hub as hub
import pages.vehicle_analysis as vehicle_analysis
from services.content_feed import (
    clear_content_feed_cache as actual_clear_content_feed_cache,
    load_content_feed as actual_load_content_feed,
)
from services.peer_benchmarking import (
    load_peer_benchmarks as actual_load_peer_benchmarks,
)
hub.clear_content_feed_cache = actual_clear_content_feed_cache
hub.load_content_feed = actual_load_content_feed
vehicle_analysis.load_content_feed = actual_load_content_feed
vehicle_analysis.load_peer_benchmarks = actual_load_peer_benchmarks
st.session_state["project_germania_navigation"] = {page_name!r}
import app
app.main()
"""


def _clear_demo_caches() -> None:
    clear_intelligence_cache()
    clear_ai_report_cache()
    clear_content_feed_cache()
    clear_pipeline_status_cache()
    clear_daily_update_summary_cache()


def _assert_english_only_ui(app: AppTest, page_name: str) -> None:
    visible_text: list[str] = []
    for element_type in VISIBLE_ELEMENT_TYPES:
        for element in app.get(element_type):
            for attribute in ("value", "label", "placeholder", "help"):
                try:
                    value = getattr(element, attribute, None)
                except KeyError:
                    continue
                if value is not None:
                    visible_text.append(str(value))
    assert not [text for text in visible_text if CJK_PATTERN.search(text)], page_name
