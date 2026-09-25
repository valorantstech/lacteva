"""WO-87 — a login's email is changed by the new address confirming, never by a write.

Revision ID: d4a7c19e58b2
Revises: c9e5a3b72d14

One table, `email_change`: the pending request (who, to what address, who
asked, when it expires) and a hash of the one-time code the new address is
sent. No tenant_id, deliberately — see `core/rls.py` PLATFORM_GLOBAL.

Reversible: the downgrade drops the table.
"""

import sqlalchemy as sa
from alembic import op

revision = "d4a7c19e58b2"
down_revision = "c9e5a3b72d14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_change",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("new_email", sa.String(length=320), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_email_change_token_hash"), "email_change", ["token_hash"], unique=True)
    op.create_index(op.f("ix_email_change_user_id"), "email_change", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_email_change_user_id"), table_name="email_change")
    op.drop_index(op.f("ix_email_change_token_hash"), table_name="email_change")
    op.drop_table("email_change")
