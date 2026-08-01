"""Official KBA FZ10 provider backed by the existing read-only XLSX parser."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date

from external_intelligence.cache import ExternalIntelligenceCache
from external_intelligence.config import KBAConfig
from external_intelligence.http import HTTPFetcher
from external_intelligence.models import KBARegistration, SourceRun
from germania.collectors.kba import parse_kba_fz10_xlsx
from strategic.external import (
    ExternalIntelligenceRequest,
    ExternalSignal,
    ExternalSourceSnapshot,
    ExternalSourceStatus,
    ExternalSourceType,
    StrategicImplication,
)

logger = logging.getLogger(__name__)


class KBAOfficialProvider:
    """Download, cache, parse, and normalize official KBA FZ10 workbooks."""

    name = "kba_official_fz10"

    def __init__(
        self,
        *,
        config: KBAConfig,
        cache: ExternalIntelligenceCache,
        fetcher: HTTPFetcher,
    ) -> None:
        self.config = config
        self.cache = cache
        self.fetcher = fetcher
        self.records: tuple[KBARegistration, ...] = ()
        self.source_runs: tuple[SourceRun, ...] = ()

    def fetch_registrations(
        self,
        request: ExternalIntelligenceRequest,
    ) -> ExternalSourceSnapshot:
        """Return tracked brand/model registration signals from official FZ10."""

        if not self.config.enabled:
            return ExternalSourceSnapshot(
                source_type=ExternalSourceType.KBA_REGISTRATIONS,
                provider_name=self.name,
                status=ExternalSourceStatus.NOT_CONFIGURED,
                limitations=("KBA provider is disabled in configuration.",),
            )
        year, month = _lagged_period(
            request.report_date,
            self.config.period_lag_months,
        )
        source_url = self._download_url(year, month)
        entry = self.cache.get_or_fetch(
            source_id=f"kba_fz10_{year}_{month:02d}",
            source_url=source_url,
            ttl_seconds=self.config.ttl_seconds,
            fetcher=self.fetcher,
        )
        parsed = parse_kba_fz10_xlsx(
            entry.payload_path,
            year=year,
            month=month,
            source_url=source_url,
            collected_at=entry.fetched_at,
        )
        tracked = _tracked_vehicle_keys(request)
        records = []
        for item in parsed:
            if not _in_scope(item.brand, item.model_series, request, tracked):
                continue
            records.append(
                KBARegistration(
                    period=f"{item.year:04d}-{item.month:02d}",
                    brand=item.brand,
                    model=item.model_series,
                    registrations=item.registrations,
                    fuel_type=item.fuel_type,
                    country="DE",
                    source=self.config.source_name,
                    source_url=item.source_url or source_url,
                    retrieved_at=entry.fetched_at,
                )
            )
        self.records = tuple(records)
        limitation = (
            "Expired cached KBA data was used because refresh failed."
            if entry.cache_status == "stale_fallback"
            else None
        )
        self.source_runs = (
            SourceRun(
                source_id=f"kba_fz10_{year}_{month:02d}",
                source=self.config.source_name,
                source_url=source_url,
                status="available",
                cache_status=entry.cache_status,
                updated_at=entry.fetched_at,
                ttl_seconds=self.config.ttl_seconds,
                record_count=len(self.records),
                limitation=limitation,
            ),
        )
        signals = tuple(
            _registration_signal(record, request.report_date)
            for record in self.records
            if record.fuel_type in {None, "total"}
        )
        limitations = [
            "KBA registrations are official new registrations, not vehicle sales "
            "revenue or marketplace transactions."
        ]
        if limitation:
            limitations.append(limitation)
        if not signals:
            limitations.append(
                "The workbook contained no total-registration row for a tracked "
                "brand/model in the requested scope."
            )
        return ExternalSourceSnapshot(
            source_type=ExternalSourceType.KBA_REGISTRATIONS,
            provider_name=self.name,
            status=ExternalSourceStatus.AVAILABLE,
            signals=signals,
            limitations=tuple(limitations),
        )

    def _download_url(self, year: int, month: int) -> str:
        fallback = self.config.download_url_template.format(
            year=year,
            month=month,
        )
        template = self.config.catalog_search_url_template
        if template is None:
            return fallback
        catalog_url = template.format(year=year, month=month)
        try:
            entry = self.cache.get_or_fetch(
                source_id=f"govdata_kba_fz10_{year}",
                source_url=catalog_url,
                ttl_seconds=self.config.ttl_seconds,
                fetcher=self.fetcher,
            )
            payload = json.loads(entry.payload_path.read_text(encoding="utf-8"))
            discovered = _catalog_resource_url(payload, year, month)
            if discovered is not None:
                return discovered
            logger.warning(
                "GovData KBA catalog contained no FZ10 resource year=%s month=%s",
                year,
                month,
            )
        except Exception as exc:
            logger.warning(
                "GovData KBA catalog discovery failed; using configured fallback "
                "year=%s month=%s error=%s",
                year,
                month,
                exc,
            )
        return fallback


def _registration_signal(
    record: KBARegistration,
    report_date: date,
) -> ExternalSignal:
    entity = f"{record.brand} {record.model}".strip()
    signal_id = hashlib.sha256(
        f"{record.period}\0{entity}\0{record.fuel_type}".encode()
    ).hexdigest()[:24]
    observed = date.fromisoformat(f"{record.period}-01")
    if observed > report_date:
        observed = report_date
    return ExternalSignal(
        signal_id=signal_id,
        title=f"KBA new registrations: {entity}",
        summary=(
            f"KBA FZ10 reports {record.registrations:,} new registrations for "
            f"{entity} in {record.period}."
        ),
        implication=StrategicImplication.CONTEXT,
        source_url=record.source_url,
        observed_at=observed,
        entity=entity,
        metric_name="official_new_registrations",
        metric_value=record.registrations,
        unit="vehicles",
    )


def _lagged_period(report_date: date, lag_months: int) -> tuple[int, int]:
    index = report_date.year * 12 + report_date.month - 1 - lag_months
    return index // 12, index % 12 + 1


def _catalog_resource_url(
    payload: object,
    year: int,
    month: int,
) -> str | None:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("GovData catalog response is not successful")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("GovData catalog response has no result mapping")
    datasets = result.get("results")
    if not isinstance(datasets, list):
        raise ValueError("GovData catalog response has no dataset list")
    needle = f"fz10_{year}_{month:02d}"
    for dataset in datasets:
        if not isinstance(dataset, dict):
            continue
        resources = dataset.get("resources")
        if not isinstance(resources, list):
            continue
        for resource in resources:
            if not isinstance(resource, dict):
                continue
            url = str(resource.get("url") or "").strip()
            searchable = " ".join(
                str(resource.get(key) or "") for key in ("name", "description", "url")
            ).casefold()
            if needle in searchable and url.startswith("https://"):
                return url
    return None


def _tracked_vehicle_keys(
    request: ExternalIntelligenceRequest,
) -> set[tuple[str, str]]:
    keys = set()
    for vehicle in request.vehicles:
        folded = vehicle.casefold()
        for brand in sorted(request.brands, key=len, reverse=True):
            prefix = f"{brand.casefold()} "
            if folded.startswith(prefix):
                keys.add((brand.casefold(), folded[len(prefix) :].strip()))
                break
    return keys


def _in_scope(
    brand: str,
    model: str,
    request: ExternalIntelligenceRequest,
    tracked: set[tuple[str, str]],
) -> bool:
    brand_key = brand.casefold().strip()
    model_key = model.casefold().strip()
    return (
        brand_key in {value.casefold() for value in request.brands}
        or (
            brand_key,
            model_key,
        )
        in tracked
    )
