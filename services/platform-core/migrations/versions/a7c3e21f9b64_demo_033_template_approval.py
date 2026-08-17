"""DEMO-033 notification template approval

One new PLATFORM-GLOBAL table. No tenant column, no RLS policy, and that is a
declared decision rather than an omission — see `core/rls.py`'s PLATFORM_GLOBAL
entry, and `test_every_table_declares_an_isolation_strategy`, which fails if a
new table appears in none of the classifications.

The messaging account a template is approved against is LACTEVA's, not a
dairy's. Scoping approval per tenant would have five dairies separately
tracking the same external decision about the same account, and four of them
would be wrong.

**No data migration, and deliberately no backfill.** Every template shipped
before this milestone starts with NO ROW, which the registry reports as
`NOT_CONFIGURED`. Inserting `approved` rows would be fabricating an external
approval that nobody obtained — the one thing §9 forbids.

No financial record is read or written. A template's standing with a provider
is not money.

The downgrade drops the table and loses the record of which templates were
submitted; it loses nothing that any external party knows.
"""

import sqlalchemy as sa
from alembic import op

revision = "a7c3e21f9b64"
down_revision = "f3a9c71d5e28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_template_approval",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("template_key", sa.String(length=80), nullable=False),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=12), nullable=False, server_default="pending"),
        sa.Column("provider_template_id", sa.String(length=160), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "template_key",
            "channel",
            "language",
            "provider",
            name="uq_notification_template_approval",
        ),
    )
    op.create_index(
        "ix_notification_template_approval_state", "notification_template_approval", ["state"]
    )
    op.create_index(
        "ix_notification_template_approval_key",
        "notification_template_approval",
        ["template_key", "channel"],
    )
    # No RLS. PLATFORM_GLOBAL, with the reason written in core/rls.py.


def downgrade() -> None:
    op.drop_index(
        "ix_notification_template_approval_key", table_name="notification_template_approval"
    )
    op.drop_index(
        "ix_notification_template_approval_state", table_name="notification_template_approval"
    )
    op.drop_table("notification_template_approval")
