from __future__ import annotations

from external_intelligence.recognition import recognize_entities
from external_intelligence.vehicle_catalog import load_monitored_vehicles


def test_enabled_marketplace_catalog_contains_twenty_unique_vehicles() -> None:
    vehicles = load_monitored_vehicles()

    assert len(vehicles) == 20
    assert len({item.display_name for item in vehicles}) == 20
    assert {item.brand for item in vehicles} == {
        "Audi",
        "BMW",
        "BYD",
        "MG",
        "Mercedes-Benz",
        "NIO",
        "Tesla",
        "Volkswagen",
        "XPENG",
        "Škoda",
    }


def test_recognition_covers_new_brands_and_prefers_specific_vehicle_name() -> None:
    catalog = load_monitored_vehicles()
    brands = tuple(dict.fromkeys(item.brand for item in catalog))
    vehicles = tuple(item.display_name for item in catalog)

    matched_brands, matched_vehicles = recognize_entities(
        "Škoda Enyaq, MG MG4, XPENG G6, NIO EL6 and BYD Seal U updates",
        tracked_brands=brands,
        tracked_vehicles=vehicles,
    )

    assert {"Škoda", "MG", "XPENG", "NIO", "BYD"}.issubset(matched_brands)
    assert "BYD Seal U" in matched_vehicles
    assert "BYD Seal" not in matched_vehicles
    assert {"Škoda Enyaq", "MG MG4", "XPENG G6", "NIO EL6"}.issubset(matched_vehicles)


def test_recognition_uses_verified_aliases_and_url_without_brand_forcing() -> None:
    brands, vehicles = recognize_entities(
        "The all-new electric C-Class https://official.test/c-klasse-update",
        tracked_brands=("Mercedes-Benz",),
        tracked_vehicles=("Mercedes-Benz C-Class", "Mercedes-Benz GLC"),
        source_brand="Mercedes-Benz",
    )

    assert brands == ("Mercedes-Benz",)
    assert vehicles == ("Mercedes-Benz C-Class",)

    _, no_vehicle = recognize_entities(
        "Mercedes-Benz opens a new office",
        tracked_brands=("Mercedes-Benz",),
        tracked_vehicles=("Mercedes-Benz C-Class", "Mercedes-Benz GLC"),
        source_brand="Mercedes-Benz",
    )
    assert no_vehicle == ()
