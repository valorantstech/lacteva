"""DEMO-014 timezone hierarchy

Three timezones existed and nothing said which one a business date was
measured on. This migration makes the hierarchy expressible:

    organization    the business clock — always set, always the answer
    centre          an OPTIONAL override, NULL meaning "my organization's"
    user            display only, NULL meaning "my organization's"

**`collection_center.timezone` was `String(40) NOT NULL DEFAULT 'UTC'`.**

That default is the reason this migration exists. `'UTC'` is a real IANA zone,
so a centre that nobody configured is indistinguishable from one deliberately
running on UTC — and every centre created before DEMO-013 in a Kenyan dairy
claims a clock three hours from the one its milk is actually collected on.

The column becomes nullable and **every row still holding the literal `'UTC'`
is set to NULL**, which is the only lossless reading available: the platform
never asked anyone for a centre timezone in a form that could have meant it,
so `'UTC'` is the default's fingerprint rather than anybody's decision. A
centre that genuinely operates on UTC — none exists; no country in the
registry uses it — can say so again, and the value will then mean something.

Rows holding any OTHER zone are left exactly as they are: somebody set those.

`user_account.timezone` is new, nullable, and display-only. It is not read by
any date-boundary code, by construction: `core/timezones.business_timezone()`
does not take a user.

Reversible: the downgrade restores `'UTC'` for NULLs and the NOT NULL
constraint, which is the shape before this ran. It cannot distinguish a NULL
that was `'UTC'` from one that was never set — but after this migration those
mean the same thing, which is the entire point.
"""

import sqlalchemy as sa
from alembic import op

revision = "c5e83b19d740"
down_revision = "b8d41f7e2a95"
branch_labels = None
depends_on = None

_center = sa.table(
    "collection_center",
    sa.column("timezone", sa.String),
)


def upgrade() -> None:
    with op.batch_alter_table("collection_center") as batch:
        batch.alter_column(
            "timezone",
            existing_type=sa.String(length=40),
            type_=sa.String(length=64),
            existing_nullable=False,
            nullable=True,
        )

    # The default's fingerprint, cleared. See the module docstring.
    op.execute(_center.update().where(_center.c.timezone == "UTC").values(timezone=None))

    op.add_column("user_account", sa.Column("timezone", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("user_account", "timezone")

    op.execute(_center.update().where(_center.c.timezone.is_(None)).values(timezone="UTC"))
    with op.batch_alter_table("collection_center") as batch:
        batch.alter_column(
            "timezone",
            existing_type=sa.String(length=64),
            type_=sa.String(length=40),
            existing_nullable=True,
            nullable=False,
        )
