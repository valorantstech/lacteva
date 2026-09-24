"""WO-82 · LACTEVA-MOBILE-015 — a route can plan its own morning.

Revision ID: f4a9d2c71b83
Revises: e2f7c3b81a90

Three columns on `route`: `default_driver_id`, `default_vehicle_id` (both
nullable) and `auto_plan` (false for every existing route). With `auto_plan`
and a default driver, the daily scheduler creates the business day's run,
assigns the driver and generates its deliveries through the same three calls
the office uses. Nothing is planned for any route that exists when this
lands: the flag is off until the owner turns it on.

No data is read or rewritten. The downgrade drops the three columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "f4a9d2c71b83"
down_revision = "e2f7c3b81a90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("route") as batch:
        batch.add_column(sa.Column("default_driver_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("default_vehicle_id", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column("auto_plan", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("route") as batch:
        batch.drop_column("auto_plan")
        batch.drop_column("default_vehicle_id")
        batch.drop_column("default_driver_id")
