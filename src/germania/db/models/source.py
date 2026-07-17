"""Data source ORM models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from germania.db.base import Base, utc_now

if TYPE_CHECKING:
    from germania.db.models.collection import CollectionBatch
    from germania.db.models.exchange_rate import ExchangeRateObservation
    from germania.db.models.marketplace import MarketplaceListing
    from germania.db.models.price import OfficialPriceObservation
    from germania.db.models.registration import RegistrationObservation


class DataSource(Base):
    """Planned data source definition from configuration."""

    __tablename__ = "data_sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ("
            "'government', 'industry_association', 'central_bank', "
            "'manufacturer', 'marketplace')",
            name="source_type_allowed",
        ),
        CheckConstraint(
            "length(country_code) = 2",
            name="country_code_length",
        ),
        CheckConstraint(
            "update_frequency IN ("
            "'daily', 'weekly', 'monthly', 'quarterly', 'irregular', 'manual')",
            name="update_frequency_allowed",
        ),
        CheckConstraint(
            "authority_level IN ("
            "'primary_authoritative', 'primary_commercial', "
            "'secondary_authoritative', 'secondary_commercial')",
            name="authority_level_allowed",
        ),
        CheckConstraint(
            "collection_method IN ("
            "'manual_download', 'api', 'html_parse', "
            "'browser_automation', 'manual_entry')",
            name="collection_method_allowed",
        ),
        CheckConstraint("active IN (0, 1)", name="active_boolean"),
    )

    data_source_id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    update_frequency: Mapped[str] = mapped_column(String(50), nullable=False)
    authority_level: Mapped[str] = mapped_column(String(50), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    collection_method: Mapped[str] = mapped_column(String(50), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
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

    categories: Mapped[list[DataSourceCategory]] = relationship(
        back_populates="data_source",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    collection_batches: Mapped[list[CollectionBatch]] = relationship(
        back_populates="data_source"
    )
    official_price_observations: Mapped[list[OfficialPriceObservation]] = relationship(
        back_populates="data_source"
    )
    marketplace_listings: Mapped[list[MarketplaceListing]] = relationship(
        back_populates="data_source"
    )
    registration_observations: Mapped[list[RegistrationObservation]] = relationship(
        back_populates="data_source"
    )
    exchange_rate_observations: Mapped[list[ExchangeRateObservation]] = relationship(
        back_populates="data_source"
    )


class DataSourceCategory(Base):
    """Normalized data category for a source."""

    __tablename__ = "data_source_categories"
    __table_args__ = (
        CheckConstraint(
            "data_category IN ("
            "'registrations', 'official_prices', 'listings', "
            "'exchange_rates', 'market_statistics', 'vehicle_specifications')",
            name="data_category_allowed",
        ),
        UniqueConstraint("data_source_id", "data_category"),
        Index(
            "ix_data_source_categories_category_source",
            "data_category",
            "data_source_id",
        ),
    )

    data_source_category_id: Mapped[int] = mapped_column(primary_key=True)
    data_source_id: Mapped[int] = mapped_column(
        ForeignKey(
            "data_sources.data_source_id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    data_category: Mapped[str] = mapped_column(String(50), nullable=False)

    data_source: Mapped[DataSource] = relationship(back_populates="categories")
