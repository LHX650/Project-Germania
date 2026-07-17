"""Brand, vehicle, alias, and variant ORM models."""

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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from germania.db.base import Base, utc_now

if TYPE_CHECKING:
    from germania.db.models.estimation import EstimatedTransactionPrice
    from germania.db.models.marketplace import MarketplaceListing
    from germania.db.models.price import OfficialPriceObservation
    from germania.db.models.registration import RegistrationObservation


class Brand(Base):
    """Canonical automotive brand."""

    __tablename__ = "brands"

    brand_id: Mapped[int] = mapped_column(primary_key=True)
    canonical_brand: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )
    chinese_brand: Mapped[str | None] = mapped_column(String(100))
    manufacturer: Mapped[str | None] = mapped_column(String(255))
    country_of_origin: Mapped[str | None] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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

    vehicles: Mapped[list[Vehicle]] = relationship(back_populates="brand")


class Vehicle(Base):
    """Canonical research vehicle model."""

    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("brand_id", "canonical_model"),
        CheckConstraint(
            "priority_level IN ('high', 'medium', 'low')",
            name="priority_level_allowed",
        ),
        CheckConstraint("active IN (0, 1)", name="active_boolean"),
        Index("ix_vehicles_brand_model", "brand_id", "canonical_model"),
        Index("ix_vehicles_canonical_model", "canonical_model"),
    )

    vehicle_id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.brand_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    canonical_model: Mapped[str] = mapped_column(String(100), nullable=False)
    chinese_model: Mapped[str | None] = mapped_column(String(100))
    vehicle_segment: Mapped[str | None] = mapped_column(String(100))
    body_type: Mapped[str | None] = mapped_column(String(50))
    default_powertrain: Mapped[str | None] = mapped_column(String(50))
    priority_level: Mapped[str] = mapped_column(String(20), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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

    brand: Mapped[Brand] = relationship(back_populates="vehicles")
    aliases: Mapped[list[VehicleAlias]] = relationship(
        back_populates="vehicle",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    variants: Mapped[list[VehicleVariant]] = relationship(back_populates="vehicle")
    marketplace_listings: Mapped[list[MarketplaceListing]] = relationship(
        back_populates="vehicle"
    )
    registration_observations: Mapped[list[RegistrationObservation]] = relationship(
        back_populates="vehicle"
    )


class VehicleAlias(Base):
    """Exact vehicle alias for normalization."""

    __tablename__ = "vehicle_aliases"
    __table_args__ = (
        CheckConstraint("length(alias_text) > 0", name="alias_text_not_empty"),
        CheckConstraint(
            "alias_type IN ('official', 'german', 'english', 'marketplace', 'common')",
            name="alias_type_allowed",
        ),
        Index("ix_vehicle_aliases_normalized_alias", "normalized_alias", unique=True),
    )

    vehicle_alias_id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.vehicle_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    alias_text: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )
    alias_language: Mapped[str | None] = mapped_column(String(50))
    alias_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    vehicle: Mapped[Vehicle] = relationship(back_populates="aliases")


class VehicleVariant(Base):
    """Model-year, trim, edition, powertrain, and specification variant."""

    __tablename__ = "vehicle_variants"
    __table_args__ = (
        UniqueConstraint(
            "vehicle_id",
            "model_year",
            "trim_name",
            "variant_name",
            "edition_name",
            "drivetrain",
        ),
        CheckConstraint(
            "battery_capacity_kwh IS NULL OR battery_capacity_kwh >= 0",
            name="battery_capacity_kwh_non_negative",
        ),
        CheckConstraint(
            "engine_power_kw IS NULL OR engine_power_kw >= 0",
            name="engine_power_kw_non_negative",
        ),
        CheckConstraint(
            "engine_power_ps IS NULL OR engine_power_ps >= 0",
            name="engine_power_ps_non_negative",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL "
            "OR effective_to >= effective_from",
            name="effective_window_valid",
        ),
        CheckConstraint("active IN (0, 1)", name="active_boolean"),
        Index("ix_vehicle_variants_vehicle_year", "vehicle_id", "model_year"),
    )

    vehicle_variant_id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.vehicle_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    model_year: Mapped[str | None] = mapped_column(String(20))
    generation: Mapped[str | None] = mapped_column(String(100))
    trim_name: Mapped[str | None] = mapped_column(String(255))
    variant_name: Mapped[str | None] = mapped_column(String(255))
    edition_name: Mapped[str | None] = mapped_column(String(255))
    drivetrain: Mapped[str | None] = mapped_column(String(50))
    transmission: Mapped[str | None] = mapped_column(String(50))
    powertrain: Mapped[str | None] = mapped_column(String(50))
    fuel_type: Mapped[str | None] = mapped_column(String(50))
    battery_capacity_kwh: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    engine_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    engine_power_ps: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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

    vehicle: Mapped[Vehicle] = relationship(back_populates="variants")
    official_price_observations: Mapped[list[OfficialPriceObservation]] = relationship(
        back_populates="vehicle_variant"
    )
    marketplace_listings: Mapped[list[MarketplaceListing]] = relationship(
        back_populates="vehicle_variant"
    )
    registration_observations: Mapped[list[RegistrationObservation]] = relationship(
        back_populates="vehicle_variant"
    )
    estimated_transaction_prices: Mapped[list[EstimatedTransactionPrice]] = (
        relationship(back_populates="vehicle_variant")
    )
