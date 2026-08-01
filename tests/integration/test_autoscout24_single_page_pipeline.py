from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from germania.collectors.autoscout24 import (
    AutoScout24Collector,
    AutoScout24SinglePagePipeline,
    SearchConfig,
)
from germania.config.playwright import load_playwright_config
from germania.db import (
    Base,
    MarketplaceListing,
    MarketplacePriceHistory,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from germania.db.repositories import BaseRepository
from germania.db.seed import seed_configuration

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "autoscout24"
    / "fixture_pipeline.html"
)


def test_single_page_pipeline_supports_dry_run_import_and_idempotency(
    tmp_path: Path,
) -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    try:
        with session_scope(session_factory) as session:
            seed_configuration(session)

            dry_manager = FakeBrowserManager(html)
            dry_result = _pipeline(session, dry_manager).run(
                SearchConfig(brand="Volkswagen", model="Golf"),
                raw_html_path=tmp_path / "dry-run.html",
                mode="dry_run",
            )
            assert dry_result.parsed == 6
            assert dry_result.matching.matched == 4
            assert dry_result.matching.rejected == 0
            assert dry_result.matching.low_confidence == 2
            assert dry_result.import_result.inserted == 2
            assert BaseRepository(session, MarketplaceListing).count() == 0
            assert BaseRepository(session, MarketplacePriceHistory).count() == 0
            assert dry_manager.close_count == 1

            import_manager = FakeBrowserManager(html)
            imported = _pipeline(session, import_manager).run(
                SearchConfig(brand="Volkswagen", model="Golf"),
                raw_html_path=tmp_path / "import.html",
                mode="import",
            )
            assert imported.parsed == 6
            assert imported.import_result.inserted == 2
            assert imported.import_result.price_history_inserted == 2
            assert BaseRepository(session, MarketplaceListing).count() == 2
            assert BaseRepository(session, MarketplacePriceHistory).count() == 2
            assert import_manager.close_count == 1

            repeat_manager = FakeBrowserManager(html)
            repeated = _pipeline(session, repeat_manager).run(
                SearchConfig(brand="Volkswagen", model="Golf"),
                raw_html_path=tmp_path / "repeat.html",
                mode="import",
            )
            assert repeated.import_result.inserted == 0
            assert repeated.import_result.updated == 2
            assert repeated.import_result.skipped == 0
            assert repeated.import_result.price_history_inserted == 0
            assert BaseRepository(session, MarketplaceListing).count() == 2
            assert BaseRepository(session, MarketplacePriceHistory).count() == 2
            assert repeat_manager.close_count == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _pipeline(
    session: Session,
    browser_manager: FakeBrowserManager,
) -> AutoScout24SinglePagePipeline:
    collector = AutoScout24Collector(
        playwright_settings=load_playwright_config(environ={}),
        browser_manager=browser_manager,
    )
    return AutoScout24SinglePagePipeline(collector, session)


class FakeBrowserManager:
    def __init__(self, html: str) -> None:
        self.html = html
        self.close_count = 0

    def new_page(self) -> FakePage:
        return FakePage(self.html)

    def close(self) -> None:
        self.close_count += 1


class FakePage:
    def __init__(self, html: str) -> None:
        self.html = html
        self.closed = False

    def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        assert url.startswith("https://www.autoscout24.de/lst/volkswagen/golf?")
        assert wait_until == "domcontentloaded"
        assert timeout == 30000

    def content(self) -> str:
        return self.html

    def close(self) -> None:
        self.closed = True
