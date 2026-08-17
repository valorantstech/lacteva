"""P0-BIZ-003 collection slip number

One nullable column on `milk_collection_transaction` and the unique constraint
that makes it a document number rather than a note.

**A migration IS necessary**: the parchi needs a human-readable, sequential,
per-tenant number, and a number that can silently repeat is not a number. The
uniqueness is a constraint, not a convention.

**No financial record is read or written.** `unit_price`, `gross_amount` and
`currency` are untouched; the slip RENDERS them, it never recomputes them.

**No data migration, and no backfill.** Every transaction completed before
this migration gets `slip_number = NULL`, which is the honest value: no slip
was ever issued for them. The slip endpoint mints lazily on first read, so a
historical transaction gets its number the day somebody actually asks for its
slip — from the same per-tenant-year series as everything after it.

NULLs do not collide under a UNIQUE constraint on either engine, so the
constraint coexists with all pre-slip history and every in-flight transaction.

The counter itself needs no schema: `document_sequence` already carries seven
series (settlement, payment, receipt, invoice, customer payment, customer
receipt, customer), and `collection_slip` is simply the eighth row kind.

The downgrade drops the column and the constraint. It loses which number each
slip carried; it loses no money, because none is stored here.
"""

import sqlalchemy as sa
from alembic import op

revision = "c9e4b2a71f05"
down_revision = "b5d1e07a4c39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch_alter_table so the constraint also applies on SQLite, which cannot
    # ALTER TABLE ... ADD CONSTRAINT and needs the copy-and-rename dance.
    with op.batch_alter_table("milk_collection_transaction") as batch:
        batch.add_column(sa.Column("slip_number", sa.String(length=30), nullable=True))
        batch.create_unique_constraint("uq_milk_tx_slip", ["tenant_id", "slip_number"])


def downgrade() -> None:
    with op.batch_alter_table("milk_collection_transaction") as batch:
        batch.drop_constraint("uq_milk_tx_slip", type_="unique")
        batch.drop_column("slip_number")
