"""Exchange-rate observation ORM model."""

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


class ExchangeRateObservation(Base):
    """Authoritative exchange-rate observation."""

    __tablename__ = "exchange_rate_observations"
    __table_args__ = (
        UniqueConstraint(
            "data_source_id",
            "base_currency",
            "quote_currency",
            "exchange_rate_date",
        ),
        CheckConstraint("length(base_currency) = 3", name="base_currency_length"),
        CheckConstraint("length(quote_currency) = 3", name="quote_currency_length"),
        CheckConstraint("exchange_rate > 0", name="exchange_rate_positive"),
        CheckConstraint(
            "base_currency <> quote_currency",
            name="currency_pair_not_self",
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
            "ix_exchange_rate_observations_currency_pair_date",
            "base_currency",
            "quote_currency",
            "exchange_rate_date",
        ),
        Index(
            "ix_exchange_rate_observations_source_pair_date",
            "data_source_id",
            "base_currency",
            "quote_currency",
            "exchange_rate_date",
            unique=True,
        ),
    )

    exchange_rate_observation_id: Mapped[int] = mapped_column(primary_key=True)
    data_source_id: Mapped[int] = mapped_column(
        ForeignKey(
            "data_sources.data_source_id",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    exchange_rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    data_quality_status: Mapped[str | None] = mapped_column(String(50))
    validation_status: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    data_source: Mapped[DataSource] = relationship(
        back_populates="exchange_rate_observations"
    )
