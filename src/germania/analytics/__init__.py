"""Read-only market-intelligence analytics for Project Germania."""

from __future__ import annotations

from germania.analytics.comparable_benchmarking import (
    MINIMUM_PEER_COUNT,
    PEER_BENCHMARK_METHODOLOGY,
    PEER_MATCH_RULES,
    ComparableVehicleBenchmark,
    ComparableVehicleInput,
    PeerMatchRule,
    PeerMetricBenchmark,
    calculate_comparable_vehicle_benchmarks,
    segment_family,
)
from germania.analytics.market_intelligence import (
    MarketIntelligenceReport,
    build_daily_market_intelligence,
    write_daily_market_intelligence,
)
from germania.analytics.quantitative_intelligence import (
    INVENTORY_PRESSURE_WEIGHTS,
    MARKET_MOMENTUM_WEIGHTS,
    PRICE_PRESSURE_WEIGHTS,
    QUANTITATIVE_METHODOLOGY,
    MomentumIndex,
    QuantitativeIndex,
    VehicleQuantitativeInput,
    VehicleQuantitativeScores,
    calculate_market_quantitative_scores,
    classify_market_momentum,
)

__all__ = [
    "MINIMUM_PEER_COUNT",
    "PEER_BENCHMARK_METHODOLOGY",
    "PEER_MATCH_RULES",
    "ComparableVehicleBenchmark",
    "ComparableVehicleInput",
    "MarketIntelligenceReport",
    "MomentumIndex",
    "PeerMatchRule",
    "PeerMetricBenchmark",
    "QuantitativeIndex",
    "VehicleQuantitativeInput",
    "VehicleQuantitativeScores",
    "INVENTORY_PRESSURE_WEIGHTS",
    "MARKET_MOMENTUM_WEIGHTS",
    "PRICE_PRESSURE_WEIGHTS",
    "QUANTITATIVE_METHODOLOGY",
    "build_daily_market_intelligence",
    "calculate_comparable_vehicle_benchmarks",
    "calculate_market_quantitative_scores",
    "classify_market_momentum",
    "segment_family",
    "write_daily_market_intelligence",
]
