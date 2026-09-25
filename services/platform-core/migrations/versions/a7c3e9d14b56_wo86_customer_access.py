"""WO-86 — the customer's own way in: a bound login, and a bill link.

Revision ID: a7c3e9d14b56
Revises: f4a9d2c71b83

Two things:

1. `invitation.customer_id` (nullable). An invitation that names a customer
   creates a CUSTOMER_PORTAL account bound to that customer at acceptance,
   which closes the gap DEMO-012 left open: the scope was enforced on every
   read, but nothing could set it except a hand in the database. NULL for
   every existing row — every invitation so far has been for staff.

2. `customer_bill_token` — the capability behind the public bill page for a
   household that will never install an app. Only the token's SHA-256 is
   stored. Tenant-owned, so RLS is installed here from the snapshotted list
   below, and `tests/test_security.py` adds that list to its union.

Reversible: the downgrade drops the column and the table. A downgraded
platform has no bill links and no customer-bound invitations, which is the
state before WO-86; existing customer logins keep their `user_account`
binding, which this migration never touched.
"""

import sqlalchemy as sa
from alembic import op

from platform_core.core.rls import BYPASS_SETTING, TENANT_SETTING

revision = "a7c3e9d14b56"
down_revision = "f4a9d2c71b83"
branch_labels = None
depends_on = None

#: Snapshotted, like every migration that installs a policy.
POLICY_TABLES = ("customer_bill_token",)

_TENANT_PREDICATE = (
    f"current_setting('{BYPASS_SETTING}', true) = 'on' "
    "OR tenant_id IS NULL "
    f"OR tenant_id::text = current_setting('{TENANT_SETTING}', true)"
)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    with op.batch_alter_table("invitation") as batch:
        batch.add_column(sa.Column("customer_id", sa.Uuid(), nullable=True))
        batch.create_index("ix_invitation_customer_id", ["customer_id"])

    op.create_table(
        "customer_bill_token",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_customer_bill_token_hash"),
    )
    op.create_index("ix_customer_bill_token_tenant_id", "customer_bill_token", ["tenant_id"])
    op.create_index("ix_customer_bill_token_customer_id", "customer_bill_token", ["customer_id"])
    op.create_index("ix_customer_bill_token_token_hash", "customer_bill_token", ["token_hash"])

    if not _is_postgres():
        return
    for table in POLICY_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING ({_TENANT_PREDICATE}) WITH CHECK ({_TENANT_PREDICATE})"
        )


def downgrade() -> None:
    if _is_postgres():
        for table in POLICY_TABLES:
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
    op.drop_index("ix_customer_bill_token_token_hash", table_name="customer_bill_token")
    op.drop_index("ix_customer_bill_token_customer_id", table_name="customer_bill_token")
    op.drop_index("ix_customer_bill_token_tenant_id", table_name="customer_bill_token")
    op.drop_table("customer_bill_token")
    with op.batch_alter_table("invitation") as batch:
        batch.drop_index("ix_invitation_customer_id")
        batch.drop_column("customer_id")
