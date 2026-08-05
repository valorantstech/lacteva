"""rls: allow platform-global rows

Revision ID: c94b1ea27f31
Revises: 6560a9a90ab9
Create Date: 2026-08-06

CI-001. Fixes a defect in the SEC-001 policy that only manifests on
PostgreSQL, which is why no SQLite test could catch it.

The original predicate was:

    tenant_id::text = current_setting('lacteva.tenant_id', true)

Ten tables legitimately hold rows with `tenant_id IS NULL` — rows that belong
to NO tenant: a self-registered user before they join an organization, the
seeded system roles, platform-level audit and outbox entries. In SQL,
`NULL = 'anything'` evaluates to NULL, and a policy predicate that is NULL is
not true, so those rows were invisible to every reader and, through
`WITH CHECK`, impossible to insert.

The practical consequence: with RLS enabled, **user registration fails**.

Allowing `tenant_id IS NULL` does not weaken isolation. Tenant-owned data
always carries a tenant id; a row without one is platform-global by
definition, and making it visible to all tenants is what the application has
always assumed.
"""

import sqlalchemy as sa
from alembic import op

revision = "c94b1ea27f31"
down_revision = "6560a9a90ab9"
branch_labels = None
depends_on = None

TENANT_SETTING = "lacteva.tenant_id"
BYPASS_SETTING = "lacteva.bypass_rls"

# The same snapshot SEC-001 protected, repeated rather than imported: a
# migration is a historical record, and one that reads another migration's
# module both couples them and fails outside a package context.
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

_FIXED = (
    f"current_setting('{BYPASS_SETTING}', true) = 'on' "
    "OR tenant_id IS NULL "
    f"OR tenant_id::text = current_setting('{TENANT_SETTING}', true)"
)
_ORIGINAL = (
    f"current_setting('{BYPASS_SETTING}', true) = 'on' "
    f"OR tenant_id::text = current_setting('{TENANT_SETTING}', true)"
)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _replace(predicate: str) -> None:
    for table in TENANT_TABLES:
        op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                f"USING ({predicate}) WITH CHECK ({predicate})"
            )
        )


def upgrade() -> None:
    if not _is_postgres():
        return  # SQLite has no row-level security
    _replace(_FIXED)


def downgrade() -> None:
    if not _is_postgres():
        return
    _replace(_ORIGINAL)
