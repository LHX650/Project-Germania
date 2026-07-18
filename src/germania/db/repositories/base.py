"""Generic repository helpers for SQLAlchemy ORM models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import DeclarativeBase, Session


class BaseRepository[ModelT: DeclarativeBase]:
    """Small CRUD wrapper around a SQLAlchemy session and mapped model."""

    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def add(self, instance: ModelT) -> ModelT:
        """Add an instance to the current transaction and flush it."""

        self.session.add(instance)
        self.session.flush()
        return instance

    def get_by_id(self, entity_id: object) -> ModelT | None:
        """Return one instance by primary key, or ``None`` if missing."""

        return self.session.get(self.model, entity_id)

    def list(self, *, offset: int = 0, limit: int | None = None) -> list[ModelT]:
        """Return model instances ordered by primary key."""

        _validate_non_negative(offset, "offset")
        if limit is not None:
            _validate_non_negative(limit, "limit")

        statement = select(self.model).order_by(*self._primary_key_columns())
        if offset:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)

        return list(self.session.scalars(statement).all())

    def update(
        self,
        instance: ModelT,
        values: Mapping[str, Any] | None = None,
        **changes: Any,
    ) -> ModelT:
        """Apply column updates to an instance and flush them."""

        update_values = dict(values or {})
        update_values.update(changes)
        self._validate_update_columns(update_values)

        for field_name, value in update_values.items():
            setattr(instance, field_name, value)

        self.session.add(instance)
        self.session.flush()
        return instance

    def delete(self, instance: ModelT) -> None:
        """Delete an instance from the current transaction and flush it."""

        self.session.delete(instance)
        self.session.flush()

    def exists(self, entity_id: object) -> bool:
        """Return whether an instance exists for the given primary key."""

        return self.get_by_id(entity_id) is not None

    def count(self) -> int:
        """Return the total number of rows for the model."""

        result = self.session.scalar(select(func.count()).select_from(self.model))
        return int(result or 0)

    def _primary_key_columns(self) -> Sequence[Any]:
        mapper = inspect(self.model)
        return mapper.primary_key

    def _validate_update_columns(self, values: Mapping[str, Any]) -> None:
        column_names = set(self.model.__table__.columns.keys())
        unknown_columns = sorted(set(values).difference(column_names))
        if unknown_columns:
            unknown = ", ".join(unknown_columns)
            msg = f"{self.model.__name__} has no writable column(s): {unknown}"
            raise ValueError(msg)


def _validate_non_negative(value: int, name: str) -> None:
    if value < 0:
        msg = f"{name} must be non-negative"
        raise ValueError(msg)
