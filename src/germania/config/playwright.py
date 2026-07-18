"""Playwright YAML configuration loader for collection foundations."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PLAYWRIGHT_CONFIG_PATH = PROJECT_ROOT / "config" / "playwright.yaml"

PLAYWRIGHT_HEADLESS_ENV = "PLAYWRIGHT_HEADLESS"
REQUEST_TIMEOUT_ENV = "REQUEST_TIMEOUT"
MAX_REQUESTS_PER_RUN_ENV = "MAX_REQUESTS_PER_RUN"

ALLOWED_BROWSER_TYPES = frozenset({"chromium", "firefox", "webkit"})
_SOURCE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class PlaywrightConfigError(ValueError):
    """Raised when Playwright runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class ViewportSettings:
    """Browser viewport dimensions used for Playwright contexts."""

    width: int
    height: int

    def as_playwright_options(self) -> dict[str, int]:
        """Return the viewport mapping expected by Playwright."""
        return {"width": self.width, "height": self.height}


@dataclass(frozen=True)
class BrowserSettings:
    """Browser launch and context settings."""

    browser_type: str
    headless: bool
    launch_timeout_ms: int
    navigation_timeout_ms: int
    action_timeout_ms: int
    slow_mo_ms: int
    viewport: ViewportSettings
    locale: str
    timezone_id: str
    user_agent: str | None = None

    def context_options(self) -> dict[str, object]:
        """Return browser context options safe for Playwright new_context."""
        options: dict[str, object] = {
            "viewport": self.viewport.as_playwright_options(),
            "locale": self.locale,
            "timezone_id": self.timezone_id,
        }
        if self.user_agent:
            options["user_agent"] = self.user_agent
        return options


@dataclass(frozen=True)
class RequestSettings:
    """Request budget and timing settings shared by collectors."""

    request_timeout_seconds: float
    max_requests_per_run: int
    min_delay_seconds: float


@dataclass(frozen=True)
class RetrySettings:
    """Retry policy values loaded from configuration."""

    max_attempts: int
    initial_backoff_seconds: float
    backoff_multiplier: float
    max_backoff_seconds: float


@dataclass(frozen=True)
class ComplianceSettings:
    """Collection safety settings that prevent prohibited automation behavior."""

    respect_robots_txt: bool
    stop_on_access_denied: bool
    allow_login: bool
    allow_captcha_bypass: bool
    allow_access_control_bypass: bool


@dataclass(frozen=True)
class SourceCollectionOverride:
    """Optional per-source runtime override for collection settings."""

    source_id: str
    enabled: bool
    request_timeout_seconds: float | None = None
    max_requests_per_run: int | None = None
    min_delay_seconds: float | None = None
    retry_max_attempts: int | None = None


@dataclass(frozen=True)
class SourceRuntimeSettings:
    """Resolved runtime settings for a specific source."""

    request_timeout_seconds: float
    max_requests_per_run: int
    min_delay_seconds: float
    retry: RetrySettings


@dataclass(frozen=True)
class PlaywrightSettings:
    """Complete Playwright and collector runtime settings."""

    browser: BrowserSettings
    requests: RequestSettings
    retry: RetrySettings
    compliance: ComplianceSettings
    source_overrides: Mapping[str, SourceCollectionOverride]

    def for_source(self, source_id: str) -> SourceRuntimeSettings:
        """Resolve request and retry settings for a configured source."""
        override = self.source_overrides.get(source_id)
        retry = self.retry
        if override is not None and override.retry_max_attempts is not None:
            retry = replace(retry, max_attempts=override.retry_max_attempts)

        return SourceRuntimeSettings(
            request_timeout_seconds=(
                override.request_timeout_seconds
                if override is not None and override.request_timeout_seconds is not None
                else self.requests.request_timeout_seconds
            ),
            max_requests_per_run=(
                override.max_requests_per_run
                if override is not None and override.max_requests_per_run is not None
                else self.requests.max_requests_per_run
            ),
            min_delay_seconds=(
                override.min_delay_seconds
                if override is not None and override.min_delay_seconds is not None
                else self.requests.min_delay_seconds
            ),
            retry=retry,
        )


def load_playwright_config(
    config_path: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
) -> PlaywrightSettings:
    """Load and validate Playwright runtime configuration."""
    path = (
        Path(config_path) if config_path is not None else DEFAULT_PLAYWRIGHT_CONFIG_PATH
    )
    logger.debug("Loading Playwright configuration from %s", path)

    if not path.exists():
        raise _playwright_config_error(path, "file", "file not found")

    try:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise _playwright_config_error(path, "yaml", f"invalid YAML: {exc}") from exc

    settings = _build_playwright_settings(data, path)
    return _apply_environment_overrides(settings, path, environ)


def _build_playwright_settings(data: object, path: Path) -> PlaywrightSettings:
    if not isinstance(data, dict):
        raise _playwright_config_error(
            path,
            "top_level",
            "Playwright configuration must be a mapping",
        )

    _validate_metadata(data.get("metadata"), path)

    browser_data = _required_mapping(data, "browser", path)
    requests_data = _required_mapping(data, "requests", path)
    retry_data = _required_mapping(data, "retry", path)
    compliance_data = _required_mapping(data, "compliance", path)
    source_overrides_data = _optional_mapping(data, "source_overrides", path)

    browser = _build_browser_settings(browser_data, path)
    requests = _build_request_settings(requests_data, path)
    retry = _build_retry_settings(retry_data, path)
    compliance = _build_compliance_settings(compliance_data, path)
    source_overrides = _build_source_overrides(source_overrides_data, path)

    return PlaywrightSettings(
        browser=browser,
        requests=requests,
        retry=retry,
        compliance=compliance,
        source_overrides=source_overrides,
    )


def _validate_metadata(value: object, path: Path) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise _playwright_config_error(path, "metadata", "metadata must be a mapping")

    schema_version = value.get("schema_version")
    if schema_version != 1:
        raise _playwright_config_error(
            path,
            "metadata.schema_version",
            "schema_version must be 1",
        )


def _build_browser_settings(data: Mapping[str, object], path: Path) -> BrowserSettings:
    browser_type = _required_enum(
        data,
        "browser_type",
        ALLOWED_BROWSER_TYPES,
        path,
        "browser.browser_type",
    )
    viewport_data = _required_mapping(data, "viewport", path, "browser.viewport")

    return BrowserSettings(
        browser_type=browser_type,
        headless=_required_bool(data, "headless", path, "browser.headless"),
        launch_timeout_ms=_required_positive_int(
            data,
            "launch_timeout_ms",
            path,
            "browser.launch_timeout_ms",
        ),
        navigation_timeout_ms=_required_positive_int(
            data,
            "navigation_timeout_ms",
            path,
            "browser.navigation_timeout_ms",
        ),
        action_timeout_ms=_required_positive_int(
            data,
            "action_timeout_ms",
            path,
            "browser.action_timeout_ms",
        ),
        slow_mo_ms=_required_non_negative_int(
            data,
            "slow_mo_ms",
            path,
            "browser.slow_mo_ms",
        ),
        viewport=ViewportSettings(
            width=_required_positive_int(
                viewport_data,
                "width",
                path,
                "browser.viewport.width",
            ),
            height=_required_positive_int(
                viewport_data,
                "height",
                path,
                "browser.viewport.height",
            ),
        ),
        locale=_required_non_empty_string(data, "locale", path, "browser.locale"),
        timezone_id=_required_non_empty_string(
            data,
            "timezone_id",
            path,
            "browser.timezone_id",
        ),
        user_agent=_optional_non_empty_string(
            data,
            "user_agent",
            path,
            "browser.user_agent",
        ),
    )


def _build_request_settings(
    data: Mapping[str, object],
    path: Path,
) -> RequestSettings:
    return RequestSettings(
        request_timeout_seconds=_required_positive_number(
            data,
            "request_timeout_seconds",
            path,
            "requests.request_timeout_seconds",
        ),
        max_requests_per_run=_required_positive_int(
            data,
            "max_requests_per_run",
            path,
            "requests.max_requests_per_run",
        ),
        min_delay_seconds=_required_non_negative_number(
            data,
            "min_delay_seconds",
            path,
            "requests.min_delay_seconds",
        ),
    )


def _build_retry_settings(data: Mapping[str, object], path: Path) -> RetrySettings:
    return RetrySettings(
        max_attempts=_required_positive_int(
            data,
            "max_attempts",
            path,
            "retry.max_attempts",
        ),
        initial_backoff_seconds=_required_non_negative_number(
            data,
            "initial_backoff_seconds",
            path,
            "retry.initial_backoff_seconds",
        ),
        backoff_multiplier=_required_minimum_number(
            data,
            "backoff_multiplier",
            1,
            path,
            "retry.backoff_multiplier",
        ),
        max_backoff_seconds=_required_non_negative_number(
            data,
            "max_backoff_seconds",
            path,
            "retry.max_backoff_seconds",
        ),
    )


def _build_compliance_settings(
    data: Mapping[str, object],
    path: Path,
) -> ComplianceSettings:
    settings = ComplianceSettings(
        respect_robots_txt=_required_bool(
            data,
            "respect_robots_txt",
            path,
            "compliance.respect_robots_txt",
        ),
        stop_on_access_denied=_required_bool(
            data,
            "stop_on_access_denied",
            path,
            "compliance.stop_on_access_denied",
        ),
        allow_login=_required_bool(data, "allow_login", path, "compliance.allow_login"),
        allow_captcha_bypass=_required_bool(
            data,
            "allow_captcha_bypass",
            path,
            "compliance.allow_captcha_bypass",
        ),
        allow_access_control_bypass=_required_bool(
            data,
            "allow_access_control_bypass",
            path,
            "compliance.allow_access_control_bypass",
        ),
    )

    if settings.allow_login:
        raise _playwright_config_error(
            path,
            "compliance.allow_login",
            "login automation is prohibited",
        )
    if settings.allow_captcha_bypass:
        raise _playwright_config_error(
            path,
            "compliance.allow_captcha_bypass",
            "captcha bypass is prohibited",
        )
    if settings.allow_access_control_bypass:
        raise _playwright_config_error(
            path,
            "compliance.allow_access_control_bypass",
            "access-control bypass is prohibited",
        )

    return settings


def _build_source_overrides(
    data: Mapping[str, object],
    path: Path,
) -> dict[str, SourceCollectionOverride]:
    overrides: dict[str, SourceCollectionOverride] = {}
    for source_id, raw_override in data.items():
        if not _SOURCE_ID_PATTERN.fullmatch(source_id):
            raise _playwright_config_error(
                path,
                f"source_overrides.{source_id}",
                "source override keys must be snake_case source ids",
            )
        if not isinstance(raw_override, dict):
            raise _playwright_config_error(
                path,
                f"source_overrides.{source_id}",
                "source override must be a mapping",
            )

        override = SourceCollectionOverride(
            source_id=source_id,
            enabled=_optional_bool(
                raw_override,
                "enabled",
                True,
                path,
                f"source_overrides.{source_id}.enabled",
            ),
            request_timeout_seconds=_optional_positive_number(
                raw_override,
                "request_timeout_seconds",
                path,
                f"source_overrides.{source_id}.request_timeout_seconds",
            ),
            max_requests_per_run=_optional_positive_int(
                raw_override,
                "max_requests_per_run",
                path,
                f"source_overrides.{source_id}.max_requests_per_run",
            ),
            min_delay_seconds=_optional_non_negative_number(
                raw_override,
                "min_delay_seconds",
                path,
                f"source_overrides.{source_id}.min_delay_seconds",
            ),
            retry_max_attempts=_optional_positive_int(
                raw_override,
                "retry_max_attempts",
                path,
                f"source_overrides.{source_id}.retry_max_attempts",
            ),
        )
        overrides[source_id] = override

    return overrides


def _apply_environment_overrides(
    settings: PlaywrightSettings,
    path: Path,
    environ: Mapping[str, str] | None,
) -> PlaywrightSettings:
    values = os.environ if environ is None else environ
    browser = settings.browser
    requests = settings.requests

    headless_override = values.get(PLAYWRIGHT_HEADLESS_ENV)
    if headless_override is not None and headless_override.strip():
        browser = replace(
            browser,
            headless=_parse_bool_env(headless_override, path, PLAYWRIGHT_HEADLESS_ENV),
        )

    request_timeout_override = values.get(REQUEST_TIMEOUT_ENV)
    if request_timeout_override is not None and request_timeout_override.strip():
        requests = replace(
            requests,
            request_timeout_seconds=_parse_positive_number_env(
                request_timeout_override,
                path,
                REQUEST_TIMEOUT_ENV,
            ),
        )

    max_requests_override = values.get(MAX_REQUESTS_PER_RUN_ENV)
    if max_requests_override is not None and max_requests_override.strip():
        requests = replace(
            requests,
            max_requests_per_run=_parse_positive_int_env(
                max_requests_override,
                path,
                MAX_REQUESTS_PER_RUN_ENV,
            ),
        )

    return replace(settings, browser=browser, requests=requests)


def _required_mapping(
    data: Mapping[str, object],
    key: str,
    path: Path,
    field: str | None = None,
) -> Mapping[str, object]:
    value = data.get(key)
    field_name = field or key
    if not isinstance(value, dict):
        raise _playwright_config_error(path, field_name, "field must be a mapping")
    return value


def _optional_mapping(
    data: Mapping[str, object],
    key: str,
    path: Path,
) -> Mapping[str, object]:
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise _playwright_config_error(path, key, "field must be a mapping")
    return value


def _required_bool(
    data: Mapping[str, object],
    key: str,
    path: Path,
    field: str,
) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise _playwright_config_error(path, field, "field must be a boolean")
    return value


def _optional_bool(
    data: Mapping[str, object],
    key: str,
    default: bool,
    path: Path,
    field: str,
) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise _playwright_config_error(path, field, "field must be a boolean")
    return value


def _required_enum(
    data: Mapping[str, object],
    key: str,
    allowed_values: frozenset[str],
    path: Path,
    field: str,
) -> str:
    value = data.get(key)
    if not isinstance(value, str) or value not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        raise _playwright_config_error(path, field, f"field must be one of: {allowed}")
    return value


def _required_non_empty_string(
    data: Mapping[str, object],
    key: str,
    path: Path,
    field: str,
) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _playwright_config_error(path, field, "field must be non-empty text")
    return value


def _optional_non_empty_string(
    data: Mapping[str, object],
    key: str,
    path: Path,
    field: str,
) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _playwright_config_error(path, field, "field must be null or text")
    return value


def _required_positive_int(
    data: Mapping[str, object],
    key: str,
    path: Path,
    field: str,
) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise _playwright_config_error(path, field, "field must be a positive integer")
    return value


def _required_non_negative_int(
    data: Mapping[str, object],
    key: str,
    path: Path,
    field: str,
) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _playwright_config_error(
            path,
            field,
            "field must be a non-negative integer",
        )
    return value


def _optional_positive_int(
    data: Mapping[str, object],
    key: str,
    path: Path,
    field: str,
) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise _playwright_config_error(path, field, "field must be a positive integer")
    return value


def _required_positive_number(
    data: Mapping[str, object],
    key: str,
    path: Path,
    field: str,
) -> float:
    value = data.get(key)
    if not _is_number(value) or value <= 0:
        raise _playwright_config_error(path, field, "field must be a positive number")
    return float(value)


def _required_non_negative_number(
    data: Mapping[str, object],
    key: str,
    path: Path,
    field: str,
) -> float:
    value = data.get(key)
    if not _is_number(value) or value < 0:
        raise _playwright_config_error(
            path,
            field,
            "field must be a non-negative number",
        )
    return float(value)


def _required_minimum_number(
    data: Mapping[str, object],
    key: str,
    minimum: float,
    path: Path,
    field: str,
) -> float:
    value = data.get(key)
    if not _is_number(value) or value < minimum:
        raise _playwright_config_error(
            path,
            field,
            f"field must be greater than or equal to {minimum:g}",
        )
    return float(value)


def _optional_positive_number(
    data: Mapping[str, object],
    key: str,
    path: Path,
    field: str,
) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if not _is_number(value) or value <= 0:
        raise _playwright_config_error(path, field, "field must be a positive number")
    return float(value)


def _optional_non_negative_number(
    data: Mapping[str, object],
    key: str,
    path: Path,
    field: str,
) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if not _is_number(value) or value < 0:
        raise _playwright_config_error(
            path,
            field,
            "field must be a non-negative number",
        )
    return float(value)


def _parse_bool_env(value: str, path: Path, env_name: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise _playwright_config_error(
        path,
        f"env.{env_name}",
        "environment override must be a boolean",
    )


def _parse_positive_number_env(value: str, path: Path, env_name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise _playwright_config_error(
            path,
            f"env.{env_name}",
            "environment override must be a positive number",
        ) from exc
    if parsed <= 0:
        raise _playwright_config_error(
            path,
            f"env.{env_name}",
            "environment override must be a positive number",
        )
    return parsed


def _parse_positive_int_env(value: str, path: Path, env_name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise _playwright_config_error(
            path,
            f"env.{env_name}",
            "environment override must be a positive integer",
        ) from exc
    if parsed <= 0:
        raise _playwright_config_error(
            path,
            f"env.{env_name}",
            "environment override must be a positive integer",
        )
    return parsed


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _playwright_config_error(
    path: Path,
    field: str,
    reason: str,
) -> PlaywrightConfigError:
    return PlaywrightConfigError(f"path={path} | field={field} | reason={reason}")
