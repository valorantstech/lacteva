"""DEMO-017 delivery generation runs

One row per tenant per business date, recording what the scheduler did.

**The unique constraint on `(tenant_id, business_date)` is a second
idempotency guard, and a weaker one than it looks.** The guarantee that milk
cannot be delivered twice is `uq_delivery_customer_date_slot`, added in
DEMO-009 and used by DEMO-016's `INSERT … ON CONFLICT DO NOTHING`. This one
stops a loop that wakes every minute from re-running a finished round sixty
times an hour — it is for legibility and load, not for correctness. Both are
needed and it is worth being clear which does which.

The table is tenant-owned: it carries `tenant_id`, so `core/rls.py` derives it
into the protected set from the model metadata and the policy is installed by
the RLS machinery rather than by hand. That also means a tenant administrator
reads their own runs and nobody else's, through the ordinary policy.

Purely additive: a new table, no column added to and no row touched in any
existing one. The downgrade drops it, and drops nothing else — a rollback of
this milestone loses the record of what the scheduler did and no delivery,
invoice, payment or receipt.
"""

import sqlalchemy as sa
from alembic import op

revision = "e93b5d1c72af"
down_revision = "d71c4a9f6e28"
branch_labels = None
depends_on = None

#: Snapshotted, not derived. A migration is a historical record: this list is
#: what the RLS policy covered on the day it ran, and it must not change
#: meaning when the models later do (the rule `core/rls.py` states).
POLICY_TABLES = ("delivery_generation_run",)


def upgrade() -> None:
    op.create_table(
        "delivery_generation_run",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
        sa.Column("trigger", sa.String(length=16), nullable=False, server_default="scheduler"),
        sa.Column("plans_due", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("already_present", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("not_due", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inactive_customers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("tenant_id", "business_date", name="uq_generation_run_tenant_date"),
    )
    op.create_index(
        "ix_delivery_generation_run_tenant_id", "delivery_generation_run", ["tenant_id"]
    )
    op.create_index(
        "ix_delivery_generation_run_business_date", "delivery_generation_run", ["business_date"]
    )
    op.create_index("ix_delivery_generation_run_status", "delivery_generation_run", ["status"])

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
    op.drop_index("ix_delivery_generation_run_status", table_name="delivery_generation_run")
    op.drop_index("ix_delivery_generation_run_business_date", table_name="delivery_generation_run")
    op.drop_index("ix_delivery_generation_run_tenant_id", table_name="delivery_generation_run")
    op.drop_table("delivery_generation_run")
