"""Strict loader for the generated external-intelligence evidence artifact."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from strategic.external import (
    ExternalIntelligenceBundle,
    ExternalSignal,
    ExternalSourceSnapshot,
    ExternalSourceStatus,
    ExternalSourceType,
    StrategicImplication,
)


def load_external_intelligence_artifact(
    path: str | Path,
    *,
    expected_report_date: date,
) -> ExternalIntelligenceBundle:
    """Load attributed evidence and reject date or schema mismatches."""

    source = Path(path).expanduser().resolve(strict=True)
    payload = json.loads(source.read_text(encoding="utf-8"))
    root = _mapping(payload, "external intelligence")
    report_date = date.fromisoformat(_text(root, "report_date"))
    if report_date != expected_report_date:
        raise ValueError("external and Analytics report dates do not match")
    return ExternalIntelligenceBundle(
        kba=_kba_snapshot(_mapping(root.get("kba"), "kba"), report_date),
        news=_news_snapshot(
            _mapping(root.get("news"), "news"),
            report_date,
            ExternalSourceType.NEWS,
        ),
        brand_news=_news_snapshot(
            _mapping(root.get("brand_news"), "brand_news"),
            report_date,
            ExternalSourceType.BRAND_NEWS,
        ),
        market_data=ExternalSourceSnapshot(
            source_type=ExternalSourceType.MARKET_DATA,
            provider_name="not_configured",
            status=ExternalSourceStatus.NOT_CONFIGURED,
            limitations=("No external market-data artifact is configured.",),
        ),
    )


def _kba_snapshot(
    section: dict[str, Any],
    report_date: date,
) -> ExternalSourceSnapshot:
    signals = []
    for raw in _sequence(section.get("records"), "kba.records"):
        record = _mapping(raw, "kba record")
        observed = _timestamp(record.get("retrieved_at"), "retrieved_at")
        _not_future(observed, report_date)
        brand = _text(record, "brand")
        model = _text(record, "model")
        registrations = _integer(record.get("registrations"), "registrations")
        source_url = _https(record.get("source_url"), "source_url")
        period = _text(record, "period")
        signals.append(
            ExternalSignal(
                signal_id=f"kba:{period}:{brand}:{model}",
                title=f"KBA registrations — {brand} {model}",
                summary=(
                    f"Official KBA record for {period}: {registrations} "
                    "new registrations."
                ),
                implication=StrategicImplication.CONTEXT,
                source_url=source_url,
                observed_at=observed,
                entity=f"{brand} {model}",
                metric_name="new_registrations",
                metric_value=registrations,
                unit="vehicles",
            )
        )
    return _snapshot(
        section,
        ExternalSourceType.KBA_REGISTRATIONS,
        tuple(signals),
    )


def _news_snapshot(
    section: dict[str, Any],
    report_date: date,
    source_type: ExternalSourceType,
) -> ExternalSourceSnapshot:
    signals = []
    for raw in _sequence(section.get("articles"), "articles"):
        article = _mapping(raw, "article")
        observed = _timestamp(article.get("published_at"), "published_at")
        _not_future(observed, report_date)
        models = _strings(article.get("models"))
        brands = _strings(article.get("brands"))
        signals.append(
            ExternalSignal(
                signal_id=_text(article, "article_id"),
                title=_text(article, "title"),
                summary=_text(article, "summary"),
                implication=StrategicImplication.CONTEXT,
                source_url=_https(article.get("url"), "url"),
                observed_at=observed,
                entity=models[0] if models else (brands[0] if brands else None),
            )
        )
    return _snapshot(section, source_type, tuple(signals))


def _snapshot(
    section: dict[str, Any],
    source_type: ExternalSourceType,
    signals: tuple[ExternalSignal, ...],
) -> ExternalSourceSnapshot:
    status = ExternalSourceStatus(_text(section, "status"))
    if status is not ExternalSourceStatus.AVAILABLE and signals:
        raise ValueError("unavailable external section cannot contain records")
    return ExternalSourceSnapshot(
        source_type=source_type,
        provider_name=_text(section, "provider"),
        status=status,
        signals=signals,
        limitations=_strings(section.get("limitations")),
    )


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


def _text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} must be non-empty")
    return " ".join(value.split())


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("expected an array of strings")
    return tuple(str(item).strip() for item in value if str(item).strip())


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _timestamp(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must use ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must contain a timezone")
    return parsed.astimezone(UTC)


def _not_future(value: datetime, report_date: date) -> None:
    if value.date() > report_date:
        raise ValueError("external evidence timestamp exceeds the report date")


def _https(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text.startswith("https://"):
        raise ValueError(f"{field} must use HTTPS")
    return text
