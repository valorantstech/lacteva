"""DEMO-029 delivery receipts

One nullable column on `notification` and one new tenant-owned table.

**A migration IS necessary**, and this says so explicitly because the work
order asks. `delivered_at` has nowhere to live otherwise, and the replay
defence for provider callbacks is a UNIQUE CONSTRAINT — which is a table, not a
convention.

**No financial record is read or written.** A delivery receipt is a
communication event: it says a message arrived, and it must never touch a
collection, a settlement, an invoice, a payment, a receipt or a balance. This
migration touches `notification` and one new table beside it.

**No data migration, and no backfill.** Every existing notification gets
`delivered_at = NULL`, which is the honest value: nothing recorded before this
migration was ever confirmed delivered by anybody, and `status` stays exactly
what it was. In particular no `sent` row becomes `delivered` — turning provider
acceptance into delivery is the one thing DEMO-028 was written to stop.

`(provider, event_id)` on `notification_receipt_event` is unique, and that is
the replay defence: a gateway redelivering a report it is unsure landed is
normal operation, and the second delivery must do nothing at all.

The table carries `tenant_id`, so `core/rls.py` derives it into the protected
set from the model metadata and the policy below is installed by the same
machinery every other tenant table uses.

The downgrade drops both. It loses the record of which reports were received;
it loses no money, because none is recorded here.
"""

import sqlalchemy as sa
from alembic import op

revision = "f3a9c71d5e28"
down_revision = "e8b2a4c60d17"
branch_labels = None
depends_on = None

#: Snapshotted, not derived — a migration records what it did on the day it ran.
POLICY_TABLES = ("notification_receipt_event",)


def upgrade() -> None:
    op.add_column(
        "notification", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_table(
        "notification_receipt_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("event_id", sa.String(length=160), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "event_id", name="uq_notification_receipt_event"),
    )
    op.create_index(
        "ix_notification_receipt_event_tenant_id", "notification_receipt_event", ["tenant_id"]
    )
    op.create_index(
        "ix_notification_receipt_notification", "notification_receipt_event", ["notification_id"]
    )

    # RLS, on PostgreSQL only. SQLite has no such thing, and the test stack
    # relies on the application filters that are defence-in-depth in
    # production and the whole story in tests.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from platform_core.core.rls import policy_statements

        for table in POLICY_TABLES:
            for statement in policy_statements(table):
                op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from platform_core.core.rls import drop_statements

        for table in POLICY_TABLES:
            for statement in drop_statements(table):
                op.execute(statement)

    op.drop_index(
        "ix_notification_receipt_notification", table_name="notification_receipt_event"
    )
    op.drop_index(
        "ix_notification_receipt_event_tenant_id", table_name="notification_receipt_event"
    )
    op.drop_table("notification_receipt_event")
    op.drop_column("notification", "delivered_at")
