"""WO-108 — how a round goes out: by vehicle, on foot, or by bicycle.

Revision ID: f1a2b3c4d5e6
Revises: e5b7c2a91d04

`route.transport`, defaulting to `vehicle` so every existing round keeps
BR-0028 exactly as it was (a driver AND a vehicle before a run may start).
A shop's delivery boy walks or rides a bicycle; the round says so, and the
rule asks for the driver alone. Reversible: the column is dropped.
"""

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e5b7c2a91d04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("route") as batch:
        batch.add_column(
            sa.Column("transport", sa.String(12), nullable=False, server_default="vehicle")
        )


def downgrade() -> None:
    with op.batch_alter_table("route") as batch:
        batch.drop_column("transport")
