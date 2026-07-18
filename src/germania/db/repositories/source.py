"""Data source repository queries."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from germania.db.models import DataSource
from germania.db.repositories.base import BaseRepository


class DataSourceRepository(BaseRepository[DataSource]):
    """Repository for configured data source records."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, DataSource)

    def get_by_source_id(self, source_id: str) -> DataSource | None:
        """Return a source by stable configuration source ID."""

        statement = select(DataSource).where(DataSource.source_id == source_id)
        return self.session.scalars(statement).one_or_none()

    def list_active(self) -> list[DataSource]:
        """Return active data sources ordered by source ID."""

        statement = (
            select(DataSource)
            .where(DataSource.active.is_(True))
            .order_by(DataSource.source_id)
        )
        return list(self.session.scalars(statement).all())
