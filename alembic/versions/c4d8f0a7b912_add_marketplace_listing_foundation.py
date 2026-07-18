"""add marketplace listing foundation

Revision ID: c4d8f0a7b912
Revises: 8f4c2d9a1b6e
Create Date: 2026-07-19 00:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d8f0a7b912"
down_revision: str | Sequence[str] | None = "8f4c2d9a1b6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LISTINGS_TABLE = "marketplace_listings"
OLD_LISTINGS_UNIQUE = "uq_marketplace_listings_data_source_id"


def upgrade() -> None:
    """Upgrade schema."""

    with op.batch_alter_table(
        LISTINGS_TABLE,
        copy_from=_marketplace_listings_table_before(),
    ) as batch_op:
        batch_op.drop_index("ix_marketplace_listings_city")
        batch_op.drop_index("ix_marketplace_listings_postal_code")
        batch_op.drop_index("ix_marketplace_listings_source_listing")
        batch_op.drop_constraint(OLD_LISTINGS_UNIQUE, type_="unique")
        batch_op.drop_constraint(
            op.f("ck_marketplace_listings_condition_allowed"),
            type_="check",
        )
        batch_op.alter_column(
            "source_listing_id",
            new_column_name="external_listing_id",
            existing_type=sa.String(length=255),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "raw_brand",
            new_column_name="brand_name",
            existing_type=sa.String(length=255),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "raw_model",
            new_column_name="model_name",
            existing_type=sa.String(length=255),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "raw_variant_name",
            new_column_name="variant_name",
            existing_type=sa.String(length=255),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "condition",
            new_column_name="vehicle_condition",
            existing_type=sa.String(length=50),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "dealer_name",
            new_column_name="seller_name",
            existing_type=sa.String(length=255),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "city",
            new_column_name="seller_city",
            existing_type=sa.String(length=120),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "postal_code",
            new_column_name="seller_postcode",
            existing_type=sa.String(length=20),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "source_url",
            new_column_name="listing_url",
            existing_type=sa.String(length=1000),
            existing_nullable=True,
        )
        batch_op.add_column(sa.Column("title", sa.String(length=500), nullable=True))
        batch_op.add_column(
            sa.Column(
                "current_price_amount",
                sa.Numeric(precision=14, scale=2),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "currency",
                sa.String(length=3),
                nullable=False,
                server_default="EUR",
            )
        )
        batch_op.add_column(sa.Column("registration_year", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("fuel_type", sa.String(length=50), nullable=True))
        batch_op.add_column(
            sa.Column("transmission", sa.String(length=50), nullable=True)
        )
        batch_op.add_column(
            sa.Column("power_kw", sa.Numeric(precision=8, scale=2), nullable=True)
        )
        batch_op.add_column(sa.Column("body_type", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("color", sa.String(length=100), nullable=True))
        batch_op.add_column(
            sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_check_constraint(
            "current_price_amount_non_negative",
            "current_price_amount IS NULL OR current_price_amount >= 0",
        )
        batch_op.create_check_constraint("currency_length", "length(currency) = 3")
        batch_op.create_check_constraint(
            "power_kw_non_negative",
            "power_kw IS NULL OR power_kw >= 0",
        )
        batch_op.create_check_constraint(
            "registration_year_valid",
            "registration_year IS NULL OR registration_year >= 1886",
        )
        batch_op.create_check_constraint(
            "collection_window_valid",
            "last_collected_at IS NULL OR first_seen_at IS NULL "
            "OR last_collected_at >= first_seen_at",
        )
        batch_op.create_check_constraint(
            "vehicle_condition_allowed",
            "vehicle_condition IS NULL OR vehicle_condition IN "
            "('new', 'used', 'demonstrator', 'unknown')",
        )

    op.create_index(
        "ix_marketplace_listings_source_listing",
        LISTINGS_TABLE,
        ["data_source_id", "external_listing_id"],
        unique=True,
    )
    op.create_index(
        "ix_marketplace_listings_seller_city",
        LISTINGS_TABLE,
        ["seller_city"],
        unique=False,
    )
    op.create_index(
        "ix_marketplace_listings_seller_postcode",
        LISTINGS_TABLE,
        ["seller_postcode"],
        unique=False,
    )
    op.create_index(
        "ix_marketplace_listings_current_price",
        LISTINGS_TABLE,
        ["current_price_amount"],
        unique=False,
    )
    op.create_index(
        "ix_marketplace_listings_last_collected",
        LISTINGS_TABLE,
        ["last_collected_at"],
        unique=False,
    )

    op.create_table(
        "marketplace_price_history",
        sa.Column("marketplace_price_history_id", sa.Integer(), nullable=False),
        sa.Column("marketplace_listing_id", sa.Integer(), nullable=False),
        sa.Column(
            "price_amount",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
        ),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="EUR",
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("listing_url", sa.String(length=1000), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(currency) = 3",
            name=op.f("ck_marketplace_price_history_currency_length"),
        ),
        sa.CheckConstraint(
            "price_amount >= 0",
            name=op.f("ck_marketplace_price_history_price_amount_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["marketplace_listing_id"],
            ["marketplace_listings.marketplace_listing_id"],
            name=op.f(
                "fk_marketplace_price_history_marketplace_listing_id_"
                "marketplace_listings"
            ),
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "marketplace_price_history_id",
            name=op.f("pk_marketplace_price_history"),
        ),
        sa.UniqueConstraint(
            "marketplace_listing_id",
            "observed_at",
            name=op.f("uq_marketplace_price_history_marketplace_listing_id"),
        ),
    )
    op.create_index(
        "ix_marketplace_price_history_listing_observed",
        "marketplace_price_history",
        ["marketplace_listing_id", "observed_at"],
        unique=True,
    )
    op.create_index(
        "ix_marketplace_price_history_price",
        "marketplace_price_history",
        ["price_amount"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_marketplace_price_history_price",
        table_name="marketplace_price_history",
    )
    op.drop_index(
        "ix_marketplace_price_history_listing_observed",
        table_name="marketplace_price_history",
    )
    op.drop_table("marketplace_price_history")

    with op.batch_alter_table(
        LISTINGS_TABLE,
        copy_from=_marketplace_listings_table_after(),
    ) as batch_op:
        batch_op.drop_index("ix_marketplace_listings_last_collected")
        batch_op.drop_index("ix_marketplace_listings_current_price")
        batch_op.drop_index("ix_marketplace_listings_seller_postcode")
        batch_op.drop_index("ix_marketplace_listings_seller_city")
        batch_op.drop_index("ix_marketplace_listings_source_listing")
        batch_op.drop_constraint(
            op.f("ck_marketplace_listings_vehicle_condition_allowed"),
            type_="check",
        )
        batch_op.drop_constraint(
            op.f("ck_marketplace_listings_collection_window_valid"),
            type_="check",
        )
        batch_op.drop_constraint(
            op.f("ck_marketplace_listings_registration_year_valid"),
            type_="check",
        )
        batch_op.drop_constraint(
            op.f("ck_marketplace_listings_power_kw_non_negative"),
            type_="check",
        )
        batch_op.drop_constraint(
            op.f("ck_marketplace_listings_currency_length"),
            type_="check",
        )
        batch_op.drop_constraint(
            op.f("ck_marketplace_listings_current_price_amount_non_negative"),
            type_="check",
        )
        batch_op.drop_column("source_updated_at")
        batch_op.drop_column("last_collected_at")
        batch_op.drop_column("color")
        batch_op.drop_column("body_type")
        batch_op.drop_column("power_kw")
        batch_op.drop_column("transmission")
        batch_op.drop_column("fuel_type")
        batch_op.drop_column("registration_year")
        batch_op.drop_column("currency")
        batch_op.drop_column("current_price_amount")
        batch_op.drop_column("title")
        batch_op.alter_column(
            "listing_url",
            new_column_name="source_url",
            existing_type=sa.String(length=1000),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "seller_postcode",
            new_column_name="postal_code",
            existing_type=sa.String(length=20),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "seller_city",
            new_column_name="city",
            existing_type=sa.String(length=120),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "seller_name",
            new_column_name="dealer_name",
            existing_type=sa.String(length=255),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "vehicle_condition",
            new_column_name="condition",
            existing_type=sa.String(length=50),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "variant_name",
            new_column_name="raw_variant_name",
            existing_type=sa.String(length=255),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "model_name",
            new_column_name="raw_model",
            existing_type=sa.String(length=255),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "brand_name",
            new_column_name="raw_brand",
            existing_type=sa.String(length=255),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "external_listing_id",
            new_column_name="source_listing_id",
            existing_type=sa.String(length=255),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            "condition_allowed",
            "condition IS NULL OR condition IN "
            "('new', 'used', 'demonstrator', 'unknown')",
        )

    op.create_index(
        "ix_marketplace_listings_source_listing",
        LISTINGS_TABLE,
        ["data_source_id", "source_listing_id"],
        unique=True,
    )
    op.create_index(
        "ix_marketplace_listings_city",
        LISTINGS_TABLE,
        ["city"],
        unique=False,
    )
    op.create_index(
        "ix_marketplace_listings_postal_code",
        LISTINGS_TABLE,
        ["postal_code"],
        unique=False,
    )


def _marketplace_listings_table_before() -> sa.Table:
    metadata = sa.MetaData()
    table = sa.Table(
        LISTINGS_TABLE,
        metadata,
        sa.Column("marketplace_listing_id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("source_listing_id", sa.String(length=255), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), nullable=True),
        sa.Column("vehicle_variant_id", sa.Integer(), nullable=True),
        sa.Column("raw_brand", sa.String(length=255), nullable=True),
        sa.Column("raw_model", sa.String(length=255), nullable=True),
        sa.Column("raw_variant_name", sa.String(length=255), nullable=True),
        sa.Column("model_year", sa.String(length=20), nullable=True),
        sa.Column("first_registration_date", sa.Date(), nullable=True),
        sa.Column("condition", sa.String(length=50), nullable=True),
        sa.Column("mileage_km", sa.Integer(), nullable=True),
        sa.Column("owner_count", sa.Integer(), nullable=True),
        sa.Column("seller_type", sa.String(length=50), nullable=True),
        sa.Column("dealer_name", sa.String(length=255), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "condition IS NULL OR condition IN "
            "('new', 'used', 'demonstrator', 'unknown')",
            name="ck_marketplace_listings_condition_allowed",
        ),
        sa.CheckConstraint(
            "seller_type IS NULL OR seller_type IN "
            "('manufacturer', 'dealer', 'private', 'marketplace', 'unknown')",
            name="ck_marketplace_listings_seller_type_allowed",
        ),
        sa.CheckConstraint(
            "active IN (0, 1)",
            name="ck_marketplace_listings_active_boolean",
        ),
        sa.CheckConstraint(
            "country_code IS NULL OR length(country_code) = 2",
            name="ck_marketplace_listings_country_code_length",
        ),
        sa.CheckConstraint(
            "last_seen_at IS NULL OR first_seen_at IS NULL "
            "OR last_seen_at >= first_seen_at",
            name="ck_marketplace_listings_seen_window_valid",
        ),
        sa.CheckConstraint(
            "mileage_km IS NULL OR mileage_km >= 0",
            name="ck_marketplace_listings_mileage_km_non_negative",
        ),
        sa.CheckConstraint(
            "owner_count IS NULL OR owner_count >= 0",
            name="ck_marketplace_listings_owner_count_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["data_sources.data_source_id"],
            name="fk_marketplace_listings_data_source_id_data_sources",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.vehicle_id"],
            name="fk_marketplace_listings_vehicle_id_vehicles",
            onupdate="CASCADE",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_variant_id"],
            ["vehicle_variants.vehicle_variant_id"],
            name="fk_marketplace_listings_vehicle_variant_id_vehicle_variants",
            onupdate="CASCADE",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "marketplace_listing_id",
            name="pk_marketplace_listings",
        ),
        sa.UniqueConstraint(
            "data_source_id",
            "source_listing_id",
            name=OLD_LISTINGS_UNIQUE,
        ),
    )
    _marketplace_listing_indexes_before(table)
    return table


def _marketplace_listings_table_after() -> sa.Table:
    metadata = sa.MetaData()
    table = sa.Table(
        LISTINGS_TABLE,
        metadata,
        sa.Column("marketplace_listing_id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("external_listing_id", sa.String(length=255), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), nullable=True),
        sa.Column("vehicle_variant_id", sa.Integer(), nullable=True),
        sa.Column("brand_name", sa.String(length=255), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("variant_name", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column(
            "current_price_amount",
            sa.Numeric(precision=14, scale=2),
            nullable=True,
        ),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("registration_year", sa.Integer(), nullable=True),
        sa.Column("model_year", sa.String(length=20), nullable=True),
        sa.Column("first_registration_date", sa.Date(), nullable=True),
        sa.Column("fuel_type", sa.String(length=50), nullable=True),
        sa.Column("transmission", sa.String(length=50), nullable=True),
        sa.Column("power_kw", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("vehicle_condition", sa.String(length=50), nullable=True),
        sa.Column("body_type", sa.String(length=50), nullable=True),
        sa.Column("color", sa.String(length=100), nullable=True),
        sa.Column("mileage_km", sa.Integer(), nullable=True),
        sa.Column("owner_count", sa.Integer(), nullable=True),
        sa.Column("seller_type", sa.String(length=50), nullable=True),
        sa.Column("seller_name", sa.String(length=255), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("seller_city", sa.String(length=120), nullable=True),
        sa.Column("seller_postcode", sa.String(length=20), nullable=True),
        sa.Column("listing_url", sa.String(length=1000), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "current_price_amount IS NULL OR current_price_amount >= 0",
            name="ck_marketplace_listings_current_price_amount_non_negative",
        ),
        sa.CheckConstraint(
            "length(currency) = 3",
            name="ck_marketplace_listings_currency_length",
        ),
        sa.CheckConstraint(
            "mileage_km IS NULL OR mileage_km >= 0",
            name="ck_marketplace_listings_mileage_km_non_negative",
        ),
        sa.CheckConstraint(
            "owner_count IS NULL OR owner_count >= 0",
            name="ck_marketplace_listings_owner_count_non_negative",
        ),
        sa.CheckConstraint(
            "power_kw IS NULL OR power_kw >= 0",
            name="ck_marketplace_listings_power_kw_non_negative",
        ),
        sa.CheckConstraint(
            "registration_year IS NULL OR registration_year >= 1886",
            name="ck_marketplace_listings_registration_year_valid",
        ),
        sa.CheckConstraint(
            "last_seen_at IS NULL OR first_seen_at IS NULL "
            "OR last_seen_at >= first_seen_at",
            name="ck_marketplace_listings_seen_window_valid",
        ),
        sa.CheckConstraint(
            "last_collected_at IS NULL OR first_seen_at IS NULL "
            "OR last_collected_at >= first_seen_at",
            name="ck_marketplace_listings_collection_window_valid",
        ),
        sa.CheckConstraint(
            "vehicle_condition IS NULL OR vehicle_condition IN "
            "('new', 'used', 'demonstrator', 'unknown')",
            name="ck_marketplace_listings_vehicle_condition_allowed",
        ),
        sa.CheckConstraint(
            "seller_type IS NULL OR seller_type IN "
            "('manufacturer', 'dealer', 'private', 'marketplace', 'unknown')",
            name="ck_marketplace_listings_seller_type_allowed",
        ),
        sa.CheckConstraint(
            "country_code IS NULL OR length(country_code) = 2",
            name="ck_marketplace_listings_country_code_length",
        ),
        sa.CheckConstraint(
            "active IN (0, 1)",
            name="ck_marketplace_listings_active_boolean",
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["data_sources.data_source_id"],
            name="fk_marketplace_listings_data_source_id_data_sources",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.vehicle_id"],
            name="fk_marketplace_listings_vehicle_id_vehicles",
            onupdate="CASCADE",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_variant_id"],
            ["vehicle_variants.vehicle_variant_id"],
            name="fk_marketplace_listings_vehicle_variant_id_vehicle_variants",
            onupdate="CASCADE",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "marketplace_listing_id",
            name="pk_marketplace_listings",
        ),
    )
    _marketplace_listing_indexes_after(table)
    return table


def _marketplace_listing_indexes_before(table: sa.Table) -> None:
    sa.Index(
        "ix_marketplace_listings_source_listing",
        table.c.data_source_id,
        table.c.source_listing_id,
        unique=True,
    )
    sa.Index(
        "ix_marketplace_listings_vehicle_active",
        table.c.vehicle_id,
        table.c.active,
    )
    sa.Index(
        "ix_marketplace_listings_variant_active",
        table.c.vehicle_variant_id,
        table.c.active,
    )
    sa.Index("ix_marketplace_listings_city", table.c.city)
    sa.Index("ix_marketplace_listings_postal_code", table.c.postal_code)


def _marketplace_listing_indexes_after(table: sa.Table) -> None:
    sa.Index(
        "ix_marketplace_listings_source_listing",
        table.c.data_source_id,
        table.c.external_listing_id,
        unique=True,
    )
    sa.Index(
        "ix_marketplace_listings_vehicle_active",
        table.c.vehicle_id,
        table.c.active,
    )
    sa.Index(
        "ix_marketplace_listings_variant_active",
        table.c.vehicle_variant_id,
        table.c.active,
    )
    sa.Index("ix_marketplace_listings_seller_city", table.c.seller_city)
    sa.Index("ix_marketplace_listings_seller_postcode", table.c.seller_postcode)
    sa.Index(
        "ix_marketplace_listings_current_price",
        table.c.current_price_amount,
    )
    sa.Index(
        "ix_marketplace_listings_last_collected",
        table.c.last_collected_at,
    )
