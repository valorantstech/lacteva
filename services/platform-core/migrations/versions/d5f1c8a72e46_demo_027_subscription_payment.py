"""DEMO-027 subscription payment, webhook ledger and grace period

Two new tenant-owned tables and one nullable column on `subscription`.

**No dairy financial record is touched.** Nothing here reads or writes
`milk_collection_transaction`, `settlement`, `payment`, `customer_invoice`,
`customer_receipt` or any balance. Lacteva charging its tenants and a dairy
paying its farmers share a word and nothing else, and the separation is
physical: `subscription_payment` is a different table in a different module
from `payment`, which is PAY-001's operational engine.

**No data migration.** Existing subscriptions keep their plan, their status and
their dates exactly as they are. `grace_ends_on` arrives NULL, which is what it
means for every subscription that has never had a renewal fail.

`(tenant_id, open_key)` is unique and `open_key` is nullable: NULL does not
collide with NULL in PostgreSQL or SQLite, so one OPEN payment per organization
is enforced by the database while any number of settled ones coexist. That
constraint — not a `SELECT` — is what stops a double-clicked checkout becoming
two charges.

`(provider, event_id)` is unique, and that is the replay defence. A gateway
redelivering an event it is unsure landed is normal operation; the second
delivery must do nothing at all.

Both tables carry `tenant_id`, so `core/rls.py` derives them into the protected
set from the model metadata and the policies below are installed by the same
machinery every other tenant table uses.

The downgrade drops both tables and the column. It loses the record of which
payments were attempted; it loses no dairy money, because none is recorded
here.
"""

import sqlalchemy as sa
from alembic import op

revision = "d5f1c8a72e46"
down_revision = "c7e4a2f19b83"
branch_labels = None
depends_on = None

#: Snapshotted, not derived — a migration records what it did on the day it ran.
POLICY_TABLES = ("subscription_payment", "subscription_payment_event")


def upgrade() -> None:
    op.add_column("subscription", sa.Column("grace_ends_on", sa.Date(), nullable=True))

    op.create_table(
        "subscription_payment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("plan_code", sa.String(length=40), nullable=False),
        # NUMERIC(18, 6) to match the platform's money policy (BR-0005). The
        # scale a currency actually uses is applied by `quantize_money`; the
        # column is wide enough not to be the thing that rounds.
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("open_key", sa.String(length=8), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_reference", sa.String(length=160), nullable=True),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("failure_code", sa.String(length=60), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "open_key", name="uq_subscription_payment_open"),
        sa.UniqueConstraint(
            "provider", "provider_reference", name="uq_subscription_payment_provider_ref"
        ),
    )
    op.create_index("ix_subscription_payment_tenant_id", "subscription_payment", ["tenant_id"])
    op.create_index(
        "ix_subscription_payment_subscription_id", "subscription_payment", ["subscription_id"]
    )
    op.create_index("ix_subscription_payment_status", "subscription_payment", ["status"])
    op.create_index(
        "ix_subscription_payment_tenant_created",
        "subscription_payment",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "subscription_payment_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("event_id", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "event_id", name="uq_subscription_payment_event"),
    )
    op.create_index(
        "ix_subscription_payment_event_tenant_id", "subscription_payment_event", ["tenant_id"]
    )
    op.create_index(
        "ix_subscription_payment_event_payment", "subscription_payment_event", ["payment_id"]
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

    op.drop_index("ix_subscription_payment_event_payment", table_name="subscription_payment_event")
    op.drop_index(
        "ix_subscription_payment_event_tenant_id", table_name="subscription_payment_event"
    )
    op.drop_table("subscription_payment_event")

    op.drop_index("ix_subscription_payment_tenant_created", table_name="subscription_payment")
    op.drop_index("ix_subscription_payment_status", table_name="subscription_payment")
    op.drop_index("ix_subscription_payment_subscription_id", table_name="subscription_payment")
    op.drop_index("ix_subscription_payment_tenant_id", table_name="subscription_payment")
    op.drop_table("subscription_payment")

    op.drop_column("subscription", "grace_ends_on")
