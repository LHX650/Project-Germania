"""Compose Phase 5A/11 metrics with read-only SQLite peer controls."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from germania.analytics.comparable_benchmarking import (
    ComparableVehicleBenchmark,
    ComparableVehicleInput,
    calculate_comparable_vehicle_benchmarks,
)
from services.database import (
    ComparableVehicleMetadata,
    load_comparable_vehicle_metadata,
)
from services.intelligence import DailyMarketIntelligence, vehicle_key


@dataclass(frozen=True)
class PeerBenchmarkReport:
    """Current peer benchmarks and their verified SQLite control variables."""

    benchmarks: tuple[ComparableVehicleBenchmark, ...]
    metadata: tuple[ComparableVehicleMetadata, ...]

    @property
    def by_vehicle(self) -> dict[str, ComparableVehicleBenchmark]:
        """Return benchmark results keyed by the report vehicle identity."""

        return {item.vehicle_key: item for item in self.benchmarks}

    @property
    def metadata_by_vehicle(self) -> dict[str, ComparableVehicleMetadata]:
        """Return metadata keyed by its canonical vehicle identity."""

        return {item.vehicle_key: item for item in self.metadata}


def load_peer_benchmarks(
    report: DailyMarketIntelligence,
    database_path: str | Path | None = None,
) -> PeerBenchmarkReport:
    """Recalculate peer groups from the current report and SQLite metadata."""

    metadata = load_comparable_vehicle_metadata(database_path)
    metadata_lookup = {item.vehicle_key.casefold(): item for item in metadata}
    inputs = []
    for vehicle in report.vehicles:
        key = vehicle_key(vehicle.brand, vehicle.model)
        controls = metadata_lookup.get(key.casefold())
        scores = report.quantitative_by_vehicle[key]
        inputs.append(
            ComparableVehicleInput(
                vehicle_key=key,
                brand=vehicle.brand,
                model=vehicle.model,
                average_price_eur=vehicle.metrics.average_price_eur,
                vehicle_segment=(
                    controls.vehicle_segment if controls is not None else None
                ),
                body_type=controls.body_type if controls is not None else None,
                powertrain=controls.powertrain if controls is not None else None,
                active_inventory=float(vehicle.metrics.active_listing_count),
                price_change_7d_pct=vehicle.metrics.price_change_7d_pct,
                opportunity_score=vehicle.opportunity_score.score,
                price_pressure=scores.price_pressure.score,
                inventory_pressure=scores.inventory_pressure.score,
                market_momentum=scores.market_momentum.score,
            )
        )
    return PeerBenchmarkReport(
        benchmarks=calculate_comparable_vehicle_benchmarks(tuple(inputs)),
        metadata=metadata,
    )
