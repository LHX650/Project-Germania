from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from germania.config import (
    UNKNOWN,
    load_vehicle_config,
    normalize_brand,
    normalize_model,
    normalize_powertrain,
)
from germania.config.vehicles import VehicleConfigError


def test_load_vehicle_config_contains_initial_research_vehicles() -> None:
    config = load_vehicle_config()

    assert len(config["vehicles"]) == 23
    assert all(vehicle["active"] is True for vehicle in config["vehicles"])
    assert {
        "canonical_brand",
        "canonical_model",
        "chinese_brand",
        "chinese_model",
        "manufacturer",
        "vehicle_segment",
        "body_type",
        "powertrain",
        "country_of_origin",
        "priority_level",
        "active",
        "aliases",
    }.issubset(config["vehicles"][0])


def test_normalize_brand_aliases() -> None:
    assert normalize_brand("VW") == "Volkswagen"
    assert normalize_brand("volkswagen") == "Volkswagen"
    assert normalize_brand("ŠKODA") == "Škoda"
    assert normalize_brand("比亚迪") == "BYD"


def test_normalize_model_aliases() -> None:
    assert normalize_model("VW Golf") == "Golf"
    assert normalize_model("Volkswagen ID-4") == "ID.4"
    assert normalize_model("Skoda Enyaq") == "Enyaq"
    assert normalize_model("BYD Yuan Plus") == "Atto 3"
    assert normalize_model("Tesla Model 3") == "Model 3"
    assert normalize_model("BYD Seal") == "Seal"
    assert normalize_model("BMW 3er") == "3 Series"
    assert normalize_model("MG4 Electric") == "MG4"
    assert normalize_model("GLC 300") == "GLC"


def test_normalization_handles_case_spaces_and_punctuation() -> None:
    assert normalize_model(" tesla   model-y ") == "Model Y"
    assert normalize_model("audi q4 e tron") == "Q4 e-tron"
    assert normalize_brand("xpeng") == "XPENG"
    assert normalize_powertrain("Elektro") == "battery_electric"


def test_unknown_values_return_unknown() -> None:
    assert normalize_brand("Opel") == UNKNOWN
    assert normalize_model("Tesla Roadster") == UNKNOWN
    assert normalize_powertrain("hydrogen fuel cell") == UNKNOWN


def test_similar_models_do_not_match_incorrectly() -> None:
    assert normalize_model("ID.5") == UNKNOWN
    assert normalize_model("BYD Sealion 7") == UNKNOWN
    assert normalize_model("BMW X1") == UNKNOWN
    assert normalize_model("MG HS") == UNKNOWN
    assert normalize_model("Tesla Model X") == UNKNOWN


def test_vehicle_config_rejects_invalid_priority_level(tmp_path: Path) -> None:
    config = _valid_vehicle_config()
    config["vehicles"][0]["priority_level"] = "urgent"
    config_path = _write_vehicle_config(tmp_path, config)

    with pytest.raises(VehicleConfigError, match="priority_level"):
        load_vehicle_config(config_path)


def test_vehicle_config_rejects_invalid_powertrain(tmp_path: Path) -> None:
    config = _valid_vehicle_config()
    config["vehicles"][0]["powertrain"] = "steam"
    config_path = _write_vehicle_config(tmp_path, config)

    with pytest.raises(VehicleConfigError, match="powertrain"):
        load_vehicle_config(config_path)


def test_vehicle_config_rejects_empty_alias(tmp_path: Path) -> None:
    config = _valid_vehicle_config()
    config["vehicles"][0]["aliases"]["model"].append(" ")
    config_path = _write_vehicle_config(tmp_path, config)

    with pytest.raises(VehicleConfigError, match="empty alias"):
        load_vehicle_config(config_path)


def test_vehicle_config_rejects_cross_vehicle_model_alias_conflict(
    tmp_path: Path,
) -> None:
    config = _valid_vehicle_config()
    config["vehicles"][1]["aliases"]["model"].append(
        config["vehicles"][0]["aliases"]["model"][0]
    )
    config_path = _write_vehicle_config(tmp_path, config)

    with pytest.raises(VehicleConfigError, match="aliases.model conflicts"):
        load_vehicle_config(config_path)


def _valid_vehicle_config() -> dict[str, Any]:
    return deepcopy(load_vehicle_config())


def _write_vehicle_config(tmp_path: Path, config: dict[str, Any]) -> Path:
    config_path = tmp_path / "vehicles.yaml"
    config_path.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return config_path
