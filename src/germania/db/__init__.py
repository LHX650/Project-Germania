"""Database model package exports."""

from __future__ import annotations

from germania.db.base import Base, utc_now
from germania.db.engine import create_database_engine
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
    MarketplacePriceHistory,
    OfficialPriceObservation,
    RegistrationObservation,
    Vehicle,
    VehicleAlias,
    VehicleVariant,
)
from germania.db.session import create_session_factory, session_scope

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
    "MarketplacePriceHistory",
    "OfficialPriceObservation",
    "RegistrationObservation",
    "Vehicle",
    "VehicleAlias",
    "VehicleVariant",
    "create_database_engine",
    "create_session_factory",
    "session_scope",
    "utc_now",
]
