"""DEMO-022 record how many plans the calendar suppressed

One nullable-by-default integer on `delivery_generation_run`, and nothing
else. No table is created, no column is dropped or retyped, and no row in any
table is read or written — so no delivery, invoice, payment, receipt or
settlement can be altered by running or reverting this.

**Why a column rather than reusing `not_due`.** They answer different
questions. `not_due` means the plan's own schedule says no today — this
household does not take milk on Tuesdays. `skipped_holiday` means the DAIRY
says no — it is shut, or that plan's centre is. An operator looking at a short
round needs to tell those apart, and folding them together would make the one
number that explains a missing round unreadable.

`server_default="0"` so the column is populated for every historical run
without a data migration: a run recorded before this milestone suppressed
nothing, and zero is the true answer for it rather than a placeholder.

The table carries `tenant_id` and its RLS policy already covers every column,
so no policy work is needed — a policy protects rows, not columns. The
downgrade drops the column and loses only the count.
"""

import sqlalchemy as sa
from alembic import op

revision = "b8d3e1470f92"
down_revision = "a4f7c19d8b52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "delivery_generation_run",
        sa.Column("skipped_holiday", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("delivery_generation_run", "skipped_holiday")
