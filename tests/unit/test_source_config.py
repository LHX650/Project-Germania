from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from germania.config import load_source_config
from germania.config.sources import SourceConfigError


def test_load_source_config_default_path_success() -> None:
    config = load_source_config()

    assert "sources" in config
    assert isinstance(config["sources"], list)


def test_source_config_contains_at_least_twelve_sources() -> None:
    config = load_source_config()

    assert len(config["sources"]) >= 12


def test_source_ids_are_unique() -> None:
    config = load_source_config()
    source_ids = [source["source_id"] for source in config["sources"]]

    assert len(source_ids) == len(set(source_ids))


def test_required_fields_exist_in_all_sources() -> None:
    config = load_source_config()
    required_fields = {
        "source_id",
        "source_name",
        "source_type",
        "country_code",
        "base_url",
        "data_categories",
        "update_frequency",
        "authority_level",
        "active",
        "collection_method",
        "notes",
    }

    assert all(required_fields.issubset(source) for source in config["sources"])


def test_invalid_yaml_raises_clear_error(tmp_path: Path) -> None:
    config_path = tmp_path / "invalid_sources.yaml"
    config_path.write_text("sources:\n  - [broken\n", encoding="utf-8")

    with pytest.raises(SourceConfigError, match="field=yaml"):
        load_source_config(config_path)


def test_missing_file_raises_clear_error(tmp_path: Path) -> None:
    config_path = tmp_path / "missing_sources.yaml"

    with pytest.raises(SourceConfigError, match="field=file"):
        load_source_config(config_path)


def test_duplicate_source_id_raises_clear_error(tmp_path: Path) -> None:
    config = _valid_config()
    config["sources"].append(deepcopy(config["sources"][0]))
    config_path = _write_config(tmp_path, config)

    with pytest.raises(SourceConfigError, match="duplicate source_id"):
        load_source_config(config_path)


def test_invalid_source_type_raises_clear_error(tmp_path: Path) -> None:
    config_path = _write_config_with_field(tmp_path, "source_type", "newspaper")

    with pytest.raises(SourceConfigError, match="field=source_type"):
        load_source_config(config_path)


def test_invalid_data_categories_raises_clear_error(tmp_path: Path) -> None:
    config_path = _write_config_with_field(tmp_path, "data_categories", ["rumors"])

    with pytest.raises(SourceConfigError, match="field=data_categories"):
        load_source_config(config_path)


def test_invalid_update_frequency_raises_clear_error(tmp_path: Path) -> None:
    config_path = _write_config_with_field(tmp_path, "update_frequency", "hourly")

    with pytest.raises(SourceConfigError, match="field=update_frequency"):
        load_source_config(config_path)


def test_invalid_authority_level_raises_clear_error(tmp_path: Path) -> None:
    config_path = _write_config_with_field(tmp_path, "authority_level", "untrusted")

    with pytest.raises(SourceConfigError, match="field=authority_level"):
        load_source_config(config_path)


def test_invalid_collection_method_raises_clear_error(tmp_path: Path) -> None:
    config_path = _write_config_with_field(tmp_path, "collection_method", "scrape")

    with pytest.raises(SourceConfigError, match="field=collection_method"):
        load_source_config(config_path)


def test_active_must_be_boolean(tmp_path: Path) -> None:
    config_path = _write_config_with_field(tmp_path, "active", "true")

    with pytest.raises(SourceConfigError, match="field=active"):
        load_source_config(config_path)


def test_country_code_must_use_two_uppercase_letters(tmp_path: Path) -> None:
    config_path = _write_config_with_field(tmp_path, "country_code", "DEU")

    with pytest.raises(SourceConfigError, match="field=country_code"):
        load_source_config(config_path)


def test_null_base_url_is_allowed_for_uncertain_sources(tmp_path: Path) -> None:
    config_path = _write_config_with_field(tmp_path, "base_url", None)

    config = load_source_config(config_path)

    assert config["sources"][0]["base_url"] is None


def test_empty_base_url_string_raises_clear_error(tmp_path: Path) -> None:
    config_path = _write_config_with_field(tmp_path, "base_url", "")

    with pytest.raises(SourceConfigError, match="field=base_url"):
        load_source_config(config_path)


def test_load_source_config_returns_stable_structure() -> None:
    config = load_source_config()

    assert sorted(config) == ["metadata", "sources"]
    assert isinstance(config["metadata"]["schema_version"], int)
    assert isinstance(config["sources"][0]["data_categories"], list)


def test_custom_path_loading_success(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, _valid_config())

    config = load_source_config(config_path)

    assert config["sources"][0]["source_id"] == "test_source"


def _valid_config() -> dict[str, Any]:
    return {
        "metadata": {"schema_version": 1},
        "sources": [
            {
                "source_id": "test_source",
                "source_name": "Test Source",
                "source_type": "government",
                "country_code": "DE",
                "base_url": "https://example.test",
                "data_categories": ["registrations"],
                "update_frequency": "monthly",
                "authority_level": "primary_authoritative",
                "active": True,
                "collection_method": "manual_download",
                "notes": "Planning-only test source. No network request is made.",
            }
        ],
    }


def _write_config_with_field(tmp_path: Path, field: str, value: object) -> Path:
    config = _valid_config()
    config["sources"][0][field] = value
    return _write_config(tmp_path, config)


def _write_config(tmp_path: Path, config: dict[str, Any]) -> Path:
    config_path = tmp_path / "sources.yaml"
    config_path.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return config_path
