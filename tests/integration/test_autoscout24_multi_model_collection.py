from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sqlalchemy.orm import Session

from germania.collectors.autoscout24 import (
    AutoScout24Collector,
    AutoScout24MultiModelCollectionPipeline,
)
from germania.config import CollectionTask
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


def test_multi_model_collection_reuses_page_and_is_idempotent(
    tmp_path: Path,
) -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    tasks = (
        _task("volkswagen_golf", "Volkswagen", "Golf", 2),
        _task("tesla_model_y", "Tesla", "Model Y", 2),
    )

    try:
        with session_scope(session_factory) as session:
            seed_configuration(session)

            dry_manager = FakeBrowserManager()
            dry_result = _pipeline(session, dry_manager).run(
                tasks,
                raw_html_dir=tmp_path / "dry",
                mode="dry_run",
            )
            assert dry_result.requested_tasks == 2
            assert dry_result.succeeded_tasks == 2
            assert dry_result.requested_pages == 4
            assert dry_result.succeeded_pages == 4
            assert dry_result.parsed == 8
            assert dry_result.inserted == 8
            assert BaseRepository(session, MarketplaceListing).count() == 0
            assert dry_manager.new_page_count == 1
            assert dry_manager.page is not None
            assert dry_manager.page.close_count == 1

            import_manager = FakeBrowserManager()
            imported = _pipeline(session, import_manager).run(
                tasks,
                raw_html_dir=tmp_path / "import",
                mode="import",
            )
            assert imported.failed_tasks == 0
            assert imported.parsed == 8
            assert imported.inserted == 8
            assert imported.rejected == 0
            assert imported.price_history_inserted == 8
            assert [task.task_id for task in imported.tasks] == [
                "volkswagen_golf",
                "tesla_model_y",
            ]
            assert BaseRepository(session, MarketplaceListing).count() == 8
            assert BaseRepository(session, MarketplacePriceHistory).count() == 8
            assert import_manager.new_page_count == 1
            assert import_manager.page is not None
            assert len(import_manager.page.goto_urls) == 4
            assert import_manager.page.close_count == 1
            assert import_manager.close_count == 1

            repeat_manager = FakeBrowserManager()
            repeated = _pipeline(session, repeat_manager).run(
                tasks,
                raw_html_dir=tmp_path / "repeat",
                mode="import",
            )
            assert repeated.inserted == 0
            assert repeated.updated + repeated.skipped == 8
            assert repeated.price_history_inserted == 0
            assert BaseRepository(session, MarketplaceListing).count() == 8
            assert BaseRepository(session, MarketplacePriceHistory).count() == 8
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_multi_model_collection_reports_failed_tasks(tmp_path: Path) -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    tasks = (
        _task("volkswagen_golf", "Volkswagen", "Golf", 1),
        replace(
            _task("unsupported_task", "Tesla", "Model Y", 2),
            source_id="unsupported_marketplace",
        ),
    )

    try:
        with session_scope(session_factory) as session:
            seed_configuration(session)
            browser_manager = FakeBrowserManager()
            result = _pipeline(session, browser_manager).run(
                tasks,
                raw_html_dir=tmp_path / "failed-task",
                mode="dry_run",
            )

            assert result.requested_tasks == 2
            assert result.succeeded_tasks == 1
            assert result.failed_tasks == 1
            assert result.requested_pages == 3
            assert result.succeeded_pages == 1
            assert result.failed_pages == 2
            assert result.parsed == 2
            assert result.tasks[1].error_message is not None
            assert browser_manager.new_page_count == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _task(task_id: str, brand: str, model: str, max_pages: int) -> CollectionTask:
    slug = model.casefold().replace(" ", "-")
    return CollectionTask(
        task_id=task_id,
        source_id="autoscout24_de",
        brand_name=brand,
        model_name=model,
        search_url=f"https://www.autoscout24.de/lst/{brand.casefold()}/{slug}",
        max_pages=max_pages,
        enabled=True,
        priority=1,
        notes="integration test",
    )


def _pipeline(
    session: Session,
    browser_manager: FakeBrowserManager,
) -> AutoScout24MultiModelCollectionPipeline:
    collector = AutoScout24Collector(
        playwright_settings=load_playwright_config(environ={}),
        browser_manager=browser_manager,
    )
    return AutoScout24MultiModelCollectionPipeline(collector, session)


class FakeBrowserManager:
    def __init__(self) -> None:
        self.new_page_count = 0
        self.close_count = 0
        self.page: FakePage | None = None

    def new_page(self) -> FakePage:
        self.new_page_count += 1
        self.page = FakePage()
        return self.page

    def close(self) -> None:
        self.close_count += 1


class FakePage:
    def __init__(self) -> None:
        self.goto_urls: list[str] = []
        self.current_html = ""
        self.close_count = 0

    def set_default_navigation_timeout(self, timeout_ms: int) -> None:
        assert timeout_ms == 30000

    def set_default_timeout(self, timeout_ms: int) -> None:
        assert timeout_ms == 10000

    def route(self, pattern: str, handler: object) -> None:
        assert pattern == "**/*"

    def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        assert wait_until == "domcontentloaded"
        assert timeout == 30000
        self.goto_urls.append(url)
        parsed = urlparse(url)
        page = int(parse_qs(parsed.query).get("page", ["1"])[0])
        brand, model = _vehicle_from_path(parsed.path)
        self.current_html = _listing_page_html(brand, model, page)

    def content(self) -> str:
        return self.current_html

    def close(self) -> None:
        self.close_count += 1


def _vehicle_from_path(path: str) -> tuple[str, str]:
    if path.endswith("/tesla/model-y"):
        return "Tesla", "Model Y"
    return "Volkswagen", "Golf"


def _listing_page_html(brand: str, model: str, page: int) -> str:
    cards = "".join(_listing_card(brand, model, page, index) for index in range(2))
    return f"<!doctype html><html><body>{cards}</body></html>"


def _listing_card(brand: str, model: str, page: int, index: int) -> str:
    listing_id = f"{brand}-{model}-{page}-{index}".casefold().replace(" ", "-")
    return f"""
    <article data-testid="listing-card" data-listing-id="{listing_id}">
      <a data-field="url" href="/angebote/{listing_id}">
        <span data-field="title">{brand} {model}</span>
        <span data-field="brand">{brand}</span>
        <span data-field="model">{model}</span>
      </a>
      <span data-field="price">{30000 + page + index} EUR</span>
      <span data-field="mileage">20.000 km</span>
    </article>
    """
