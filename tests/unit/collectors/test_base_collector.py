from __future__ import annotations

import hashlib
import logging
from datetime import UTC
from pathlib import Path
from typing import Any

import pytest
import yaml

from germania.collectors.base import BaseCollector
from germania.collectors.exceptions import (
    CollectorConfigurationError,
    RequestBudgetExceeded,
)
from germania.config.playwright import load_playwright_config


def test_base_collector_loads_source_and_runtime_settings(caplog: object) -> None:
    collector = DummyCollector(
        "autoscout24_de",
        source_config=_source_config("autoscout24_de"),
        playwright_settings=load_playwright_config(environ={}),
    )

    with caplog.at_level(logging.INFO, logger="germania.collectors.autoscout24_de"):
        request = collector.record_request("https://www.autoscout24.de/example")

    assert collector.source.source_name == "AutoScout24 Germany"
    assert collector.source.data_categories == ("listings",)
    assert collector.request_budget == 50
    assert collector.remaining_request_budget() == 49
    assert request.sequence_number == 1
    assert request.requested_at.tzinfo == UTC
    assert request.timeout_seconds == 30
    assert "Recorded collection request" in caplog.text


def test_base_collector_enforces_request_budget(tmp_path: Path) -> None:
    settings = load_playwright_config(
        _write_playwright_config(tmp_path, source_id="test_source", max_requests=1),
        environ={},
    )
    collector = DummyCollector(
        "test_source",
        source_config=_source_config("test_source"),
        playwright_settings=settings,
    )

    collector.record_request("https://example.test/one")

    with pytest.raises(RequestBudgetExceeded, match="budget=1"):
        collector.record_request("https://example.test/two")


def test_base_collector_builds_raw_metadata_hash() -> None:
    collector = DummyCollector(
        "kba",
        source_config=_source_config("kba", source_name="KBA"),
        playwright_settings=load_playwright_config(environ={}),
    )
    raw_content = b"period,total\n2026-06,123\n"

    metadata = collector.build_raw_metadata("https://www.kba.de/file.csv", raw_content)

    assert metadata.source_id == "kba"
    assert metadata.source_name == "KBA"
    assert metadata.collected_at.tzinfo == UTC
    assert metadata.content_sha256 == hashlib.sha256(raw_content).hexdigest()


def test_base_collector_rejects_unknown_source() -> None:
    with pytest.raises(CollectorConfigurationError, match="Unknown source_id"):
        DummyCollector(
            "missing_source",
            source_config=_source_config("known_source"),
            playwright_settings=load_playwright_config(environ={}),
        )


def test_base_collector_rejects_disabled_source_override(tmp_path: Path) -> None:
    config_path = _write_playwright_config(
        tmp_path,
        source_id="test_source",
        max_requests=1,
        enabled=False,
    )

    with pytest.raises(CollectorConfigurationError, match="disabled"):
        DummyCollector(
            "test_source",
            source_config=_source_config("test_source"),
            playwright_settings=load_playwright_config(config_path, environ={}),
        )


class DummyCollector(BaseCollector):
    def collect(self) -> list[object]:
        """Return no records because tests do not collect source data."""
        return []


def _source_config(
    source_id: str,
    *,
    source_name: str = "AutoScout24 Germany",
    active: bool = True,
) -> dict[str, Any]:
    return {
        "metadata": {"schema_version": 1},
        "sources": [
            {
                "source_id": source_id,
                "source_name": source_name,
                "source_type": "marketplace",
                "country_code": "DE",
                "base_url": "https://example.test",
                "data_categories": ["listings"],
                "update_frequency": "daily",
                "authority_level": "primary_commercial",
                "active": active,
                "collection_method": "html_parse",
                "notes": "Unit-test source. No network request is made.",
            }
        ],
    }


def _write_playwright_config(
    tmp_path: Path,
    *,
    source_id: str,
    max_requests: int,
    enabled: bool = True,
) -> Path:
    config = {
        "metadata": {"schema_version": 1},
        "browser": {
            "browser_type": "chromium",
            "headless": True,
            "launch_timeout_ms": 30000,
            "navigation_timeout_ms": 30000,
            "action_timeout_ms": 10000,
            "slow_mo_ms": 0,
            "viewport": {"width": 1280, "height": 720},
            "locale": "de-DE",
            "timezone_id": "Europe/Berlin",
            "user_agent": None,
        },
        "requests": {
            "request_timeout_seconds": 30,
            "max_requests_per_run": 100,
            "min_delay_seconds": 1,
        },
        "retry": {
            "max_attempts": 3,
            "initial_backoff_seconds": 1,
            "backoff_multiplier": 2,
            "max_backoff_seconds": 30,
        },
        "compliance": {
            "respect_robots_txt": True,
            "stop_on_access_denied": True,
            "allow_login": False,
            "allow_captcha_bypass": False,
            "allow_access_control_bypass": False,
        },
        "source_overrides": {
            source_id: {
                "enabled": enabled,
                "max_requests_per_run": max_requests,
            }
        },
    }
    config_path = tmp_path / "playwright.yaml"
    config_path.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return config_path
