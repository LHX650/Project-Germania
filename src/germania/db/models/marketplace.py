"""Marketplace listing ORM models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from germania.db.base import Base, utc_now

if TYPE_CHECKING:
    from germania.db.models.collection import CollectionBatch
    from germania.db.models.estimation import EstimatedTransactionPrice
    from germania.db.models.source import DataSource
    from germania.db.models.vehicle import Vehicle, VehicleVariant


class MarketplaceListing(Base):
    """Current marketplace listing state keyed by source and external ID."""

    __tablename__ = "marketplace_listings"
    __table_args__ = (
        UniqueConstraint(
            "data_source_id",
            "external_listing_id",
            name="uq_marketplace_listings_source_external",
        ),
        CheckConstraint(
            "current_price_amount IS NULL OR current_price_amount >= 0",
            name="current_price_amount_non_negative",
        ),
        CheckConstraint("length(currency) = 3", name="currency_length"),
        CheckConstraint(
            "mileage_km IS NULL OR mileage_km >= 0",
            name="mileage_km_non_negative",
        ),
        CheckConstraint(
            "owner_count IS NULL OR owner_count >= 0",
            name="owner_count_non_negative",
        ),
        CheckConstraint(
            "power_kw IS NULL OR power_kw >= 0",
            name="power_kw_non_negative",
        ),
        CheckConstraint(
            "registration_year IS NULL OR registration_year >= 1886",
            name="registration_year_valid",
        ),
        CheckConstraint(
            "last_seen_at IS NULL OR first_seen_at IS NULL "
            "OR last_seen_at >= first_seen_at",
            name="seen_window_valid",
        ),
        CheckConstraint(
            "last_collected_at IS NULL OR first_seen_at IS NULL "
            "OR last_collected_at >= first_seen_at",
            name="collection_window_valid",
        ),
        CheckConstraint(
            "vehicle_condition IS NULL OR vehicle_condition IN ("
            "'new', 'used', 'demonstrator', 'unknown')",
            name="vehicle_condition_allowed",
        ),
        CheckConstraint(
            "seller_type IS NULL OR seller_type IN ("
            "'manufacturer', 'dealer', 'private', 'marketplace', 'unknown')",
            name="seller_type_allowed",
        ),
        CheckConstraint(
            "country_code IS NULL OR length(country_code) = 2",
            name="country_code_length",
        ),
        CheckConstraint("active IN (0, 1)", name="active_boolean"),
        Index(
            "ix_marketplace_listings_source_listing",
            "data_source_id",
            "external_listing_id",
            unique=True,
        ),
        Index("ix_marketplace_listings_vehicle_active", "vehicle_id", "active"),
        Index(
            "ix_marketplace_listings_variant_active",
            "vehicle_variant_id",
            "active",
        ),
        Index("ix_marketplace_listings_seller_city", "seller_city"),
        Index("ix_marketplace_listings_seller_postcode", "seller_postcode"),
        Index("ix_marketplace_listings_current_price", "current_price_amount"),
        Index("ix_marketplace_listings_last_collected", "last_collected_at"),
    )

    marketplace_listing_id: Mapped[int] = mapped_column(primary_key=True)
    data_source_id: Mapped[int] = mapped_column(
        ForeignKey(
            "data_sources.data_source_id",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    external_listing_id: Mapped[str] = mapped_column(String(255), nullable=False)
    vehicle_id: Mapped[int | None] = mapped_column(
        ForeignKey("vehicles.vehicle_id", ondelete="SET NULL", onupdate="CASCADE")
    )
    vehicle_variant_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "vehicle_variants.vehicle_variant_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        )
    )
    brand_name: Mapped[str | None] = mapped_column(String(255))
    model_name: Mapped[str | None] = mapped_column(String(255))
    variant_name: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(500))
    current_price_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    registration_year: Mapped[int | None]
    model_year: Mapped[str | None] = mapped_column(String(20))
    first_registration_date: Mapped[date | None] = mapped_column(Date)
    fuel_type: Mapped[str | None] = mapped_column(String(50))
    transmission: Mapped[str | None] = mapped_column(String(50))
    power_kw: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    vehicle_condition: Mapped[str | None] = mapped_column(String(50))
    body_type: Mapped[str | None] = mapped_column(String(50))
    color: Mapped[str | None] = mapped_column(String(100))
    mileage_km: Mapped[int | None]
    owner_count: Mapped[int | None]
    seller_type: Mapped[str | None] = mapped_column(String(50))
    seller_name: Mapped[str | None] = mapped_column(String(255))
    country_code: Mapped[str | None] = mapped_column(String(2))
    state: Mapped[str | None] = mapped_column(String(100))
    seller_city: Mapped[str | None] = mapped_column(String(120))
    seller_postcode: Mapped[str | None] = mapped_column(String(20))
    listing_url: Mapped[str | None] = mapped_column(String(1000))
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    data_source: Mapped[DataSource] = relationship(
        back_populates="marketplace_listings"
    )
    vehicle: Mapped[Vehicle | None] = relationship(
        back_populates="marketplace_listings"
    )
    vehicle_variant: Mapped[VehicleVariant | None] = relationship(
        back_populates="marketplace_listings"
    )
    observations: Mapped[list[MarketplaceListingObservation]] = relationship(
        back_populates="marketplace_listing"
    )
    price_history: Mapped[list[MarketplacePriceHistory]] = relationship(
        back_populates="marketplace_listing"
    )
    estimated_transaction_prices: Mapped[list[EstimatedTransactionPrice]] = (
        relationship(back_populates="marketplace_listing")
    )


class MarketplaceListingObservation(Base):
    """Dated observation for a stable marketplace listing."""

    __tablename__ = "marketplace_listing_observations"
    __table_args__ = (
        UniqueConstraint("marketplace_listing_id", "observed_at"),
        CheckConstraint(
            "listed_price IS NULL OR listed_price >= 0",
            name="listed_price_non_negative",
        ),
        CheckConstraint(
            "currency IS NULL OR length(currency) = 3",
            name="currency_length",
        ),
        CheckConstraint(
            "price_includes_vat IS NULL OR price_includes_vat IN (0, 1)",
            name="price_includes_vat_boolean",
        ),
        CheckConstraint(
            "listing_status IN ('active', 'removed', 'sold', 'unavailable', 'unknown')",
            name="listing_status_allowed",
        ),
        CheckConstraint(
            "mileage_km IS NULL OR mileage_km >= 0",
            name="mileage_km_non_negative",
        ),
        CheckConstraint(
            "data_quality_status IS NULL OR data_quality_status IN ("
            "'valid', 'warning', 'invalid', 'unknown')",
            name="data_quality_status_allowed",
        ),
        CheckConstraint(
            "validation_status IS NULL OR validation_status IN ("
            "'pending', 'passed', 'failed')",
            name="validation_status_allowed",
        ),
        Index(
            "ix_marketplace_listing_observations_listing_observed",
            "marketplace_listing_id",
            "observed_at",
            unique=True,
        ),
        Index("ix_marketplace_listing_observations_listed_price", "listed_price"),
    )

    marketplace_listing_observation_id: Mapped[int] = mapped_column(primary_key=True)
    marketplace_listing_id: Mapped[int] = mapped_column(
        ForeignKey(
            "marketplace_listings.marketplace_listing_id",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    collection_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "collection_batches.collection_batch_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        )
    )
    listed_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    price_includes_vat: Mapped[bool | None] = mapped_column(Boolean)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    listing_status: Mapped[str] = mapped_column(String(50), nullable=False)
    mileage_km: Mapped[int | None]
    source_url: Mapped[str | None] = mapped_column(String(1000))
    data_quality_status: Mapped[str | None] = mapped_column(String(50))
    validation_status: Mapped[str | None] = mapped_column(String(50))
    duplicate_key: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    marketplace_listing: Mapped[MarketplaceListing] = relationship(
        back_populates="observations"
    )
    collection_batch: Mapped[CollectionBatch | None] = relationship(
        back_populates="marketplace_listing_observations"
    )
    estimated_transaction_prices: Mapped[list[EstimatedTransactionPrice]] = (
        relationship(back_populates="marketplace_listing_observation")
    )


class MarketplacePriceHistory(Base):
    """Price-change history for one marketplace listing."""

    __tablename__ = "marketplace_price_history"
    __table_args__ = (
        UniqueConstraint("marketplace_listing_id", "observed_at"),
        CheckConstraint("price_amount >= 0", name="price_amount_non_negative"),
        CheckConstraint("length(currency) = 3", name="currency_length"),
        Index(
            "ix_marketplace_price_history_listing_observed",
            "marketplace_listing_id",
            "observed_at",
            unique=True,
        ),
        Index("ix_marketplace_price_history_price", "price_amount"),
    )

    marketplace_price_history_id: Mapped[int] = mapped_column(primary_key=True)
    marketplace_listing_id: Mapped[int] = mapped_column(
        ForeignKey(
            "marketplace_listings.marketplace_listing_id",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    price_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    listing_url: Mapped[str | None] = mapped_column(String(1000))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    marketplace_listing: Mapped[MarketplaceListing] = relationship(
        back_populates="price_history"
    )
