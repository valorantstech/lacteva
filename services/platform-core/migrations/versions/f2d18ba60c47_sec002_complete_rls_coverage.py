"""sec-002: complete RLS coverage

Revision ID: f2d18ba60c47
Revises: c94b1ea27f31
Create Date: 2026-08-06

SEC-002. Closes the gap ABR-002 found: **every table now declares exactly one
isolation strategy**, and the ones that claim to be tenant-owned are actually
protected by the database rather than by whichever query remembered to join.

Three things happen here.

1. **Thirteen tenant-owned tables gain `tenant_id` and a policy.** They are
   child rows of a tenant-owned aggregate — supplier profiles, bank accounts,
   documents, settlement lines, payment lines and attempts, receipt lines,
   price bands, center config/windows/calendar, device health reports, role
   permissions. Each was reachable only through its parent, so SEC-001's
   "does it have a tenant_id column" rule skipped them and BR-0022's promise
   — a query that forgets its filter returns NOTHING — was simply false for
   them. `supplier_profile` (names, phones, national IDs) and
   `supplier_bank_account` (account numbers) were the worst of it.

   Denormalising `tenant_id` is safe here because no aggregate in this
   platform is ever reparented: a settlement line does not move to another
   settlement, a profile does not move to another supplier.

2. **`organization` gains an identity policy.** It has no `tenant_id` because
   it IS the tenant — `organization.id` is what every other `tenant_id`
   points at. It was therefore readable by any bound session, which meant a
   tenant could enumerate the platform's customer list. It is now isolated by
   its own primary key.

3. **`role_permission` is nullable** because its parent `role` is: system
   roles belong to no tenant. The standard policy already treats a NULL
   tenant as globally visible, which is exactly right for a shared catalog.

Ordering matters and is easy to get wrong: the backfill must complete BEFORE
the policy is created, or the policy filters the very UPDATE that populates
the column it is filtering on.
"""

import sqlalchemy as sa
from alembic import op

revision = "f2d18ba60c47"
down_revision = "c94b1ea27f31"
branch_labels = None
depends_on = None

# Snapshot, not an import. A migration is a historical record: it must keep
# meaning what it meant when it ran, even after the models move on. (The same
# reasoning as the TENANT_TABLES snapshot in a1c7f3b90e22.)
TENANT_SETTING = "lacteva.tenant_id"
BYPASS_SETTING = "lacteva.bypass_rls"

# child table -> (parent table, join column, nullable tenant)
NEW_TENANT_TABLES: dict[str, tuple[str, str, bool]] = {
    "supplier_profile": ("supplier", "supplier_id", False),
    "supplier_bank_account": ("supplier", "supplier_id", False),
    "supplier_document": ("supplier", "supplier_id", False),
    "settlement_line": ("settlement", "settlement_id", False),
    "payment_line": ("payment", "payment_id", False),
    "payment_attempt": ("payment", "payment_id", False),
    "receipt_line": ("receipt", "receipt_id", False),
    "pricing_matrix_row": ("pricing_matrix", "matrix_id", False),
    "collection_center_config": ("collection_center", "center_id", False),
    "center_operating_window": ("collection_center", "center_id", False),
    "center_calendar_entry": ("collection_center", "center_id", False),
    "device_health_report": ("device", "device_id", False),
    # `role` may itself be global (system roles), so this one stays nullable.
    "role_permission": ("role", "role_id", True),
}

_TENANT_PREDICATE = (
    f"current_setting('{BYPASS_SETTING}', true) = 'on' "
    "OR tenant_id IS NULL "
    f"OR tenant_id::text = current_setting('{TENANT_SETTING}', true)"
)

_IDENTITY_PREDICATE = (
    f"current_setting('{BYPASS_SETTING}', true) = 'on' "
    f"OR id::text = current_setting('{TENANT_SETTING}', true)"
)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # --- 1. the column, everywhere (both dialects) ------------------------
    for table, (parent, column, nullable) in NEW_TENANT_TABLES.items():
        op.add_column(table, sa.Column("tenant_id", sa.Uuid(), nullable=True))
        op.execute(
            f"UPDATE {table} SET tenant_id = p.tenant_id "  # noqa: S608 - fixed identifiers
            f"FROM {parent} p WHERE p.id = {table}.{column}"
            if _is_postgres()
            else f"UPDATE {table} SET tenant_id = "  # noqa: S608 - fixed identifiers
            f"(SELECT p.tenant_id FROM {parent} p WHERE p.id = {table}.{column})"
        )
        if not nullable:
            # Rows whose parent vanished cannot be assigned a tenant. There
            # should be none — but if there are, they are orphans and this is
            # where the platform finds out, which is the right place.
            op.execute(f"DELETE FROM {table} WHERE tenant_id IS NULL")  # noqa: S608
            # Batch mode because SQLite cannot ALTER a column in place; on
            # PostgreSQL this emits the plain ALTER and costs one scan.
            with op.batch_alter_table(table) as batch:
                batch.alter_column("tenant_id", existing_type=sa.Uuid(), nullable=False)
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])

    if not _is_postgres():
        # SQLite has no row-level security. The columns above still apply, so
        # the schemas match; the policies are proven by the PostgreSQL suite.
        return

    # --- 2. policies for the newly tenant-owned tables ---------------------
    for table in NEW_TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING ({_TENANT_PREDICATE}) WITH CHECK ({_TENANT_PREDICATE})"
        )

    # --- 3. organization, isolated by identity ----------------------------
    # No `IS NULL` escape: `id` is NOT NULL, so an unbound session sees no
    # organization at all. Creation and platform-admin reads use the audited
    # bypass instead, because both are genuinely cross-tenant acts.
    op.execute("ALTER TABLE organization ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organization FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY organization_tenant_isolation ON organization "
        f"USING ({_IDENTITY_PREDICATE}) WITH CHECK ({_IDENTITY_PREDICATE})"
    )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS organization_tenant_isolation ON organization")
        op.execute("ALTER TABLE organization NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE organization DISABLE ROW LEVEL SECURITY")
        for table in NEW_TENANT_TABLES:
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    for table in NEW_TENANT_TABLES:
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")
