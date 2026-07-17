"""Database model package exports."""

from __future__ import annotations

from germania.db.base import Base, utc_now
from germania.db.models import (
    Brand,
    CollectionBatch,
    DataQualityIssue,
    DataSource,
    DataSourceCategory,
    EstimatedTransactionPrice,
    ExchangeRateObservation,
    MarketplaceListing,
    MarketplaceListingObservation,
    OfficialPriceObservation,
    RegistrationObservation,
    Vehicle,
    VehicleAlias,
    VehicleVariant,
)

__all__ = [
    "Base",
    "Brand",
    "CollectionBatch",
    "DataQualityIssue",
    "DataSource",
    "DataSourceCategory",
    "EstimatedTransactionPrice",
    "ExchangeRateObservation",
    "MarketplaceListing",
    "MarketplaceListingObservation",
    "OfficialPriceObservation",
    "RegistrationObservation",
    "Vehicle",
    "VehicleAlias",
    "VehicleVariant",
    "utc_now",
]
