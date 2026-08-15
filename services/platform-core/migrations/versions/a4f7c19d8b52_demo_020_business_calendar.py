"""DEMO-020 organization calendar and financial periods

Two new tenant-owned tables and nothing else. No column is added to, and no
row touched in, any existing table — so no collection, settlement, payment,
receipt, invoice or balance can be altered by running or reverting this.

**Both tables carry `tenant_id`**, so `core/rls.py` derives them into the
protected set from the model metadata and the policies below are installed by
the same machinery every other tenant table uses. `POLICY_TABLES` is
snapshotted rather than derived, for the reason DEMO-017 states: a migration is
a historical record of what it did, and it must not change meaning when the
models later do.

**The tables start empty and that is what makes this safe to deploy into a
running platform.** `is_working_day` treats an absent row as a working day —
exactly the platform's behaviour before the table existed — and the financial
period guard permits any date not covered by a CLOSED period. With no rows,
every guard passes and nothing an operator does today behaves differently
tomorrow. The capability only begins to refuse once somebody deliberately
declares a holiday or closes a month.

The downgrade drops both tables. A rollback therefore loses the declared
holidays and the record of which periods were closed, and loses no money.
"""

import sqlalchemy as sa
from alembic import op

revision = "a4f7c19d8b52"
down_revision = "e93b5d1c72af"
branch_labels = None
depends_on = None

#: Snapshotted, not derived. See the module docstring.
POLICY_TABLES = ("organization_calendar_day", "financial_period")


def upgrade() -> None:
    op.create_table(
        "organization_calendar_day",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("working", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="holiday"),
        sa.Column("name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("tenant_id", "day", name="uq_org_calendar_tenant_day"),
    )
    op.create_index(
        "ix_organization_calendar_day_tenant_id", "organization_calendar_day", ["tenant_id"]
    )
    op.create_index("ix_organization_calendar_day_day", "organization_calendar_day", ["day"])

    op.create_table(
        "financial_period",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("label", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("tenant_id", "period_start", name="uq_financial_period_start"),
    )
    op.create_index("ix_financial_period_tenant_id", "financial_period", ["tenant_id"])
    op.create_index("ix_financial_period_period_start", "financial_period", ["period_start"])
    op.create_index("ix_financial_period_period_end", "financial_period", ["period_end"])
    op.create_index("ix_financial_period_status", "financial_period", ["status"])

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

    op.drop_index("ix_financial_period_status", table_name="financial_period")
    op.drop_index("ix_financial_period_period_end", table_name="financial_period")
    op.drop_index("ix_financial_period_period_start", table_name="financial_period")
    op.drop_index("ix_financial_period_tenant_id", table_name="financial_period")
    op.drop_table("financial_period")

    op.drop_index("ix_organization_calendar_day_day", table_name="organization_calendar_day")
    op.drop_index("ix_organization_calendar_day_tenant_id", table_name="organization_calendar_day")
    op.drop_table("organization_calendar_day")
