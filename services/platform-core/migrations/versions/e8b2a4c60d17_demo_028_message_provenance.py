"""DEMO-028 notification provider status and source record

Three nullable columns on `notification`. No table created, no row rewritten,
no financial record touched — this milestone sends information and does not
change money.

`provider_status` holds what the GATEWAY said (`accepted` | `sent` |
`delivered` | `unknown`), separately from `status`, which holds what LACTEVA
did. They were one column, and that is how an accepted request came to be
displayed as a delivery: `DeliveryResult.status` has carried the provider's own
word since MSG-001 and nothing stored it.

`source_type` / `source_id` name the business record a message is ABOUT — the
settlement or the invoice — as opposed to `event_id`, which names what produced
it and is the idempotency key. Asking "what did settlement STL-000123 tell this
farmer?" previously meant walking `event_outbox` payloads.

All three arrive NULL and stay NULL for every existing row, which is the honest
value: nothing recorded before this migration knows what the provider claimed,
and backfilling a guess would put a fact in the audit trail that nobody
observed.

The downgrade drops the three columns and loses only that provenance.
"""

import sqlalchemy as sa
from alembic import op

revision = "e8b2a4c60d17"
down_revision = "d5f1c8a72e46"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notification", sa.Column("provider_status", sa.String(length=20), nullable=True))
    op.add_column("notification", sa.Column("source_type", sa.String(length=30), nullable=True))
    op.add_column("notification", sa.Column("source_id", sa.Uuid(), nullable=True))
    op.create_index("ix_notification_source_id", "notification", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_notification_source_id", table_name="notification")
    op.drop_column("notification", "source_id")
    op.drop_column("notification", "source_type")
    op.drop_column("notification", "provider_status")
