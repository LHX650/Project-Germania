from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from germania.collectors.autoscout24 import (
    AutoScout24Collector,
    AutoScout24MultiModelCollectionPipeline,
    clear_source_run_states,
)
from germania.collectors.exceptions import (
    CollectorAccessDeniedError,
    RequestBudgetExceeded,
)
from germania.config import CollectionTask
from germania.config.playwright import PlaywrightSettings, load_playwright_config
from germania.db import (
    Base,
    CollectionBatch,
    MarketplaceListing,
    MarketplaceListingObservation,
    MarketplacePriceHistory,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from germania.db.repositories import BaseRepository
from germania.db.seed import seed_configuration


@pytest.fixture(autouse=True)
def _isolate_source_run_states() -> None:
    clear_source_run_states()
    yield
    clear_source_run_states()


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
            assert dry_result.matching.matched == 8
            assert dry_result.matching.rejected == 0
            assert dry_result.matching.low_confidence == 0
            assert dry_result.inserted == 8
            assert BaseRepository(session, MarketplaceListing).count() == 0
            assert dry_manager.new_page_count == 2
            assert dry_manager.page is not None
            assert dry_manager.page.close_count == 1

            import_manager = FakeBrowserManager()
            imported = _pipeline(session, import_manager).run(
                tasks,
                raw_html_dir=tmp_path / "import",
                mode="import",
                run_id="phase2-first",
            )
            assert imported.failed_tasks == 0
            assert imported.run_id == "phase2-first"
            assert imported.parsed == 8
            assert imported.matching.matched == 8
            assert imported.inserted == 8
            assert imported.rejected == 0
            assert imported.price_history_inserted == 8
            assert imported.observations_inserted == 8
            assert imported.page_success_rate == 1.0
            assert [task.task_id for task in imported.tasks] == [
                "volkswagen_golf",
                "tesla_model_y",
            ]
            assert BaseRepository(session, MarketplaceListing).count() == 8
            assert BaseRepository(session, MarketplacePriceHistory).count() == 8
            assert BaseRepository(session, MarketplaceListingObservation).count() == 8
            batches = list(
                session.scalars(
                    select(CollectionBatch).order_by(
                        CollectionBatch.collection_batch_id
                    )
                )
            )
            assert [batch.collection_job_id for batch in batches] == [
                "phase2-first",
                "phase2-first",
            ]
            assert [batch.status for batch in batches] == ["completed", "completed"]
            assert [batch.record_count for batch in batches] == [4, 4]
            assert [batch.success_count for batch in batches] == [4, 4]
            assert [batch.failure_count for batch in batches] == [0, 0]
            assert all(batch.started_at is not None for batch in batches)
            assert all(batch.completed_at is not None for batch in batches)
            batch_notes = [json.loads(batch.notes or "{}") for batch in batches]
            assert [notes["task_id"] for notes in batch_notes] == [
                "volkswagen_golf",
                "tesla_model_y",
            ]
            assert all(notes["page_success_rate"] == 1.0 for notes in batch_notes)
            observations = list(
                session.scalars(
                    select(MarketplaceListingObservation).order_by(
                        MarketplaceListingObservation.marketplace_listing_observation_id
                    )
                )
            )
            assert all(
                observation.collection_batch_id is not None
                for observation in observations
            )
            assert all(
                observation.listing_status == "active" for observation in observations
            )
            assert all(
                observation.listed_price is not None for observation in observations
            )
            assert all(observation.mileage_km == 20_000 for observation in observations)
            assert import_manager.new_page_count == 2
            assert import_manager.page is not None
            assert len(import_manager.page.goto_urls) == 4
            assert import_manager.page.close_count == 1
            assert import_manager.close_count == 1

            repeat_manager = FakeBrowserManager()
            repeated = _pipeline(session, repeat_manager).run(
                tasks,
                raw_html_dir=tmp_path / "repeat",
                mode="import",
                run_id="phase2-second",
            )
            assert repeated.inserted == 0
            assert repeated.updated + repeated.skipped == 8
            assert repeated.price_history_inserted == 0
            assert repeated.observations_inserted == 8
            assert BaseRepository(session, MarketplaceListing).count() == 8
            assert BaseRepository(session, MarketplacePriceHistory).count() == 8
            assert BaseRepository(session, MarketplaceListingObservation).count() == 16
            assert BaseRepository(session, CollectionBatch).count() == 4
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_multi_model_import_isolates_failed_task_and_finalizes_batches(
    tmp_path: Path,
) -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    tasks = (
        _task("volkswagen_golf", "Volkswagen", "Golf", 1),
        _task("tesla_model_y", "Tesla", "Model Y", 1),
    )

    try:
        with session_scope(session_factory) as session:
            seed_configuration(session)
            browser_manager = FakeBrowserManager(failing_paths={"/volkswagen/golf"})
            result = _pipeline(session, browser_manager).run(
                tasks,
                raw_html_dir=tmp_path / "isolated-failure",
                mode="import",
                run_id="phase2-isolation",
            )

            assert result.requested_tasks == 2
            assert result.succeeded_tasks == 1
            assert result.failed_tasks == 1
            assert result.succeeded_pages == 1
            assert result.failed_pages == 1
            assert result.observations_inserted == 2
            assert [task.succeeded for task in result.tasks] == [False, True]
            batches = list(
                session.scalars(
                    select(CollectionBatch).order_by(
                        CollectionBatch.collection_batch_id
                    )
                )
            )
            assert [batch.status for batch in batches] == ["failed", "completed"]
            assert BaseRepository(session, MarketplaceListing).count() == 2
            assert BaseRepository(session, MarketplaceListingObservation).count() == 2
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_multi_model_rejects_page_plan_above_request_budget(
    tmp_path: Path,
) -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    settings = load_playwright_config(environ={})
    source_override = settings.source_overrides["autoscout24_de"]
    settings = replace(
        settings,
        source_overrides={
            **settings.source_overrides,
            "autoscout24_de": replace(
                source_override,
                max_requests_per_run=1,
            ),
        },
    )

    try:
        with session_scope(session_factory) as session:
            seed_configuration(session)
            browser_manager = FakeBrowserManager()
            collector = AutoScout24Collector(
                playwright_settings=settings,
                browser_manager=browser_manager,
            )
            pipeline = AutoScout24MultiModelCollectionPipeline(collector, session)

            with pytest.raises(RequestBudgetExceeded, match="requested_pages=2"):
                pipeline.run(
                    (_task("volkswagen_golf", "Volkswagen", "Golf", 2),),
                    raw_html_dir=tmp_path / "over-budget",
                    mode="dry_run",
                )

            assert collector.request_count == 0
            assert browser_manager.new_page_count == 0
            assert browser_manager.close_count == 1
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
            assert browser_manager.new_page_count == 2
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_access_denied_preflight_opens_shared_circuit_and_preserves_old_data(
    tmp_path: Path,
) -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    task = _task("volkswagen_golf", "Volkswagen", "Golf", 1)

    try:
        with session_scope(session_factory) as session:
            seed_configuration(session)
            baseline_manager = FakeBrowserManager()
            baseline = _pipeline(session, baseline_manager).run(
                (task,),
                raw_html_dir=tmp_path / "baseline",
                mode="import",
                run_id="baseline-run",
            )
            assert baseline.inserted == 2
            before = (
                BaseRepository(session, MarketplaceListing).count(),
                BaseRepository(session, MarketplaceListingObservation).count(),
                BaseRepository(session, MarketplacePriceHistory).count(),
            )

            denied_manager = FakeBrowserManager(access_denied_paths={"/"})
            with pytest.raises(CollectorAccessDeniedError, match="HTTP 403"):
                _pipeline(session, denied_manager).run(
                    (task,),
                    raw_html_dir=tmp_path / "denied",
                    mode="import",
                    run_id="shared-denied-run",
                )

            assert denied_manager.new_page_count == 1
            assert denied_manager.pages[0].goto_urls == ["https://www.autoscout24.de/"]
            assert not list((tmp_path / "denied").rglob("*.html"))
            assert before == (
                BaseRepository(session, MarketplaceListing).count(),
                BaseRepository(session, MarketplaceListingObservation).count(),
                BaseRepository(session, MarketplacePriceHistory).count(),
            )

            retry_manager = FakeBrowserManager()
            with pytest.raises(CollectorAccessDeniedError, match="HTTP 403"):
                _pipeline(session, retry_manager).run(
                    (task,),
                    raw_html_dir=tmp_path / "retry",
                    mode="import",
                    run_id="shared-denied-run",
                )
            assert retry_manager.new_page_count == 0
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_first_listing_403_stops_current_batch_and_remaining_tasks(
    tmp_path: Path,
) -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    tasks = (
        _task("volkswagen_golf", "Volkswagen", "Golf", 3),
        _task("tesla_model_y", "Tesla", "Model Y", 1),
    )

    try:
        with session_scope(session_factory) as session:
            seed_configuration(session)
            browser_manager = FakeBrowserManager(
                access_denied_paths={"/lst/volkswagen/golf"}
            )
            result = _pipeline(session, browser_manager).run(
                tasks,
                raw_html_dir=tmp_path / "listing-denied",
                mode="import",
                run_id="listing-denied-run",
            )

            assert result.succeeded_tasks == 0
            assert result.failed_tasks == 2
            assert result.succeeded_pages == 0
            assert result.failed_pages == 4
            assert browser_manager.new_page_count == 2
            requested_urls = [
                url for page in browser_manager.pages for url in page.goto_urls
            ]
            assert requested_urls == [
                "https://www.autoscout24.de/",
                "https://www.autoscout24.de/lst/volkswagen/golf",
            ]
            assert BaseRepository(session, MarketplaceListing).count() == 0
            assert BaseRepository(session, MarketplaceListingObservation).count() == 0
            assert BaseRepository(session, MarketplacePriceHistory).count() == 0
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_source_request_budget_is_shared_across_cohorts(tmp_path: Path) -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    settings = load_playwright_config(environ={})
    settings = replace(
        settings,
        requests=replace(settings.requests, max_requests_per_run=3),
    )
    task = _task("volkswagen_golf", "Volkswagen", "Golf", 1)

    try:
        with session_scope(session_factory) as session:
            seed_configuration(session)
            first_manager = FakeBrowserManager()
            first = _pipeline(session, first_manager, settings=settings).run(
                (task,),
                raw_html_dir=tmp_path / "cohort-a",
                mode="dry_run",
                run_id="shared-budget-run",
            )
            assert first.succeeded_pages == 1
            assert first_manager.new_page_count == 2

            second_manager = FakeBrowserManager()
            second = _pipeline(session, second_manager, settings=settings).run(
                (task,),
                raw_html_dir=tmp_path / "cohort-b",
                mode="dry_run",
                run_id="shared-budget-run",
            )
            assert second.succeeded_pages == 1
            assert second_manager.new_page_count == 1

            exhausted_manager = FakeBrowserManager()
            with pytest.raises(RequestBudgetExceeded, match="remaining_budget=0"):
                _pipeline(session, exhausted_manager, settings=settings).run(
                    (task,),
                    raw_html_dir=tmp_path / "cohort-c",
                    mode="dry_run",
                    run_id="shared-budget-run",
                )
            assert exhausted_manager.new_page_count == 0
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
    *,
    settings: PlaywrightSettings | None = None,
) -> AutoScout24MultiModelCollectionPipeline:
    collector = AutoScout24Collector(
        playwright_settings=settings or load_playwright_config(environ={}),
        browser_manager=browser_manager,
        request_sleeper=lambda _: None,
    )
    return AutoScout24MultiModelCollectionPipeline(collector, session)


class FakeBrowserManager:
    def __init__(
        self,
        *,
        failing_paths: set[str] | None = None,
        access_denied_paths: set[str] | None = None,
    ) -> None:
        self.failing_paths = failing_paths or set()
        self.access_denied_paths = access_denied_paths or set()
        self.new_page_count = 0
        self.close_count = 0
        self.page: FakePage | None = None
        self.pages: list[FakePage] = []

    def new_page(self) -> FakePage:
        self.new_page_count += 1
        self.page = FakePage(
            failing_paths=self.failing_paths,
            access_denied_paths=self.access_denied_paths,
        )
        self.pages.append(self.page)
        return self.page

    def close(self) -> None:
        self.close_count += 1


class FakePage:
    def __init__(
        self,
        *,
        failing_paths: set[str],
        access_denied_paths: set[str],
    ) -> None:
        self.failing_paths = failing_paths
        self.access_denied_paths = access_denied_paths
        self.goto_urls: list[str] = []
        self.current_html = ""
        self.url = ""
        self.close_count = 0

    def set_default_navigation_timeout(self, timeout_ms: int) -> None:
        assert timeout_ms == 30000

    def set_default_timeout(self, timeout_ms: int) -> None:
        assert timeout_ms == 10000

    def route(self, pattern: str, handler: object) -> None:
        assert pattern == "**/*"

    def goto(
        self,
        url: str,
        *,
        wait_until: str,
        timeout: int,
    ) -> FakeResponse:
        assert wait_until == "domcontentloaded"
        assert timeout == 30000
        self.goto_urls.append(url)
        self.url = url
        parsed = urlparse(url)
        if parsed.path in self.access_denied_paths:
            return FakeResponse(
                403,
                {"server": "test-edge", "set-cookie": "private-value"},
            )
        if any(parsed.path.endswith(path) for path in self.failing_paths):
            raise RuntimeError(f"simulated task failure: {parsed.path}")
        page = int(parse_qs(parsed.query).get("page", ["1"])[0])
        brand, model = _vehicle_from_path(parsed.path)
        self.current_html = _listing_page_html(brand, model, page)
        return FakeResponse(200, {"server": "test-origin"})

    def content(self) -> str:
        return self.current_html

    def close(self) -> None:
        self.close_count += 1


class FakeResponse:
    def __init__(self, status: int, headers: dict[str, str]) -> None:
        self.status = status
        self._headers = headers

    def all_headers(self) -> dict[str, str]:
        return self._headers


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
