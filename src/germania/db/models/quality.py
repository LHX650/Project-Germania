"""Data quality issue ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from germania.db.base import Base, utc_now


class DataQualityIssue(Base):
    """Quality issue linked through a generic entity reference.

    The `(entity_type, entity_id)` pair can reference any model table, so this
    design intentionally does not declare a database-level foreign key. Referential
    integrity for this generic link must be checked by the quality layer.
    """

    __tablename__ = "data_quality_issues"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low', 'informational')",
            name="severity_allowed",
        ),
        CheckConstraint(
            "resolution_status IN ("
            "'open', 'investigating', 'resolved', 'accepted', 'ignored')",
            name="resolution_status_allowed",
        ),
        CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= detected_at",
            name="resolution_window_valid",
        ),
        Index("ix_data_quality_issues_entity", "entity_type", "entity_id"),
        Index(
            "ix_data_quality_issues_resolution_severity",
            "resolution_status",
            "severity",
        ),
    )

    data_quality_issue_id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False)
    issue_code: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(50), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[str | None] = mapped_column(Text)
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
