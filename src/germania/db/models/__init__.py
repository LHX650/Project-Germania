"""ORM model exports for Project Germania."""

from __future__ import annotations

from germania.db.models.collection import CollectionBatch
from germania.db.models.estimation import EstimatedTransactionPrice
from germania.db.models.exchange_rate import ExchangeRateObservation
from germania.db.models.marketplace import (
    MarketplaceListing,
    MarketplaceListingObservation,
)
from germania.db.models.price import OfficialPriceObservation
from germania.db.models.quality import DataQualityIssue
from germania.db.models.registration import RegistrationObservation
from germania.db.models.source import DataSource, DataSourceCategory
from germania.db.models.vehicle import Brand, Vehicle, VehicleAlias, VehicleVariant

__all__ = [
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
]
