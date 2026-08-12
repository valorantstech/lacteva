"""DEMO-008 RBAC: centre-scoped grants and last-login

Two nullable columns, both expand-only.

`user_role.center_id` is the optional CENTRE scope of a grant. NULL means
organization-wide, which is what every grant written before this migration
means — so adding the column narrows nobody. A non-null value restricts that
grant to a single collection centre, which is how a centre manager differs from
an organization manager holding the same permissions. The scope lives on the
GRANT rather than on the role because the same role is worth granting at
different scopes: a person can run centre A and later centre B without a second
role being invented for them.

`user_account.last_login_at` records when an account last authenticated
successfully. It is nullable rather than defaulted to the creation time,
because "never signed in" is a distinct and useful answer for an administrator
reviewing access — backfilling it with `created_at` would have manufactured a
login that never happened.

Neither column is backfilled, neither is indexed as a constraint change, and
no existing row is rewritten: the catalogue update is the whole of it. Safe to
apply while serving traffic, and safe to roll back — a downgrade loses a scope
that only DEMO-008 grants can carry, and a timestamp that the next login
rewrites.
"""

import sqlalchemy as sa
from alembic import op

revision = "a3f81c46b204"
down_revision = "8c41f0a7b2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_role", sa.Column("center_id", sa.Uuid(), nullable=True))
    op.create_index("ix_user_role_center_id", "user_role", ["center_id"])
    op.add_column(
        "user_account",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_account", "last_login_at")
    op.drop_index("ix_user_role_center_id", table_name="user_role")
    op.drop_column("user_role", "center_id")
