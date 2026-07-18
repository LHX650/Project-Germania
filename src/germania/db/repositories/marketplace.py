"""Marketplace listing repository queries and idempotent upserts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from germania.db.models import DataSource, MarketplaceListing, MarketplacePriceHistory
from germania.db.repositories.base import BaseRepository
from germania.db.repositories.source import DataSourceRepository

if TYPE_CHECKING:
    from germania.collectors.marketplace.models import MarketplaceListingRecord


@dataclass(frozen=True)
class MarketplaceListingUpsertResult:
    """Result summary for one marketplace listing upsert."""

    listing: MarketplaceListing
    price_history: MarketplacePriceHistory | None = None
    created: bool = False
    updated: bool = False
    price_history_created: bool = False

    @property
    def unchanged(self) -> bool:
        """Return whether the listing and price history were unchanged."""

        return not self.created and not self.updated and not self.price_history_created


class MarketplaceListingRepository(BaseRepository[MarketplaceListing]):
    """Repository for current marketplace listings and price history."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, MarketplaceListing)

    def get_by_source_listing_key(
        self,
        *,
        source_id: str,
        external_listing_id: str,
    ) -> MarketplaceListing | None:
        """Return one listing by configured source ID and external listing ID."""

        statement = (
            select(MarketplaceListing)
            .join(
                DataSource,
                MarketplaceListing.data_source_id == DataSource.data_source_id,
            )
            .where(
                DataSource.source_id == source_id,
                MarketplaceListing.external_listing_id == external_listing_id,
            )
        )
        return self.session.scalars(statement).one_or_none()

    def list_active(
        self,
        *,
        source_id: str | None = None,
        vehicle_id: int | None = None,
    ) -> list[MarketplaceListing]:
        """Return active listings, optionally scoped by source or vehicle."""

        statement = select(MarketplaceListing).where(
            MarketplaceListing.active.is_(True)
        )
        if source_id is not None:
            statement = statement.join(
                DataSource,
                MarketplaceListing.data_source_id == DataSource.data_source_id,
            ).where(DataSource.source_id == source_id)
        if vehicle_id is not None:
            statement = statement.where(MarketplaceListing.vehicle_id == vehicle_id)
        statement = statement.order_by(MarketplaceListing.marketplace_listing_id)
        return list(self.session.scalars(statement).all())

    def upsert_listing_record(
        self,
        record: MarketplaceListingRecord,
        *,
        vehicle_id: int | None = None,
        vehicle_variant_id: int | None = None,
    ) -> MarketplaceListingUpsertResult:
        """Insert or update one marketplace listing without creating master data."""

        _validate_record(record)
        source = DataSourceRepository(self.session).get_by_source_id(record.source_id)
        if source is None:
            msg = (
                "Data source is not available for marketplace listing record: "
                f"{record.source_id}"
            )
            raise ValueError(msg)

        existing = self.get_by_source_listing_key(
            source_id=record.source_id,
            external_listing_id=record.external_listing_id,
        )
        values = _listing_values(
            record,
            data_source_id=source.data_source_id,
            vehicle_id=vehicle_id,
            vehicle_variant_id=vehicle_variant_id,
        )

        if existing is None:
            listing = self.add(MarketplaceListing(**values))
            price_history = self.add_price_history_if_changed(listing, record)
            return MarketplaceListingUpsertResult(
                listing=listing,
                price_history=price_history,
                created=True,
                price_history_created=price_history is not None,
            )

        values["first_seen_at"] = existing.first_seen_at
        changes = _changed_values(existing, values)
        if changes:
            self.update(existing, changes)

        price_history = self.add_price_history_if_changed(existing, record)
        return MarketplaceListingUpsertResult(
            listing=existing,
            price_history=price_history,
            updated=bool(changes),
            price_history_created=price_history is not None,
        )

    def add_price_history_if_changed(
        self,
        listing: MarketplaceListing,
        record: MarketplaceListingRecord,
    ) -> MarketplacePriceHistory | None:
        """Append a price history row only when the listing price changed."""

        if record.price_amount is None:
            return None

        latest = self.get_latest_price_history(listing.marketplace_listing_id)
        if latest is not None and _same_price(
            latest.price_amount,
            latest.currency,
            record.price_amount,
            record.currency,
        ):
            return None

        observed_at = record.source_updated_at or record.collected_at
        price_history = MarketplacePriceHistory(
            marketplace_listing_id=listing.marketplace_listing_id,
            price_amount=record.price_amount,
            currency=record.currency or "EUR",
            observed_at=observed_at,
            collected_at=record.collected_at,
            source_updated_at=record.source_updated_at,
            listing_url=record.listing_url,
            notes=None,
        )
        return BaseRepository(self.session, MarketplacePriceHistory).add(price_history)

    def get_latest_price_history(
        self,
        marketplace_listing_id: int,
    ) -> MarketplacePriceHistory | None:
        """Return the latest price history row for a listing."""

        statement = (
            select(MarketplacePriceHistory)
            .where(
                MarketplacePriceHistory.marketplace_listing_id == marketplace_listing_id
            )
            .order_by(
                MarketplacePriceHistory.observed_at.desc(),
                MarketplacePriceHistory.marketplace_price_history_id.desc(),
            )
            .limit(1)
        )
        return self.session.scalars(statement).one_or_none()

    def set_active(
        self,
        listing: MarketplaceListing,
        *,
        active: bool,
        seen_at: datetime | None = None,
    ) -> MarketplaceListing:
        """Update current active state and optional last-seen timestamp."""

        changes: dict[str, Any] = {"active": active}
        if seen_at is not None:
            changes["last_seen_at"] = _to_aware_utc(seen_at)
        return self.update(listing, changes)


def _listing_values(
    record: MarketplaceListingRecord,
    *,
    data_source_id: int,
    vehicle_id: int | None,
    vehicle_variant_id: int | None,
) -> dict[str, Any]:
    collected_at = _to_aware_utc(record.collected_at)
    source_updated_at = (
        _to_aware_utc(record.source_updated_at)
        if record.source_updated_at is not None
        else None
    )
    return {
        "data_source_id": data_source_id,
        "external_listing_id": record.external_listing_id,
        "vehicle_id": vehicle_id,
        "vehicle_variant_id": vehicle_variant_id,
        "brand_name": record.brand_name,
        "model_name": record.model_name,
        "variant_name": record.variant_name,
        "title": record.title,
        "current_price_amount": record.price_amount,
        "currency": record.currency or "EUR",
        "registration_year": record.registration_year,
        "model_year": None,
        "first_registration_date": None,
        "fuel_type": record.fuel_type,
        "transmission": record.transmission,
        "power_kw": record.power_kw,
        "vehicle_condition": record.vehicle_condition,
        "body_type": record.body_type,
        "color": record.color,
        "mileage_km": record.mileage_km,
        "owner_count": None,
        "seller_type": record.seller_type,
        "seller_name": record.seller_name,
        "country_code": None,
        "state": None,
        "seller_city": record.seller_city,
        "seller_postcode": record.seller_postcode,
        "listing_url": record.listing_url,
        "first_seen_at": collected_at,
        "last_seen_at": collected_at,
        "last_collected_at": collected_at,
        "source_updated_at": source_updated_at,
        "active": True,
        "notes": None,
    }


def _validate_record(record: MarketplaceListingRecord) -> None:
    if not record.source_id:
        msg = "Marketplace listing record requires source_id"
        raise ValueError(msg)
    if not record.external_listing_id:
        msg = "Marketplace listing record requires external_listing_id"
        raise ValueError(msg)
    if record.price_amount is not None and record.price_amount < 0:
        msg = "Marketplace listing record price_amount must be non-negative"
        raise ValueError(msg)
    if len(record.currency or "") != 3:
        msg = "Marketplace listing record currency must be a 3-letter code"
        raise ValueError(msg)
    if record.mileage_km is not None and record.mileage_km < 0:
        msg = "Marketplace listing record mileage_km must be non-negative"
        raise ValueError(msg)


def _changed_values(
    listing: MarketplaceListing,
    values: dict[str, Any],
) -> dict[str, Any]:
    return {
        field_name: value
        for field_name, value in values.items()
        if not _values_equal(getattr(listing, field_name), value)
    }


def _same_price(
    left_amount: Decimal,
    left_currency: str,
    right_amount: Decimal,
    right_currency: str,
) -> bool:
    return left_amount == right_amount and left_currency == (right_currency or "EUR")


def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, datetime) and isinstance(right, datetime):
        return _to_naive_utc(left) == _to_naive_utc(right)
    return left == right


def _to_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
