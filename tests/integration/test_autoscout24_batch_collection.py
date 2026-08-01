from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sqlalchemy.orm import Session

from germania.collectors.autoscout24 import (
    AutoScout24BatchCollectionPipeline,
    AutoScout24Collector,
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


def test_batch_collection_dry_run_imports_and_repeats_idempotently(
    tmp_path: Path,
) -> None:
    pages = {
        1: _listing_page_html(1),
        2: _listing_page_html(2),
        3: _listing_page_html(3),
        4: _listing_page_html(4),
    }
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    try:
        with session_scope(session_factory) as session:
            seed_configuration(session)

            dry_manager = FakeBrowserManager(pages)
            dry_result = _pipeline(session, dry_manager).run(
                SearchConfig(brand="Volkswagen", model="Golf"),
                raw_html_dir=tmp_path / "dry-run",
                mode="dry_run",
            )

            assert dry_result.requested_pages == 3
            assert dry_result.succeeded_pages == 3
            assert dry_result.failed_pages == 0
            assert dry_result.parsed == 60
            assert dry_result.matching.matched == 60
            assert dry_result.matching.rejected == 0
            assert dry_result.matching.low_confidence == 0
            assert dry_result.import_result.inserted == 60
            assert BaseRepository(session, MarketplaceListing).count() == 0
            assert BaseRepository(session, MarketplacePriceHistory).count() == 0
            assert dry_manager.new_page_count == 1
            assert dry_manager.page is not None
            assert dry_manager.page.close_count == 1
            assert dry_manager.page.resource_actions == [
                ("image", "abort"),
                ("font", "abort"),
                ("script", "continue"),
            ]
            assert dry_manager.close_count == 1

            import_manager = FakeBrowserManager(pages, failing_pages={2})
            imported = _pipeline(session, import_manager).run(
                SearchConfig(brand="Volkswagen", model="Golf"),
                raw_html_dir=tmp_path / "import",
                max_pages=4,
                mode="import",
            )

            assert imported.requested_pages == 4
            assert imported.succeeded_pages == 3
            assert imported.failed_pages == 1
            assert imported.parsed == 60
            assert imported.matching.matched == 60
            assert imported.import_result.total == 60
            assert imported.import_result.inserted == 60
            assert imported.import_result.rejected == 0
            assert imported.import_result.price_history_inserted == 60
            assert BaseRepository(session, MarketplaceListing).count() == 60
            assert BaseRepository(session, MarketplacePriceHistory).count() == 60
            assert import_manager.new_page_count == 1
            assert import_manager.page is not None
            assert len(import_manager.page.goto_urls) == 4
            assert import_manager.page.close_count == 1
            assert import_manager.close_count == 1
            assert (tmp_path / "import" / "page_002.html").exists() is False

            repeat_manager = FakeBrowserManager(pages, failing_pages={2})
            repeated = _pipeline(session, repeat_manager).run(
                SearchConfig(brand="Volkswagen", model="Golf"),
                raw_html_dir=tmp_path / "repeat",
                max_pages=4,
                mode="import",
            )

            assert repeated.succeeded_pages == 3
            assert repeated.failed_pages == 1
            assert repeated.import_result.inserted == 0
            assert repeated.import_result.rejected == 0
            assert repeated.import_result.price_history_inserted == 0
            assert BaseRepository(session, MarketplaceListing).count() == 60
            assert BaseRepository(session, MarketplacePriceHistory).count() == 60
            assert repeat_manager.new_page_count == 1
            assert repeat_manager.close_count == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _pipeline(
    session: Session,
    browser_manager: FakeBrowserManager,
) -> AutoScout24BatchCollectionPipeline:
    collector = AutoScout24Collector(
        playwright_settings=load_playwright_config(environ={}),
        browser_manager=browser_manager,
    )
    return AutoScout24BatchCollectionPipeline(collector, session)


def _listing_page_html(page: int) -> str:
    listings = "\n".join(
        _listing_card(page, listing_index) for listing_index in range(20)
    )
    return f"<!doctype html><html><body><main>{listings}</main></body></html>"


def _listing_card(page: int, listing_index: int) -> str:
    listing_id = f"as24-golf-p{page:03d}-{listing_index:02d}"
    price = 20_000 + (page * 100) + listing_index
    return f"""
      <article data-testid="listing-card" data-listing-id="{listing_id}">
        <a data-field="url" href="/angebote/volkswagen-golf-{listing_id}">
          <span data-field="title">Volkswagen Golf Batch {page}-{listing_index}</span>
          <span data-field="brand">Volkswagen</span>
          <span data-field="model">Golf</span>
        </a>
        <span data-field="variant">Life</span>
        <span data-field="price">{price} EUR</span>
        <span data-field="registration">EZ 03/2021</span>
        <span data-field="mileage">42.000 km</span>
        <span data-field="fuel_type">Benzin</span>
        <span data-field="transmission">Automatik</span>
        <span data-field="power">110 kW</span>
        <span data-field="location">DE-10115 Berlin</span>
        <span data-field="seller_type">dealer</span>
        <span data-field="seller_name">Batch Autohaus</span>
      </article>
    """


class FakeBrowserManager:
    def __init__(
        self,
        pages: dict[int, str],
        *,
        failing_pages: set[int] | None = None,
    ) -> None:
        self.pages = pages
        self.failing_pages = failing_pages or set()
        self.new_page_count = 0
        self.close_count = 0
        self.page: FakePage | None = None

    def new_page(self) -> FakePage:
        self.new_page_count += 1
        self.page = FakePage(self.pages, failing_pages=self.failing_pages)
        return self.page

    def close(self) -> None:
        self.close_count += 1


class FakePage:
    def __init__(
        self,
        pages: dict[int, str],
        *,
        failing_pages: set[int],
    ) -> None:
        self.pages = pages
        self.failing_pages = failing_pages
        self.goto_urls: list[str] = []
        self.resource_actions: list[tuple[str, str]] = []
        self.current_html = ""
        self.close_count = 0

    def set_default_navigation_timeout(self, timeout_ms: int) -> None:
        assert timeout_ms == 30000

    def set_default_timeout(self, timeout_ms: int) -> None:
        assert timeout_ms == 10000

    def route(self, pattern: str, handler: object) -> None:
        assert pattern == "**/*"
        for resource_type in ("image", "font", "script"):
            route = FakeRoute(resource_type)
            handler(route)
            assert route.action is not None
            self.resource_actions.append((resource_type, route.action))

    def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        assert wait_until == "domcontentloaded"
        assert timeout == 30000
        self.goto_urls.append(url)
        page = _page_from_url(url)
        if page in self.failing_pages:
            raise RuntimeError(f"simulated page failure: {page}")
        self.current_html = self.pages[page]

    def content(self) -> str:
        return self.current_html

    def close(self) -> None:
        self.close_count += 1


class FakeRoute:
    def __init__(self, resource_type: str) -> None:
        self.request = FakeRequest(resource_type)
        self.action: str | None = None

    def abort(self) -> None:
        self.action = "abort"

    def continue_(self) -> None:
        self.action = "continue"


class FakeRequest:
    def __init__(self, resource_type: str) -> None:
        self.resource_type = resource_type


def _page_from_url(url: str) -> int:
    query = parse_qs(urlparse(url).query)
    return int(query.get("page", ["1"])[0])
