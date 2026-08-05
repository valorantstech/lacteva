"""PostgreSQL Row Level Security binding (SEC-001).

Until now tenant isolation held because every query remembered to filter by
`tenant_id`. That is a discipline, and disciplines fail silently — one
forgotten predicate in one new module is a cross-tenant leak that no test
necessarily catches. RLS moves the guarantee into the database: a policy
compares each row's `tenant_id` against a session variable, so a query that
forgets the filter returns nothing rather than another dairy's milk.

Application filters stay exactly where they are. They become
**defense-in-depth** and, just as importantly, they keep query plans sane —
the database is authoritative, not solely responsible.

**How the tenant reaches the database.** Each request sets
`lacteva.tenant_id` on its connection with `SET LOCAL`, which is scoped to the
transaction and therefore cannot leak across pooled connections. Platform
operations that legitimately span tenants (the relay dispatcher, consumers,
projection rebuilds) set `lacteva.bypass_rls` instead — an explicit,
auditable escape hatch rather than a superuser connection.

**SQLite.** SQLite has no row-level security, so the test stack cannot execute
these policies; the binding degrades to a no-op there. That is a real
divergence and it is documented in RLS-GUIDE.md: SQLite tests prove the
application-level isolation, and the policies themselves are proven by the
Postgres-only suite plus the migration's own assertions.
"""

import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.config import get_settings

log = structlog.get_logger("security.rls")

TENANT_SETTING = "lacteva.tenant_id"
BYPASS_SETTING = "lacteva.bypass_rls"


def tenant_tables() -> tuple[str, ...]:
    """Every tenant-owned table, DERIVED from the mapped metadata.

    Hand-maintaining this list is how a new module quietly ships without
    protection; deriving it means a table with a `tenant_id` column is either
    covered or a test fails. Migrations still snapshot their own list — a
    migration is a historical record and must not change meaning when the
    models later do.
    """
    from platform_core.core.db import Base

    return tuple(
        sorted(
            table.name for table in Base.metadata.tables.values() if "tenant_id" in table.columns
        )
    )


def is_postgres() -> bool:
    return get_settings().database_url.startswith("postgresql")


async def bind_tenant(session: AsyncSession, tenant_id: uuid.UUID | None) -> None:
    """Bind the request's tenant to this transaction.

    `SET LOCAL` is transaction-scoped: when the transaction ends the setting
    is gone, so a pooled connection can never carry one request's tenant into
    the next request's query.
    """
    if not is_postgres() or not get_settings().rls_enabled:
        return
    await session.execute(
        text(f"SET LOCAL {TENANT_SETTING} = :tenant"),
        {"tenant": str(tenant_id) if tenant_id else ""},
    )
    await session.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'off'"))


async def bind_platform_context(session: AsyncSession, *, reason: str) -> None:
    """Grant this transaction cross-tenant visibility.

    Used only by machinery that is definitionally multi-tenant — the relay
    dispatcher, consumers, projection rebuilds, and platform-admin operations.
    The reason is logged so an auditor can see every place the guarantee was
    deliberately stepped around.
    """
    if not is_postgres() or not get_settings().rls_enabled:
        return
    await session.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
    log.debug("rls_bypass_granted", reason=reason)


def policy_statements(table: str) -> list[str]:
    """The DDL for one table's protection.

    A single policy covers SELECT, INSERT, UPDATE, and DELETE: `USING`
    restricts which rows are visible and modifiable, and `WITH CHECK`
    restricts what may be written, so no operation can create or move a row
    into another tenant.

    `tenant_id IS NULL` is explicitly allowed. Such a row belongs to no
    tenant — a self-registered user, a seeded system role, a platform-level
    audit entry — and `NULL = 'anything'` is NULL in SQL, which a policy
    treats as false. Without this clause, registration itself fails
    (CI-001 found this; SQLite could not).

    FORCE is essential — without it the table owner (which is who the
    application connects as) silently bypasses its own policies.
    """
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"""
        CREATE POLICY {table}_tenant_isolation ON {table}
        USING (
            current_setting('{BYPASS_SETTING}', true) = 'on'
            OR tenant_id IS NULL
            OR tenant_id::text = current_setting('{TENANT_SETTING}', true)
        )
        WITH CHECK (
            current_setting('{BYPASS_SETTING}', true) = 'on'
            OR tenant_id IS NULL
            OR tenant_id::text = current_setting('{TENANT_SETTING}', true)
        )
        """,
    ]


def drop_statements(table: str) -> list[str]:
    """The rollback path (see SECURITY.md): policies come off cleanly."""
    return [
        f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
    ]
