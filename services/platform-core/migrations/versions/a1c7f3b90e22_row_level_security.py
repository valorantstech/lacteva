"""row level security

Revision ID: a1c7f3b90e22
Revises: e8845cde90c0
Create Date: 2026-08-05

SEC-001. Makes PostgreSQL authoritative for tenant isolation: every
tenant-owned table gets a policy comparing its `tenant_id` against the
`lacteva.tenant_id` session setting, with an explicit `lacteva.bypass_rls`
escape hatch for the machinery that is definitionally cross-tenant (relay
dispatch, consumers, projection rebuilds).

The table list is SNAPSHOTTED here rather than derived from live metadata: a
migration is a historical record and must not change meaning when the models
later do. A runtime test asserts the current metadata is fully covered, so a
new tenant-owned table cannot ship without its own policy migration.

SQLite has no row-level security, so this migration is a no-op there. The
divergence is deliberate and documented in RLS-GUIDE.md.
"""

import sqlalchemy as sa
from alembic import op

revision = "a1c7f3b90e22"
down_revision = "e8845cde90c0"
branch_labels = None
depends_on = None

TENANT_SETTING = "lacteva.tenant_id"
BYPASS_SETTING = "lacteva.bypass_rls"

# Snapshot of every tenant-owned table as of SEC-001.
TENANT_TABLES = (
    "audit_record",
    "auth_session",
    "branch",
    "collection_center",
    "collection_session",
    "config_entry",
    "consumer_execution",
    "dead_letter_queue",
    "device",
    "event_outbox",
    "invitation",
    "membership",
    "milk_collection_transaction",
    "notification",
    "notification_recipient",
    "operator_assignment",
    "payment",
    "pricing_matrix",
    # Projection read models register at consumer discovery rather than at
    # import, which is exactly how they were missed on the first pass —
    # the coverage test caught them.
    "projection_center_totals",
    "projection_daily_totals",
    "projection_supplier_totals",
    "quality_dimension",
    "rate_card",
    "rate_card_center_assignment",
    "rate_card_product_assignment",
    "receipt",
    "role",
    "settlement",
    "supplier",
    "supplier_center_assignment",
    "sync_operation",
    "transaction_event",
    "transaction_metrics",
    "transaction_snapshot",
    "user_account",
    "user_role",
    "workspace",
)

_PREDICATE = (
    f"current_setting('{BYPASS_SETTING}', true) = 'on' "
    f"OR tenant_id::text = current_setting('{TENANT_SETTING}', true)"
)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return  # SQLite: no RLS engine; application filters remain the guard
    for table in TENANT_TABLES:
        # FORCE matters: without it the table OWNER — which is who the
        # application connects as — silently bypasses its own policies.
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
            )
        )


def downgrade() -> None:
    if not _is_postgres():
        return
    for table in TENANT_TABLES:
        op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
