"""Static guards for the shared Phase 11 visual and responsive system."""

from __future__ import annotations

from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parents[1]


def test_shared_visual_system_has_explicit_390px_layout_support() -> None:
    source = (DASHBOARD_DIR / "theme" / "styles.py").read_text(encoding="utf-8")

    assert "@media (max-width: 420px)" in source
    assert '[data-testid="stHorizontalBlock"]' in source
    assert "flex-wrap: wrap !important" in source
    assert '[data-testid="column"]' in source
    assert "min-width: 100% !important" in source
    assert "radial-gradient" not in source
    assert "@keyframes" not in source


def test_all_eight_visible_pages_use_the_shared_page_header() -> None:
    page_files = (
        "executive_overview.py",
        "global_intelligence_hub.py",
        "vehicle_intelligence.py",
        "brand_competition.py",
        "price_intelligence.py",
        "vehicle_analysis.py",
        "search_center.py",
        "data_quality.py",
    )

    for name in page_files:
        source = (DASHBOARD_DIR / "pages" / name).read_text(encoding="utf-8")
        assert "render_page_header" in source, name


def test_phase_11_model_has_no_collection_or_pipeline_dependency() -> None:
    source = (
        DASHBOARD_DIR.parent
        / "src"
        / "germania"
        / "analytics"
        / "quantitative_intelligence.py"
    ).read_text(encoding="utf-8")

    assert "germania.collectors" not in source
    assert "daily_market_monitor" not in source
    assert "from pipeline" not in source
    assert "database" not in source.casefold()


def test_peer_model_is_isolated_from_config_and_production_chain() -> None:
    source = (
        DASHBOARD_DIR.parent
        / "src"
        / "germania"
        / "analytics"
        / "comparable_benchmarking.py"
    ).read_text(encoding="utf-8")
    lowered = source.casefold()

    assert "collector" not in lowered
    assert "daily_market_monitor" not in lowered
    assert "pipeline" not in lowered
    assert "vehicles.yaml" not in lowered
    assert "germania.db" not in lowered


def test_vehicle_analysis_peer_region_order_and_chart_contract() -> None:
    page_source = (DASHBOARD_DIR / "pages" / "vehicle_analysis.py").read_text(
        encoding="utf-8"
    )
    component_source = (
        DASHBOARD_DIR / "components" / "peer_benchmarking.py"
    ).read_text(encoding="utf-8")

    assert page_source.index("render_quantitative_score_cards(") < page_source.index(
        "load_peer_benchmarks(report)"
    )
    assert page_source.index("load_peer_benchmarks(report)") < page_source.index(
        "_render_trends(snapshot)"
    )
    assert "datum.role === 'Target'" in component_source
    assert '"type": "rule"' in component_source
    for metric in (
        "price_gap_pct",
        "inventory_gap_pct",
        "opportunity_score_gap",
        "price_pressure_gap",
        "inventory_pressure_gap",
        "market_momentum_gap",
    ):
        assert metric in component_source
