"""extend registration observations for KBA fuel records

Revision ID: 8f4c2d9a1b6e
Revises: 26591d9c4240
Create Date: 2026-07-18 15:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8f4c2d9a1b6e"
down_revision: str | Sequence[str] | None = "26591d9c4240"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "registration_observations"
OLD_UNIQUE = "uq_registration_observations_data_source_id"
NEW_UNIQUE = "uq_registration_observations_kba_idempotency"
BRAND_FK = "fk_registration_observations_brand_id_brands"


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table(
        TABLE_NAME,
        copy_from=_registration_observations_table(include_kba_columns=False),
    ) as batch_op:
        batch_op.drop_constraint(OLD_UNIQUE, type_="unique")
        batch_op.add_column(sa.Column("brand_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("fuel_type", sa.String(length=50), nullable=True))
        batch_op.add_column(
            sa.Column("market_share", sa.Numeric(precision=8, scale=4), nullable=True)
        )
        batch_op.create_foreign_key(
            BRAND_FK,
            "brands",
            ["brand_id"],
            ["brand_id"],
            onupdate="CASCADE",
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            NEW_UNIQUE,
            [
                "data_source_id",
                "brand_id",
                "vehicle_id",
                "registration_period",
                "fuel_type",
            ],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table(
        TABLE_NAME,
        copy_from=_registration_observations_table(include_kba_columns=True),
    ) as batch_op:
        batch_op.drop_constraint(NEW_UNIQUE, type_="unique")
        batch_op.drop_constraint(BRAND_FK, type_="foreignkey")
        batch_op.drop_column("market_share")
        batch_op.drop_column("fuel_type")
        batch_op.drop_column("brand_id")
        batch_op.create_unique_constraint(
            OLD_UNIQUE,
            [
                "data_source_id",
                "vehicle_id",
                "registration_period",
                "registration_scope",
                "sales_metric_type",
            ],
        )


def _registration_observations_table(*, include_kba_columns: bool) -> sa.Table:
    metadata = sa.MetaData()
    columns: list[sa.Column | sa.Constraint] = [
        sa.Column("registration_observation_id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
    ]
    if include_kba_columns:
        columns.append(sa.Column("brand_id", sa.Integer(), nullable=True))

    columns.extend(
        [
            sa.Column("vehicle_id", sa.Integer(), nullable=True),
            sa.Column("vehicle_variant_id", sa.Integer(), nullable=True),
            sa.Column("canonical_brand", sa.String(length=100), nullable=True),
            sa.Column("canonical_model", sa.String(length=100), nullable=True),
            sa.Column("raw_brand", sa.String(length=255), nullable=True),
            sa.Column("raw_model", sa.String(length=255), nullable=True),
            sa.Column("registration_count", sa.Integer(), nullable=True),
        ]
    )
    if include_kba_columns:
        columns.extend(
            [
                sa.Column("fuel_type", sa.String(length=50), nullable=True),
                sa.Column(
                    "market_share",
                    sa.Numeric(precision=8, scale=4),
                    nullable=True,
                ),
            ]
        )

    columns.extend(
        [
            sa.Column("sales_value", sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column("sales_metric_type", sa.String(length=50), nullable=False),
            sa.Column("registration_period", sa.String(length=20), nullable=False),
            sa.Column("registration_scope", sa.String(length=100), nullable=False),
            sa.Column("region", sa.String(length=100), nullable=True),
            sa.Column("country_code", sa.String(length=2), nullable=True),
            sa.Column("state", sa.String(length=100), nullable=True),
            sa.Column("valid_date", sa.Date(), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source_url", sa.String(length=1000), nullable=True),
            sa.Column("source_record_id", sa.String(length=255), nullable=True),
            sa.Column("source_file_name", sa.String(length=500), nullable=True),
            sa.Column("source_page_number", sa.Integer(), nullable=True),
            sa.Column("data_quality_status", sa.String(length=50), nullable=True),
            sa.Column("validation_status", sa.String(length=50), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "data_quality_status IS NULL OR data_quality_status IN ("
                "'valid', 'warning', 'invalid', 'unknown')",
                name="ck_registration_observations_data_quality_status_allowed",
            ),
            sa.CheckConstraint(
                "sales_metric_type IN ("
                "'new_registration', 'retail_sales', 'wholesale_sales', "
                "'delivery', 'unknown')",
                name="ck_registration_observations_sales_metric_type_allowed",
            ),
            sa.CheckConstraint(
                "validation_status IS NULL OR validation_status IN ("
                "'pending', 'passed', 'failed')",
                name="ck_registration_observations_validation_status_allowed",
            ),
            sa.CheckConstraint(
                "country_code IS NULL OR length(country_code) = 2",
                name="ck_registration_observations_country_code_length",
            ),
            sa.CheckConstraint(
                "registration_count IS NULL OR registration_count >= 0",
                name="ck_registration_observations_registration_count_non_negative",
            ),
            sa.CheckConstraint(
                "sales_value IS NULL OR sales_value >= 0",
                name="ck_registration_observations_sales_value_non_negative",
            ),
            sa.CheckConstraint(
                "source_page_number IS NULL OR source_page_number > 0",
                name="ck_registration_observations_source_page_number_positive",
            ),
            sa.ForeignKeyConstraint(
                ["data_source_id"],
                ["data_sources.data_source_id"],
                name="fk_registration_observations_data_source_id_data_sources",
                onupdate="CASCADE",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["vehicle_id"],
                ["vehicles.vehicle_id"],
                name="fk_registration_observations_vehicle_id_vehicles",
                onupdate="CASCADE",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["vehicle_variant_id"],
                ["vehicle_variants.vehicle_variant_id"],
                name=(
                    "fk_registration_observations_vehicle_variant_id_"
                    "vehicle_variants"
                ),
                onupdate="CASCADE",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint(
                "registration_observation_id",
                name="pk_registration_observations",
            ),
        ]
    )
    if include_kba_columns:
        columns.extend(
            [
                sa.ForeignKeyConstraint(
                    ["brand_id"],
                    ["brands.brand_id"],
                    name=BRAND_FK,
                    onupdate="CASCADE",
                    ondelete="SET NULL",
                ),
                sa.UniqueConstraint(
                    "data_source_id",
                    "brand_id",
                    "vehicle_id",
                    "registration_period",
                    "fuel_type",
                    name=NEW_UNIQUE,
                ),
            ]
        )
    else:
        columns.append(
            sa.UniqueConstraint(
                "data_source_id",
                "vehicle_id",
                "registration_period",
                "registration_scope",
                "sales_metric_type",
                name=OLD_UNIQUE,
            )
        )

    table = sa.Table(TABLE_NAME, metadata, *columns)
    sa.Index(
        "ix_registration_observations_scope_metric_period",
        table.c.registration_scope,
        table.c.sales_metric_type,
        table.c.registration_period,
    )
    sa.Index(
        "ix_registration_observations_vehicle_period",
        table.c.vehicle_id,
        table.c.registration_period,
    )
    return table
