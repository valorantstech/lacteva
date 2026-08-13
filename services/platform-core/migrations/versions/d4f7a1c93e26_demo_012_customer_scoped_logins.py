"""DEMO-012 customer-scoped logins

A dairy's household signing in on the mobile app must see its own deliveries
and its own bill — and nothing else in the organization.

Tenancy cannot express that. Every `sales.*` permission is tenant-wide, so a
customer granted `sales.invoice.read` so it can read its own bill would read
every other household's bill in the same dairy. Tenancy answers "which
organization"; this column answers "which customer inside it".

`customer_id` is NULL for every existing account and for every staff account,
which is what makes this additive: the scope only ever REMOVES rows
(`core/tenancy.enforce_customer_scope`), so a scope that fails to apply cannot
widen anyone's access — it can only show a customer nothing.

Referenced by id, with no foreign key, because `customer` belongs to another
module and the baseline forbids joining across that boundary. The index exists
because every request from a customer login reads this column.

Reversible: the downgrade drops the column, returning every account to
unscoped, which is exactly the state before DEMO-012.
"""

import sqlalchemy as sa
from alembic import op

revision = "d4f7a1c93e26"
down_revision = "c8a4d2f10b73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_account",
        sa.Column("customer_id", sa.Uuid(), nullable=True),
    )
    op.create_index("ix_user_account_customer_id", "user_account", ["customer_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_account_customer_id", table_name="user_account")
    op.drop_column("user_account", "customer_id")
