"""WO-89 — a rate that varies by the day, and by the household.

Revision ID: b8d4f2a61c93
Revises: a7c3e9d14b56

`milk_delivery` gains the provenance of its price — `price_source`
(`plan` | `override`), `priced_by`, `override_reason` — and
`customer_invoice_line` copies `price_source` with the rate it already
copied, so a bill can say which day was different. Every existing row is
`plan`: until now nothing could write anything but the plan's rate into
`unit_price`, so that is the truth about every row that exists.

Additive and reversible: the downgrade drops the four columns. No business
value moves; `unit_price` and `amount` are untouched.
"""

import sqlalchemy as sa
from alembic import op

revision = "b8d4f2a61c93"
down_revision = "a7c3e9d14b56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("milk_delivery") as batch:
        batch.add_column(
            sa.Column("price_source", sa.String(length=10), nullable=False, server_default="plan")
        )
        batch.add_column(sa.Column("priced_by", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("override_reason", sa.String(length=300), nullable=True))
    with op.batch_alter_table("customer_invoice_line") as batch:
        batch.add_column(
            sa.Column("price_source", sa.String(length=10), nullable=False, server_default="plan")
        )


def downgrade() -> None:
    with op.batch_alter_table("customer_invoice_line") as batch:
        batch.drop_column("price_source")
    with op.batch_alter_table("milk_delivery") as batch:
        batch.drop_column("override_reason")
        batch.drop_column("priced_by")
        batch.drop_column("price_source")
