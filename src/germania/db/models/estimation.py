"""Estimated transaction price ORM model."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
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
    from germania.db.models.marketplace import (
        MarketplaceListing,
        MarketplaceListingObservation,
    )
    from germania.db.models.vehicle import VehicleVariant


class EstimatedTransactionPrice(Base):
    """Derived transaction-price estimate, not a confirmed transaction."""

    __tablename__ = "estimated_transaction_prices"
    __table_args__ = (
        UniqueConstraint(
            "input_reference",
            "estimation_method",
            "estimation_version",
            "estimated_at",
        ),
        CheckConstraint(
            "estimated_transaction_price >= 0",
            name="estimated_transaction_price_non_negative",
        ),
        CheckConstraint("length(currency) = 3", name="currency_length"),
        CheckConstraint(
            "confidence_level IN ('high', 'medium', 'low', 'unknown')",
            name="confidence_level_allowed",
        ),
        CheckConstraint(
            "length(estimation_method) > 0",
            name="estimation_method_not_empty",
        ),
        CheckConstraint(
            "length(estimation_version) > 0",
            name="estimation_version_not_empty",
        ),
        Index(
            "ix_estimated_transaction_prices_variant_estimated",
            "vehicle_variant_id",
            "estimated_at",
        ),
        Index(
            "ix_estimated_transaction_prices_confidence_estimated",
            "confidence_level",
            "estimated_at",
        ),
    )

    estimated_transaction_price_id: Mapped[int] = mapped_column(primary_key=True)
    marketplace_listing_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "marketplace_listings.marketplace_listing_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        )
    )
    marketplace_listing_observation_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "marketplace_listing_observations.marketplace_listing_observation_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        )
    )
    vehicle_variant_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "vehicle_variants.vehicle_variant_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        )
    )
    estimated_transaction_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    estimation_method: Mapped[str] = mapped_column(String(120), nullable=False)
    estimation_version: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence_level: Mapped[str] = mapped_column(String(50), nullable=False)
    input_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    estimated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    valid_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    marketplace_listing: Mapped[MarketplaceListing | None] = relationship(
        back_populates="estimated_transaction_prices"
    )
    marketplace_listing_observation: Mapped[MarketplaceListingObservation | None] = (
        relationship(back_populates="estimated_transaction_prices")
    )
    vehicle_variant: Mapped[VehicleVariant | None] = relationship(
        back_populates="estimated_transaction_prices"
    )
