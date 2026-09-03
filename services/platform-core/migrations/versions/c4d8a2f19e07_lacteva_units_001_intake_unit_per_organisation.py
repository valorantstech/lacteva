"""LACTEVA-UNITS-001 the intake unit belongs to the organisation

D-21 / WO-70. The platform hard-coded kilograms: `milk_collection/service.py`
refused any other unit and wrote the constant `"kg"` into a column that could
hold anything. In India milk is sold and quoted in LITRES. The unit becomes a
property of the organisation, resolved from its country like its currency,
with an owner-declared conversion factor for a dairy that measures in one unit
and trades in the other.

BACKFILL, AND WHY IT IS `kg` FOR EVERYONE — Indian organisations included.
Every row that exists was WEIGHED: the service allowed nothing else. The
organisation column defaults to `kg` so every existing tenant keeps measuring
what it measured, and every existing transaction keeps `weight_unit = 'kg'`.
Relabelling those rows as litres would turn real weights into volumes on paid
settlements — about 3% wrong, and silent. Moving a live organisation to
litres is a deliberate owner action in settings, and it applies to FUTURE
transactions only; `test_units.py` proves history does not move.

The transaction gains the three columns ruling 3 pins at capture: the paid
unit, the paid quantity and the factor that produced it. Null everywhere
today, because no organisation has declared a trade unit yet — a factor is a
commercial term somebody has to state, never a default.

Revision ID: c4d8a2f19e07
Revises: b7c41d29e5af
Create Date: 2026-09-03 22:40:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "c4d8a2f19e07"
down_revision = "b7c41d29e5af"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organization") as batch:
        batch.add_column(
            sa.Column("quantity_unit", sa.String(length=8), server_default="kg", nullable=False)
        )
        batch.add_column(sa.Column("trade_unit", sa.String(length=8), nullable=True))
        batch.add_column(
            sa.Column("conversion_factor", sa.Numeric(precision=8, scale=4), nullable=True)
        )
        batch.add_column(sa.Column("conversion_effective_from", sa.Date(), nullable=True))
    # Belt and braces: the server default fills the column on every dialect
    # that adds NOT NULL columns with a default, and this statement says the
    # intent in words a reader of the migration history can check.
    op.execute("UPDATE organization SET quantity_unit = 'kg' WHERE quantity_unit IS NULL")

    with op.batch_alter_table("milk_collection_transaction") as batch:
        batch.add_column(sa.Column("trade_unit", sa.String(length=8), nullable=True))
        batch.add_column(sa.Column("trade_quantity", sa.Float(), nullable=True))
        batch.add_column(
            sa.Column("conversion_factor", sa.Numeric(precision=8, scale=4), nullable=True)
        )
    # A weighed row without its unit written (none are expected — the service
    # always wrote the constant) is a kilogram row: that is what was measured.
    op.execute(
        "UPDATE milk_collection_transaction SET weight_unit = 'kg' "
        "WHERE weight_unit IS NULL AND net_weight IS NOT NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("milk_collection_transaction") as batch:
        batch.drop_column("conversion_factor")
        batch.drop_column("trade_quantity")
        batch.drop_column("trade_unit")
    with op.batch_alter_table("organization") as batch:
        batch.drop_column("conversion_effective_from")
        batch.drop_column("conversion_factor")
        batch.drop_column("trade_unit")
        batch.drop_column("quantity_unit")
