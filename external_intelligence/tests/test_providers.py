from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from external_intelligence.cache import ExternalIntelligenceCache
from external_intelligence.config import KBAConfig, load_config
from external_intelligence.http import HTTPResponse
from external_intelligence.kba import KBAOfficialProvider, _catalog_resource_url
from strategic.external import ExternalIntelligenceRequest, ExternalSourceStatus

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "kba"
    / "fz10_2026_06_sample.xlsx"
)


@dataclass
class FixtureFetcher:
    body: bytes
    urls: list[str] = field(default_factory=list)

    def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> HTTPResponse:
        del headers
        self.urls.append(url)
        return HTTPResponse(
            self.body,
            200,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def test_kba_provider_outputs_official_brand_model_period_json_shape(
    tmp_path: Path,
) -> None:
    fetcher = FixtureFetcher(FIXTURE.read_bytes())
    provider = KBAOfficialProvider(
        config=KBAConfig(
            enabled=True,
            source_name="KBA FZ10 fixture",
            source_page_url="https://www.kba.de/monthly",
            download_url_template="https://www.kba.de/fz10_{year}_{month:02d}.xlsx",
            period_lag_months=1,
            ttl_seconds=3600,
        ),
        cache=ExternalIntelligenceCache(tmp_path / "cache"),
        fetcher=fetcher,
    )

    snapshot = provider.fetch_registrations(
        ExternalIntelligenceRequest(
            report_date=date(2026, 7, 31),
            brands=("Volkswagen",),
            vehicles=("Volkswagen Golf",),
        )
    )

    assert snapshot.status is ExternalSourceStatus.AVAILABLE
    assert fetcher.urls == ["https://www.kba.de/fz10_2026_06.xlsx"]
    total = next(record for record in provider.records if record.fuel_type == "total")
    assert total.period == "2026-06"
    assert total.brand == "Volkswagen"
    assert total.model == "Golf"
    assert total.registrations == 1234
    assert total.country == "DE"
    assert snapshot.signals[0].metric_name == "official_new_registrations"


def test_default_config_supports_six_required_official_brand_sources() -> None:
    config = load_config()
    assert {source.brand for source in config.brand_news_sources} == {
        "Volkswagen",
        "BMW",
        "Mercedes-Benz",
        "Audi",
        "Tesla",
        "BYD",
    }
    assert all(
        source.page_url.startswith("https://") for source in config.brand_news_sources
    )


def test_kba_catalog_discovers_exact_month_resource() -> None:
    payload = {
        "success": True,
        "result": {
            "results": [
                {
                    "resources": [
                        {
                            "name": "FZ10 June 2026",
                            "url": (
                                "https://www.kba.de/downloads/" "fz10_2026_06.xlsx"
                            ),
                        }
                    ]
                }
            ]
        },
    }

    assert _catalog_resource_url(payload, 2026, 6) == (
        "https://www.kba.de/downloads/fz10_2026_06.xlsx"
    )
