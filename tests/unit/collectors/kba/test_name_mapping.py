from __future__ import annotations

from pathlib import Path

from germania.collectors.kba import KBANameMapping

PROJECT_ROOT = Path(__file__).resolve().parents[4]
APPROVED_MAPPING = PROJECT_ROOT / "config" / "kba_name_mapping.yaml"


def test_name_mapping_loads_approved_yaml() -> None:
    mapping = KBANameMapping.load(APPROVED_MAPPING)

    assert mapping.normalize_brand("SKODA") == "\u0160koda"
    assert KBANameMapping.load(APPROVED_MAPPING) is mapping


def test_name_mapping_applies_approved_brand_mapping() -> None:
    mapping = KBANameMapping.load(APPROVED_MAPPING)

    assert mapping.normalize_brand("MERCEDES") == "Mercedes-Benz"
    assert mapping.normalize_brand("TESLA") == "Tesla"


def test_name_mapping_applies_approved_vehicle_mapping() -> None:
    mapping = KBANameMapping.load(APPROVED_MAPPING)

    assert mapping.normalize_vehicle("NIO", "EL6") == ("NIO", "EL6")
    assert mapping.normalize_vehicle("XPENG", "G6") == ("XPENG", "G6")


def test_name_mapping_returns_original_values_when_no_mapping_exists() -> None:
    mapping = KBANameMapping.load(APPROVED_MAPPING)

    assert mapping.normalize_brand("UNKNOWN") == "UNKNOWN"
    assert mapping.normalize_vehicle("UNKNOWN", "MODEL X") == ("UNKNOWN", "MODEL X")


def test_name_mapping_does_not_apply_rejected_vehicle_mapping() -> None:
    mapping = KBANameMapping.load(APPROVED_MAPPING)

    assert mapping.normalize_vehicle("TESLA", "MODEL 3") == ("Tesla", "MODEL 3")
    assert mapping.is_rejected_vehicle("TESLA", "MODEL 3") is True


def test_name_mapping_does_not_read_proposed_yaml(tmp_path: Path) -> None:
    approved_path = tmp_path / "kba_name_mapping.yaml"
    proposed_path = tmp_path / "kba_name_mapping.proposed.yaml"
    approved_path.write_text(
        """
approved_brand_mappings:
  - source_value: AUDI
    canonical_value: Audi
    decision: approved
approved_vehicle_mappings: []
rejected_vehicle_mappings: []
ambiguous_mappings: []
""",
        encoding="utf-8",
    )
    proposed_path.write_text(
        """
approved_brand_mappings:
  - source_value: AUDI
    canonical_value: Wrong Proposed Value
    decision: approved
approved_vehicle_mappings: []
rejected_vehicle_mappings: []
ambiguous_mappings: []
""",
        encoding="utf-8",
    )

    mapping = KBANameMapping.load(approved_path)

    assert mapping.normalize_brand("AUDI") == "Audi"
