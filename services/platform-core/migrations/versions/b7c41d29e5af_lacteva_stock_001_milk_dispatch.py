"""LACTEVA-STOCK-001 milk dispatch

WO-56. Bulk milk leaving a collection centre — the third movement in a
centre's day, and the one nothing recorded (BR-0030). A movement, not a sale:
no customer, no rate, no amount, no currency, and no foreign key that could
introduce one later.

Every NOT NULL column with a Python-side default gets a SERVER default too.
The table is new and has no rows to migrate, but the LACTEVA-NOTIFY-003 lesson
holds regardless: a default that exists only in the ORM is not a default the
database has, and the first insert that does not go through SQLAlchemy fails.

Revision ID: b7c41d29e5af
Revises: 0e45ee1f7f13
Create Date: 2026-09-02 00:30:50.808866
"""

import sqlalchemy as sa
from alembic import op

#: The tables this migration grants a policy to, snapshotted here rather than
#: read from the models: a migration is a historical record and must not change
#: meaning when the models later do. `test_security.py` unions these lists, so
#: a new tenant-owned table cannot become protected by accident.
POLICY_TABLES = ("milk_dispatch",)

revision = "b7c41d29e5af"
down_revision = "0e45ee1f7f13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "milk_dispatch",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("center_id", sa.Uuid(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("milk_type", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("quantity_unit", sa.String(length=8), server_default="kg", nullable=False),
        sa.Column("destination", sa.String(length=120), nullable=False),
        sa.Column("reference", sa.String(length=60), server_default="", nullable=False),
        sa.Column("notes", sa.String(length=300), server_default="", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="recorded", nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_by", sa.Uuid(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(length=300), server_default="", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_milk_dispatch_business_date"), "milk_dispatch", ["business_date"], unique=False
    )
    op.create_index(
        op.f("ix_milk_dispatch_center_id"), "milk_dispatch", ["center_id"], unique=False
    )
    op.create_index(
        op.f("ix_milk_dispatch_milk_type"), "milk_dispatch", ["milk_type"], unique=False
    )
    op.create_index(op.f("ix_milk_dispatch_status"), "milk_dispatch", ["status"], unique=False)
    op.create_index(
        op.f("ix_milk_dispatch_tenant_id"), "milk_dispatch", ["tenant_id"], unique=False
    )

    # SEC-002: tenant-owned means a policy, always.
    if op.get_bind().dialect.name == "postgresql":
        predicate = (
            "current_setting('lacteva.bypass_rls', true) = 'on' "
            "OR tenant_id IS NULL "
            "OR tenant_id::text = current_setting('lacteva.tenant_id', true)"
        )
        for table in POLICY_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                f"USING ({predicate}) WITH CHECK ({predicate})"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in POLICY_TABLES:
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
    op.drop_index(op.f("ix_milk_dispatch_tenant_id"), table_name="milk_dispatch")
    op.drop_index(op.f("ix_milk_dispatch_status"), table_name="milk_dispatch")
    op.drop_index(op.f("ix_milk_dispatch_milk_type"), table_name="milk_dispatch")
    op.drop_index(op.f("ix_milk_dispatch_center_id"), table_name="milk_dispatch")
    op.drop_index(op.f("ix_milk_dispatch_business_date"), table_name="milk_dispatch")
    op.drop_table("milk_dispatch")
