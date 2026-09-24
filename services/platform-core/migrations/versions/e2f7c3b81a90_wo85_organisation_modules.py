"""WO-85 / D-31 — the organisation says which of the product's modules it runs.

Revision ID: e2f7c3b81a90
Revises: d1e6b4a92c07

One JSON list column on `organization`, `modules`, exactly as
`supported_languages` is. The keys are `collection` (milk in from suppliers)
and `sales` (milk out to customers); the registry is `core/modules.py`.

**Every existing organisation gets BOTH.** Owner decision D-31: "dont remove
what we have created earlier". A dairy firm that lost its intake screens to a
migration is the failure this line exists to prevent, and
`test_modules.py::test_the_migration_turns_both_modules_on_for_every_existing_organisation`
runs this file against a database with an organisation in it and reads the
column back.

Presentation only: the column decides what a navigation shows. No other
table is read or written, no policy changes, nothing is deleted.

The downgrade drops the column. Nothing is lost that the schema before it
could express, because before it every organisation had everything.
"""

import sqlalchemy as sa
from alembic import op

revision = "e2f7c3b81a90"
down_revision = "d1e6b4a92c07"
branch_labels = None
depends_on = None

BOTH = '["collection", "sales"]'


def upgrade() -> None:
    with op.batch_alter_table("organization") as batch:
        batch.add_column(sa.Column("modules", sa.JSON(), nullable=True))
    # The default, spelled as data rather than as a server default a JSON
    # column cannot portably carry on both dialects: every row that exists
    # when this lands runs the whole product.
    op.execute(f"UPDATE organization SET modules = '{BOTH}' WHERE modules IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("organization") as batch:
        batch.drop_column("modules")
