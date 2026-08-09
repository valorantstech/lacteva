"""SEC-003 notification secret payload (F-04)

An invitation token is a one-time secret that must reach the invitee and
nobody else — least of all the person who issued the invitation, who could
otherwise accept it and create an account bound to someone else's email.
FINAL-001 found the raw token returned in the invite API response.

Removing it from the response is only half the fix: the token still has to be
delivered, and delivery goes through the notification pipeline, which stores
what it renders so it can retry. `Notification.payload` is exposed by
`NotificationView`, so putting the token there would have moved the exposure
from the inviter's HTTP response to the notification history — where every
holder of `notification.read` could harvest live tokens.

Hence a column that no view reads, holding only the variables whose VALUES are
secret, and cleared the moment the notification reaches a terminal state. The
stored `rendered_text` carries `[redacted]` in place of the token; the real
value exists only in the message handed to the provider.

Expand-only: one nullable JSON column, no backfill, no rewrite, no lock beyond
the catalogue update. Safe to apply while serving traffic, and safe to roll
back — rows written before a downgrade lose only a secret that was already
scheduled to be cleared on delivery.
"""

import sqlalchemy as sa
from alembic import op

revision = "8c41f0a7b2d3"
down_revision = "5d12928a9564"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification",
        sa.Column("secret_payload", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification", "secret_payload")
