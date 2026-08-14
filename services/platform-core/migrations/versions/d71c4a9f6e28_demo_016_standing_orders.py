"""DEMO-016 standing orders

A delivery plan already said WHAT a customer takes and at WHAT PRICE. It did
not say WHEN, so somebody still had to type six hundred deliveries a day. This
adds the schedule.

**Every column is nullable or defaulted, and that is deliberate**: this
migration must not invalidate a single existing plan. A plan written before
today becomes a daily standing order with no end and no holiday, which is
exactly what it already meant in practice — the seeder and the portal both
treated `default_quantity` as "every day".

    weekdays            NOT NULL DEFAULT '1111111'  — Monday first
    effective_to        NULL = ongoing
    paused_from/_to     NULL = running
    quantity_overrides  NULL = every delivery day takes the standing quantity
    center_id           NULL = the organization at large
    slot                NOT NULL DEFAULT 'morning'  — matches milk_delivery's
    created_by          NULL for every row that predates this
    updated_at          defaulted to created_at, which is true of a row that
                        has never been edited

`ix_delivery_plan_generation` is the generator's own index: the one query that
runs against every plan a dairy has, every morning. Tenant first because RLS
filters on it before anything else.

**No RLS work.** `delivery_plan` has carried `tenant_id` and a FORCEd policy
since DEMO-009, and `core/rls.py` derives the protected set from the metadata
rather than a hand-kept list — so extending an already-protected table is
covered by construction. That is a large part of why DEMO-016 extends this
table instead of adding a second one.

Reversible: the downgrade drops what it added. Data in the dropped columns is
lost, which is the honest shape of removing a feature — but no delivery,
invoice, payment or receipt is touched by either direction, so a rollback
costs schedules and nothing financial.
"""

import sqlalchemy as sa
from alembic import op

revision = "d71c4a9f6e28"
down_revision = "c5e83b19d740"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("delivery_plan") as batch:
        batch.add_column(sa.Column("effective_to", sa.Date(), nullable=True))
        # server_default, not default: the rows that already exist are filled
        # by the database as the column is added. A Python-side default would
        # leave every historical plan NULL and the generator would skip the
        # entire dairy.
        batch.add_column(
            sa.Column("weekdays", sa.String(length=7), nullable=False, server_default="1111111")
        )
        batch.add_column(sa.Column("paused_from", sa.Date(), nullable=True))
        batch.add_column(sa.Column("paused_to", sa.Date(), nullable=True))
        batch.add_column(sa.Column("quantity_overrides", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("center_id", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column("slot", sa.String(length=10), nullable=False, server_default="morning")
        )
        batch.add_column(sa.Column("created_by", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )

    op.create_index("ix_delivery_plan_center_id", "delivery_plan", ["center_id"])
    op.create_index(
        "ix_delivery_plan_generation",
        "delivery_plan",
        ["tenant_id", "active", "effective_from", "effective_to"],
    )


def downgrade() -> None:
    op.drop_index("ix_delivery_plan_generation", table_name="delivery_plan")
    op.drop_index("ix_delivery_plan_center_id", table_name="delivery_plan")
    with op.batch_alter_table("delivery_plan") as batch:
        for column in (
            "updated_at",
            "created_by",
            "slot",
            "center_id",
            "quantity_overrides",
            "paused_to",
            "paused_from",
            "weekdays",
            "effective_to",
        ):
            batch.drop_column(column)
