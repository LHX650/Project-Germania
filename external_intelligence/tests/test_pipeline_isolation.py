"""Guard the Phase 8C content layer from production collection dependencies."""

from __future__ import annotations

from pathlib import Path


def test_content_hub_has_no_automatic_collection_dependency() -> None:
    root = Path(__file__).resolve().parents[2]
    phase_files = (
        root / "external_intelligence" / "content_feed.py",
        root / "dashboard" / "services" / "content_feed.py",
        root / "dashboard" / "pages" / "global_intelligence_hub.py",
    )
    forbidden = (
        "daily_market_monitor",
        "autoscout24",
        "marketplace_collection",
        "create_database_engine",
        "create_session_factory",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in phase_files)
    assert not any(name in combined for name in forbidden)
