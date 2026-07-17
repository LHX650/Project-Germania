"""Collection batch ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from germania.db.base import Base, utc_now

if TYPE_CHECKING:
    from germania.db.models.marketplace import MarketplaceListingObservation
    from germania.db.models.price import OfficialPriceObservation
    from germania.db.models.source import DataSource


class CollectionBatch(Base):
    """Manual import, file processing, API task, or future collection job."""

    __tablename__ = "collection_batches"
    __table_args__ = (
        CheckConstraint(
            "collection_method IN ("
            "'manual_download', 'api', 'html_parse', "
            "'browser_automation', 'manual_entry')",
            name="collection_method_allowed",
        ),
        CheckConstraint(
            "status IN ("
            "'pending', 'running', 'completed', 'partially_completed', "
            "'failed', 'cancelled')",
            name="status_allowed",
        ),
        CheckConstraint(
            "record_count IS NULL OR record_count >= 0",
            name="record_count_non_negative",
        ),
        CheckConstraint(
            "success_count IS NULL OR success_count >= 0",
            name="success_count_non_negative",
        ),
        CheckConstraint(
            "failure_count IS NULL OR failure_count >= 0",
            name="failure_count_non_negative",
        ),
        CheckConstraint(
            "record_count IS NULL OR success_count IS NULL OR failure_count IS NULL "
            "OR success_count + failure_count <= record_count",
            name="batch_counts_consistent",
        ),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="completion_window_valid",
        ),
        Index("ix_collection_batches_batch_id", "batch_id", unique=True),
        Index("ix_collection_batches_source_started", "data_source_id", "started_at"),
    )

    collection_batch_id: Mapped[int] = mapped_column(primary_key=True)
    data_source_id: Mapped[int] = mapped_column(
        ForeignKey(
            "data_sources.data_source_id",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    batch_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    record_type: Mapped[str | None] = mapped_column(String(50))
    collection_method: Mapped[str] = mapped_column(String(50), nullable=False)
    collection_job_id: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    record_count: Mapped[int | None]
    success_count: Mapped[int | None]
    failure_count: Mapped[int | None]
    source_file_name: Mapped[str | None] = mapped_column(String(500))
    raw_file_path: Mapped[str | None] = mapped_column(String(1000))
    raw_payload_reference: Mapped[str | None] = mapped_column(String(500))
    parser_version: Mapped[str | None] = mapped_column(String(120))
    checksum: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    data_source: Mapped[DataSource] = relationship(back_populates="collection_batches")
    official_price_observations: Mapped[list[OfficialPriceObservation]] = relationship(
        back_populates="collection_batch"
    )
    marketplace_listing_observations: Mapped[list[MarketplaceListingObservation]] = (
        relationship(back_populates="collection_batch")
    )
