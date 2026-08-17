"""DEMO-034 logistics — routes, stops, vehicles, drivers and delivery runs

Five new TENANT-OWNED tables, every one carrying `tenant_id` and every one
given the standard isolation policy from `core/rls.py`. Nothing here is
platform-global: a dairy's rounds, vans and drivers are its own.

**No existing table is altered and no row is written.** The delivery domain
keeps its schema and its meaning: `milk_delivery` gains no route column, no
run reference and no new status. A run COMPOSES deliveries at read time, so
there is nothing to backfill and nothing that can drift.

**No financial table is read or written.** A route is an operational execution
concept — it holds no quantity, no amount, no balance and no billing state —
so no invoice, settlement, payment or receipt is touched by this migration or
by anything it enables.

The downgrade drops the five tables. It loses the record of which van went
where, and loses nothing about what was delivered or what it was worth,
because none of that was ever stored here.
"""

import sqlalchemy as sa
from alembic import op

revision = "b5d1e07a4c39"
down_revision = "a7c3e21f9b64"
branch_labels = None
depends_on = None

POLICY_TABLES = ("route", "route_stop", "vehicle", "driver", "delivery_run")


def upgrade() -> None:
    op.create_table(
        "route",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("center_id", sa.Uuid(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "code", name="uq_route_tenant_code"),
    )
    op.create_index("ix_route_tenant_id", "route", ["tenant_id"])
    op.create_index("ix_route_code", "route", ["code"])
    op.create_index("ix_route_center_id", "route", ["center_id"])
    op.create_index("ix_route_active", "route", ["active"])

    op.create_table(
        "route_stop",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("route_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # One customer cannot be on the same route twice. The constraint a
        # duplicate-association race has to lose to.
        sa.UniqueConstraint("route_id", "customer_id", name="uq_route_stop_customer"),
    )
    op.create_index("ix_route_stop_tenant_id", "route_stop", ["tenant_id"])
    op.create_index("ix_route_stop_route_id", "route_stop", ["route_id"])
    op.create_index("ix_route_stop_customer_id", "route_stop", ["customer_id"])
    op.create_index("ix_route_stop_order", "route_stop", ["tenant_id", "route_id", "position"])

    op.create_table(
        "vehicle",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("registration", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("center_id", sa.Uuid(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "registration", name="uq_vehicle_tenant_registration"),
    )
    op.create_index("ix_vehicle_tenant_id", "vehicle", ["tenant_id"])
    op.create_index("ix_vehicle_registration", "vehicle", ["registration"])
    op.create_index("ix_vehicle_center_id", "vehicle", ["center_id"])
    op.create_index("ix_vehicle_active", "vehicle", ["active"])

    op.create_table(
        "driver",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=24), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("center_id", sa.Uuid(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "code", name="uq_driver_tenant_code"),
    )
    op.create_index("ix_driver_tenant_id", "driver", ["tenant_id"])
    op.create_index("ix_driver_code", "driver", ["code"])
    op.create_index("ix_driver_user_id", "driver", ["user_id"])
    op.create_index("ix_driver_center_id", "driver", ["center_id"])
    op.create_index("ix_driver_active", "driver", ["active"])

    op.create_table(
        "delivery_run",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("route_id", sa.Uuid(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(length=10), nullable=False, server_default="morning"),
        sa.Column("vehicle_id", sa.Uuid(), nullable=True),
        sa.Column("driver_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="planned"),
        sa.Column("notes", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # The idempotency guard, in the database rather than in Python: two
        # operators tapping "start today's run" produce one row and one loser.
        sa.UniqueConstraint(
            "tenant_id",
            "route_id",
            "business_date",
            "slot",
            name="uq_delivery_run_route_date_slot",
        ),
    )
    op.create_index("ix_delivery_run_tenant_id", "delivery_run", ["tenant_id"])
    op.create_index("ix_delivery_run_route_id", "delivery_run", ["route_id"])
    op.create_index("ix_delivery_run_business_date", "delivery_run", ["business_date"])
    op.create_index("ix_delivery_run_status", "delivery_run", ["status"])
    op.create_index("ix_delivery_run_vehicle_id", "delivery_run", ["vehicle_id"])
    op.create_index("ix_delivery_run_driver_id", "delivery_run", ["driver_id"])
    op.create_index("ix_delivery_run_day", "delivery_run", ["tenant_id", "business_date", "status"])

    # RLS, on PostgreSQL only. SQLite has no such thing, and the test stack
    # relies on the application filters that are defence-in-depth in
    # production and the whole story in tests.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from platform_core.core.rls import policy_statements

        for table in POLICY_TABLES:
            for statement in policy_statements(table):
                op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from platform_core.core.rls import drop_statements

        for table in POLICY_TABLES:
            for statement in drop_statements(table):
                op.execute(statement)

    op.drop_table("delivery_run")
    op.drop_table("driver")
    op.drop_table("vehicle")
    op.drop_table("route_stop")
    op.drop_table("route")
