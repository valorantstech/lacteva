"""DEMO-026 subscription, trial and entitlement

One new tenant-owned table. No column is added to, and no row read or written
in, any existing table — so no collection, delivery, settlement, payment,
receipt, invoice or balance can be altered by running or reverting this.

**No data migration, deliberately.** Existing organizations are not given
subscription rows here. `SubscriptionService.ensure_trial` is get-or-create and
is called by every read, so an organization that predates this milestone
acquires its trial the first time anyone looks — counted from ITS OWN
`organization.created_at` on ITS OWN timezone, not from the day this shipped.
Backfilling in SQL would have had to pick a date without a clock, and would
have been wrong for every tenant that is not on UTC.

`tenant_id` is UNIQUE. That constraint is the duplicate prevention: a double
signup, a retried worker and two concurrent requests all arrive at the same
insert and the database decides which wins.

The table carries `tenant_id`, so `core/rls.py` derives it into the protected
set from the model metadata and the policy below is installed by the same
machinery every other tenant table uses.

The downgrade drops the table. A rollback loses which plan each organization
was on and when its trial started — and loses no money, because none is
recorded here.
"""

import sqlalchemy as sa
from alembic import op

revision = "c7e4a2f19b83"
down_revision = "b8d3e1470f92"
branch_labels = None
depends_on = None

#: Snapshotted, not derived — a migration records what it did on the day it ran.
POLICY_TABLES = ("subscription",)


def upgrade() -> None:
    op.create_table(
        "subscription",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "plan_code", sa.String(length=40), nullable=False, server_default="LACTEVA_TRIAL"
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="trialing"),
        sa.Column("trial_started_on", sa.Date(), nullable=True),
        sa.Column("trial_ends_on", sa.Date(), nullable=True),
        sa.Column("started_on", sa.Date(), nullable=True),
        sa.Column("current_period_end", sa.Date(), nullable=True),
        sa.Column("subscribed_centres", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payment_provider", sa.String(length=40), nullable=True),
        sa.Column("external_customer_id", sa.String(length=120), nullable=True),
        sa.Column("external_subscription_id", sa.String(length=120), nullable=True),
        sa.Column("external_price_id", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_subscription_tenant"),
    )
    op.create_index("ix_subscription_tenant_id", "subscription", ["tenant_id"])
    op.create_index("ix_subscription_status", "subscription", ["status"])

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

    op.drop_index("ix_subscription_status", table_name="subscription")
    op.drop_index("ix_subscription_tenant_id", table_name="subscription")
    op.drop_table("subscription")
