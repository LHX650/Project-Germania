"""Official price observation ORM model."""

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
    from germania.db.models.source import DataSource
    from germania.db.models.vehicle import VehicleVariant


class OfficialPriceObservation(Base):
    """Official manufacturer price observation."""

    __tablename__ = "official_price_observations"
    __table_args__ = (
        UniqueConstraint(
            "vehicle_variant_id",
            "data_source_id",
            "valid_date",
            "official_price",
        ),
        CheckConstraint("official_price >= 0", name="official_price_non_negative"),
        CheckConstraint("length(currency) = 3", name="currency_length"),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL "
            "OR effective_to >= effective_from",
            name="effective_window_valid",
        ),
        CheckConstraint(
            "price_includes_vat IS NULL OR price_includes_vat IN (0, 1)",
            name="price_includes_vat_boolean",
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
            "ix_official_price_observations_variant_valid_date",
            "vehicle_variant_id",
            "valid_date",
        ),
        Index(
            "ix_official_price_observations_source_valid_date",
            "data_source_id",
            "valid_date",
        ),
    )

    official_price_observation_id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_variant_id: Mapped[int] = mapped_column(
        ForeignKey(
            "vehicle_variants.vehicle_variant_id",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    data_source_id: Mapped[int] = mapped_column(
        ForeignKey(
            "data_sources.data_source_id",
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
    official_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    price_includes_vat: Mapped[bool | None] = mapped_column(Boolean)
    valid_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    source_record_id: Mapped[str | None] = mapped_column(String(255))
    raw_brand: Mapped[str | None] = mapped_column(String(255))
    raw_model: Mapped[str | None] = mapped_column(String(255))
    raw_variant_name: Mapped[str | None] = mapped_column(String(255))
    data_quality_status: Mapped[str | None] = mapped_column(String(50))
    validation_status: Mapped[str | None] = mapped_column(String(50))
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

    vehicle_variant: Mapped[VehicleVariant] = relationship(
        back_populates="official_price_observations"
    )
    data_source: Mapped[DataSource] = relationship(
        back_populates="official_price_observations"
    )
    collection_batch: Mapped[CollectionBatch | None] = relationship(
        back_populates="official_price_observations"
    )
