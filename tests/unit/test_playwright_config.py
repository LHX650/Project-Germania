from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from germania.config.playwright import PlaywrightConfigError, load_playwright_config


def test_load_playwright_config_default_path_success() -> None:
    settings = load_playwright_config(environ={})

    assert settings.browser.browser_type == "chromium"
    assert settings.browser.headless is True
    assert settings.browser.viewport.width == 1440
    assert settings.browser.timezone_id == "Europe/Berlin"
    assert settings.requests.request_timeout_seconds == 30
    assert settings.for_source("autoscout24_de").max_requests_per_run == 50


def test_playwright_config_environment_overrides() -> None:
    settings = load_playwright_config(
        environ={
            "PLAYWRIGHT_HEADLESS": "false",
            "REQUEST_TIMEOUT": "12.5",
            "MAX_REQUESTS_PER_RUN": "7",
        }
    )

    assert settings.browser.headless is False
    assert settings.requests.request_timeout_seconds == 12.5
    assert settings.requests.max_requests_per_run == 7


def test_invalid_playwright_yaml_raises_clear_error(tmp_path: Path) -> None:
    config_path = tmp_path / "invalid_playwright.yaml"
    config_path.write_text("browser:\n  - [broken\n", encoding="utf-8")

    with pytest.raises(PlaywrightConfigError, match="field=yaml"):
        load_playwright_config(config_path, environ={})


def test_missing_playwright_file_raises_clear_error(tmp_path: Path) -> None:
    config_path = tmp_path / "missing_playwright.yaml"

    with pytest.raises(PlaywrightConfigError, match="field=file"):
        load_playwright_config(config_path, environ={})


def test_disallowed_captcha_bypass_raises_clear_error(tmp_path: Path) -> None:
    config = _valid_config()
    config["compliance"]["allow_captcha_bypass"] = True
    config_path = _write_config(tmp_path, config)

    with pytest.raises(PlaywrightConfigError, match="allow_captcha_bypass"):
        load_playwright_config(config_path, environ={})


def test_invalid_browser_type_raises_clear_error(tmp_path: Path) -> None:
    config = _valid_config()
    config["browser"]["browser_type"] = "netscape"
    config_path = _write_config(tmp_path, config)

    with pytest.raises(PlaywrightConfigError, match="browser.browser_type"):
        load_playwright_config(config_path, environ={})


def test_source_override_resolves_runtime_settings(tmp_path: Path) -> None:
    config = _valid_config()
    config["source_overrides"] = {
        "mobile_de": {
            "enabled": True,
            "request_timeout_seconds": 45,
            "max_requests_per_run": 9,
            "min_delay_seconds": 3,
            "retry_max_attempts": 2,
        }
    }
    config_path = _write_config(tmp_path, config)

    settings = load_playwright_config(config_path, environ={})
    runtime = settings.for_source("mobile_de")

    assert runtime.request_timeout_seconds == 45
    assert runtime.max_requests_per_run == 9
    assert runtime.min_delay_seconds == 3
    assert runtime.retry.max_attempts == 2


def test_invalid_environment_override_raises_clear_error() -> None:
    with pytest.raises(PlaywrightConfigError, match="env.REQUEST_TIMEOUT"):
        load_playwright_config(environ={"REQUEST_TIMEOUT": "0"})


def _valid_config() -> dict[str, Any]:
    return {
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
        "source_overrides": {},
    }


def _write_config(tmp_path: Path, config: dict[str, Any]) -> Path:
    config_path = tmp_path / "playwright.yaml"
    config_path.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return config_path
