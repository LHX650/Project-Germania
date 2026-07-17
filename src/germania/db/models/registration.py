"""Registration observation ORM model."""

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
    from germania.db.models.source import DataSource
    from germania.db.models.vehicle import Vehicle, VehicleVariant


class RegistrationObservation(Base):
    """Registration count or explicitly labeled sales metric observation."""

    __tablename__ = "registration_observations"
    __table_args__ = (
        UniqueConstraint(
            "data_source_id",
            "vehicle_id",
            "registration_period",
            "registration_scope",
            "sales_metric_type",
        ),
        CheckConstraint(
            "registration_count IS NULL OR registration_count >= 0",
            name="registration_count_non_negative",
        ),
        CheckConstraint(
            "sales_value IS NULL OR sales_value >= 0",
            name="sales_value_non_negative",
        ),
        CheckConstraint(
            "sales_metric_type IN ("
            "'new_registration', 'retail_sales', 'wholesale_sales', "
            "'delivery', 'unknown')",
            name="sales_metric_type_allowed",
        ),
        CheckConstraint(
            "country_code IS NULL OR length(country_code) = 2",
            name="country_code_length",
        ),
        CheckConstraint(
            "source_page_number IS NULL OR source_page_number > 0",
            name="source_page_number_positive",
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
            "ix_registration_observations_vehicle_period",
            "vehicle_id",
            "registration_period",
        ),
        Index(
            "ix_registration_observations_scope_metric_period",
            "registration_scope",
            "sales_metric_type",
            "registration_period",
        ),
    )

    registration_observation_id: Mapped[int] = mapped_column(primary_key=True)
    data_source_id: Mapped[int] = mapped_column(
        ForeignKey(
            "data_sources.data_source_id",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
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
    canonical_brand: Mapped[str | None] = mapped_column(String(100))
    canonical_model: Mapped[str | None] = mapped_column(String(100))
    raw_brand: Mapped[str | None] = mapped_column(String(255))
    raw_model: Mapped[str | None] = mapped_column(String(255))
    registration_count: Mapped[int | None]
    sales_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    sales_metric_type: Mapped[str] = mapped_column(String(50), nullable=False)
    registration_period: Mapped[str] = mapped_column(String(20), nullable=False)
    registration_scope: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str | None] = mapped_column(String(100))
    country_code: Mapped[str | None] = mapped_column(String(2))
    state: Mapped[str | None] = mapped_column(String(100))
    valid_date: Mapped[date | None] = mapped_column(Date)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    source_record_id: Mapped[str | None] = mapped_column(String(255))
    source_file_name: Mapped[str | None] = mapped_column(String(500))
    source_page_number: Mapped[int | None]
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

    data_source: Mapped[DataSource] = relationship(
        back_populates="registration_observations"
    )
    vehicle: Mapped[Vehicle | None] = relationship(
        back_populates="registration_observations"
    )
    vehicle_variant: Mapped[VehicleVariant | None] = relationship(
        back_populates="registration_observations"
    )
