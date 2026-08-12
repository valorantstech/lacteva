"""DEMO-009 row-level security for the sales tables

Found by the deployment verifier, which is what it is for.

`b3e18f736894` created eight tenant-owned tables and did not give them row-level
security policies. On this platform RLS is installed BY MIGRATIONS — not at
startup — so a migration that adds a tenant-owned table and stops there leaves
that table protected by application filters alone. The verifier's check
("every tenant-owned table has a policy") failed the deploy, which is exactly
the outcome SEC-002 built it for.

The exposure was latent rather than live: the rolled-back image had no sales
endpoints, so nothing could reach the tables at all. But `tenant_tables()` is
derived from the metadata precisely so that a new table cannot be forgotten,
and the derivation only helps if the policy DDL follows it.

Policies are identical to every other tenant-owned table (`core/rls.py`
`policy_statements`): one policy covering SELECT/INSERT/UPDATE/DELETE, with
`USING` restricting what is visible and `WITH CHECK` restricting what may be
written, so no operation can create or move a row into another tenant. FORCE is
essential — without it the table owner, which is who the application connects
as, silently bypasses its own policies.

SQLite has no row-level security; the columns already match, and the policies
are proven by the PostgreSQL suite.

Reversible: the downgrade drops the policies and disables RLS, returning the
tables to the state `b3e18f736894` left them in.
"""

from alembic import op

from platform_core.core.rls import BYPASS_SETTING, TENANT_SETTING

revision = "c8a4d2f10b73"
down_revision = "b3e18f736894"
branch_labels = None
depends_on = None

SALES_TABLES = (
    "customer",
    "delivery_plan",
    "milk_delivery",
    "customer_invoice",
    "customer_invoice_line",
    "customer_payment",
    "customer_payment_allocation",
    "customer_receipt",
)

_TENANT_PREDICATE = (
    f"current_setting('{BYPASS_SETTING}', true) = 'on' "
    "OR tenant_id IS NULL "
    f"OR tenant_id::text = current_setting('{TENANT_SETTING}', true)"
)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return
    for table in SALES_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING ({_TENANT_PREDICATE}) WITH CHECK ({_TENANT_PREDICATE})"
        )


def downgrade() -> None:
    if not _is_postgres():
        return
    for table in SALES_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
