from __future__ import annotations

from germania.config import (
    UNKNOWN,
    load_vehicle_config,
    normalize_brand,
    normalize_model,
    normalize_powertrain,
)


def test_load_vehicle_config_contains_initial_research_vehicles() -> None:
    config = load_vehicle_config()

    assert len(config["vehicles"]) == 15
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


def test_normalization_handles_case_spaces_and_punctuation() -> None:
    assert normalize_model(" tesla   model-y ") == "Model Y"
    assert normalize_model("audi q4 e tron") == "Q4 e-tron"
    assert normalize_brand("xpeng") == "XPENG"
    assert normalize_powertrain("Elektro") == "battery_electric"


def test_unknown_values_return_unknown() -> None:
    assert normalize_brand("Opel") == UNKNOWN
    assert normalize_model("Tesla Model 3") == UNKNOWN
    assert normalize_powertrain("hydrogen fuel cell") == UNKNOWN


def test_similar_models_do_not_match_incorrectly() -> None:
    assert normalize_model("ID.5") == UNKNOWN
    assert normalize_model("BYD Seal") == UNKNOWN
    assert normalize_model("BMW X1") == UNKNOWN
    assert normalize_model("MG HS") == UNKNOWN
    assert normalize_model("Tesla Model 3") == UNKNOWN
