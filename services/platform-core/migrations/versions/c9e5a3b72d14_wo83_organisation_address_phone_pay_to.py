"""WO-83 — a shop has an address, a phone and a "Pay to" line.

Revision ID: c9e5a3b72d14
Revises: b8d4f2a61c93

Three nullable columns on `organization`: `address`, `phone`, `pay_to`. Every
bill the shop sends is headed by them; nothing in the domain requires them,
so an organisation that has run for a year without saying is unchanged by
this landing. GSTIN/FSSAI deliberately not added (see the model).

Reversible: the downgrade drops the three columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "c9e5a3b72d14"
down_revision = "b8d4f2a61c93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organization") as batch:
        batch.add_column(sa.Column("address", sa.Text(), nullable=True))
        batch.add_column(sa.Column("phone", sa.String(length=30), nullable=True))
        batch.add_column(sa.Column("pay_to", sa.String(length=300), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("organization") as batch:
        batch.drop_column("pay_to")
        batch.drop_column("phone")
        batch.drop_column("address")
