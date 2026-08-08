"""PROD-001 receipt printable fields

Adds the facts a PRINTABLE receipt needs and the record did not carry: the
issuing dairy's name, the collection center's name, and what the money was for
(quantity and the average rate achieved over the settlement period).

All of them are COPIED at generation like every other receipt field (BR-0020) —
a receipt must show the world as it was when the money moved, so a dairy or
center that later renames itself must not retroactively rewrite receipts
farmers already hold.

**Expand-only, and deliberately so.** The three text columns are NOT NULL with
a server default of '' rather than nullable: autogenerate produced them as bare
NOT NULL, which fails outright on a table that already has rows, and this
platform's rollback matrix (DEPLOYMENT.md) only permits expand-only migrations
to roll back freely. The numeric columns are nullable because "unknown" is a
real state for them — a settlement built purely from adjustments has no
quantity and therefore no rate, and 0 would be a lie rather than a gap.

Receipts generated BEFORE this migration keep empty strings and NULLs; they
render without those rows rather than inventing them, because backfilling them
would mean re-deriving a frozen artifact from a world that has since changed.

Revision ID: dd68ec06c1c0
Revises: ced805436869
Create Date: 2026-08-08 12:32:27.686799
"""

import sqlalchemy as sa
from alembic import op

revision = "dd68ec06c1c0"
down_revision = "ced805436869"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "receipt",
        sa.Column("organization_name", sa.String(length=200), nullable=False, server_default=""),
    )
    op.add_column(
        "receipt_line",
        sa.Column("center_name", sa.String(length=200), nullable=False, server_default=""),
    )
    op.add_column(
        "receipt_line",
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=True),
    )
    op.add_column(
        "receipt_line",
        sa.Column("quantity_unit", sa.String(length=20), nullable=False, server_default=""),
    )
    op.add_column(
        "receipt_line",
        sa.Column("average_rate", sa.Numeric(precision=12, scale=4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("receipt_line", "average_rate")
    op.drop_column("receipt_line", "quantity_unit")
    op.drop_column("receipt_line", "quantity")
    op.drop_column("receipt_line", "center_name")
    op.drop_column("receipt", "organization_name")
