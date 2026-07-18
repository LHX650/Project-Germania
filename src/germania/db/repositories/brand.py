"""Brand repository queries."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from germania.db.models import Brand
from germania.db.repositories.base import BaseRepository


class BrandRepository(BaseRepository[Brand]):
    """Repository for canonical brand records."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Brand)

    def get_by_name(self, canonical_brand: str) -> Brand | None:
        """Return a brand by canonical brand name."""

        statement = select(Brand).where(Brand.canonical_brand == canonical_brand)
        return self.session.scalars(statement).one_or_none()

    def list_active(self) -> list[Brand]:
        """Return active brands ordered by canonical name."""

        statement = (
            select(Brand).where(Brand.active.is_(True)).order_by(Brand.canonical_brand)
        )
        return list(self.session.scalars(statement).all())
