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
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_core.core.config import get_settings

log = structlog.get_logger("security.rls")

TENANT_SETTING = "lacteva.tenant_id"
BYPASS_SETTING = "lacteva.bypass_rls"

# SEC-002: every table declares exactly one isolation strategy. The taxonomy
# is deliberately closed — "we never decided" is not one of the options, and
# `test_security.py::test_every_table_declares_an_isolation_strategy` fails
# when a new table appears in none of these sets.
#
#   A  TENANT_OWNED    carries tenant_id; the standard policy applies
#   B  PLATFORM_GLOBAL no tenant; RLS must NOT be enabled, with a reason
#   C  MIXED           holds both tenant and platform rows, or is isolated by
#                      a column other than tenant_id — always needs prose
#
# A is derived from the metadata (`tenant_tables()`), because a hand-kept
# list is how a new module ships unprotected. B and C are declared here,
# because "this table is deliberately not protected" is a decision and must
# be written down where the next reviewer will look.

PLATFORM_GLOBAL: dict[str, str] = {
    "consumer_cursor": (
        "One row per consumer, not per tenant. The consumer loop is "
        "definitionally cross-tenant and reads this under an audited bypass."
    ),
    "projection_state": (
        "One row per projection. Rebuild state belongs to the platform, not "
        "to any tenant whose events the projection happens to contain."
    ),
    "backup_run": (
        "Platform operations history. A backup spans every tenant; scoping "
        "it to one would make the record of a whole-database backup invisible."
    ),
    "event_delivery": (
        "Dispatch bookkeeping — attempt number, status, transport, latency. "
        "Carries no business payload and is read only by platform operators. "
        "Deliberately NOT given a tenant_id so that outbox partitions can be "
        "detached and dropped without a dependent policy (DBD-0001 §7.3)."
    ),
    "password_reset_token": (
        "Read by a flow that is definitionally unauthenticated: the caller "
        "presents a token hash and has no tenant bound, and cannot have one, "
        "because discovering which tenant the user belongs to is the point of "
        "the lookup. A policy here would make password reset impossible for "
        "every tenant-scoped user. Rows hold a hash and an expiry, never a "
        "credential, and are unreachable without the plaintext token."
    ),
}

MIXED: dict[str, str] = {
    "organization": (
        "IS the tenant — `organization.id` is what every other table's "
        "tenant_id points at, so it cannot be isolated by a tenant_id column "
        "it does not have. Isolated by IDENTITY instead: a bound session sees "
        "exactly its own organization. Creation and platform-admin listing "
        "run under an audited bypass, because an organization necessarily "
        "exists before anyone can be bound to it."
    ),
    "user_account": (
        "A user exists before joining any organization (self-registration), "
        "so tenant_id is nullable and NULL rows are globally visible by "
        "design — that is how login finds an account at all."
    ),
    "auth_session": "Platform-level sessions carry no tenant; tenant sessions carry theirs.",
    "role": "System roles are global (tenant_id NULL); tenant roles are not.",
    "role_permission": "Inherits its role's scope — global for system roles, tenant-owned else.",
    "user_role": "A platform-admin grant has no tenant; a tenant grant does.",
    "config_entry": "Platform-scope rows are global; tenant-scope rows are not.",
    "audit_record": "Platform-level actions (registration, org creation) have no tenant.",
    "event_outbox": "Events raised before a tenant exists carry no tenant_id.",
    "consumer_execution": "Mirrors the tenancy of the event it records.",
    "dead_letter_queue": "Mirrors the tenancy of the event that died.",
    "notification": "A message about a platform-level event has no tenant.",
}


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


class RlsNotEnforceable(RuntimeError):
    """The connected role bypasses row-level security (VER-001)."""


async def assert_rls_is_enforceable(session: AsyncSession) -> None:
    """Refuse to serve if the database ignores our policies.

    **The most consequential thing execution found.** A PostgreSQL SUPERUSER —
    and any role with `BYPASSRLS` — ignores row-level security completely.
    Not "unless FORCE": `FORCE ROW LEVEL SECURITY` closes the loophole for the
    table OWNER, and does nothing about superusers.

    The production stack connected as `${POSTGRES_USER}`, which the official
    `postgres` image creates as a superuser. So every policy SEC-001, SEC-002
    and MT-001 built was **inert in production**: enabled, forced, visible in
    `pg_policies`, and enforcing nothing. The only isolation left was the
    application-level filter — which is precisely the dependency RLS was
    introduced to remove.

    Nothing would have failed. `verify-deployment.sh` checks that policies
    EXIST, which they did. The platform would have run for months looking
    correct.

    So this is a startup assertion rather than a documentation note: in
    `prod` and `staging` the process refuses to start, in the same spirit as
    refusing a development credential. A tenant boundary that is off is worse
    than one that was never claimed.
    """
    if not is_postgres() or not get_settings().rls_enabled:
        return
    row = (
        await session.execute(
            text(
                "SELECT current_user, rolsuper, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            )
        )
    ).first()
    if row is None:  # pragma: no cover - the role always exists
        return
    role, is_super, bypasses = row
    if not (is_super or bypasses):
        log.info("rls_enforceable", role=role)
        return

    reason = "SUPERUSER" if is_super else "BYPASSRLS"
    message = (
        f"the database role {role!r} is {reason}, so PostgreSQL ignores every "
        "row-level security policy on this platform. Tenant isolation would be "
        "application-level only. Connect as a role created with "
        "NOSUPERUSER NOBYPASSRLS — see DEPLOYMENT.md §Database roles."
    )
    if get_settings().env in ("prod", "staging"):
        log.error("rls_not_enforceable", role=role, reason=reason)
        raise RlsNotEnforceable(message)
    # Development and the verification pipeline still need to know.
    log.warning("rls_not_enforceable", role=role, reason=reason, detail=message)


async def bind_tenant(session: AsyncSession, tenant_id: uuid.UUID | None) -> None:
    """Bind the request's tenant to this transaction.

    `SET LOCAL` is transaction-scoped: when the transaction ends the setting
    is gone, so a pooled connection can never carry one request's tenant into
    the next request's query.
    """
    if not is_postgres() or not get_settings().rls_enabled:
        return
    # VER-001: `set_config(...)`, NOT `SET LOCAL ... = :param`.
    #
    # `SET` is utility syntax, not a query: PostgreSQL will not accept a bind
    # parameter in it, and asyncpg sends everything as a prepared statement.
    # `SET LOCAL lacteva.tenant_id = $1` is therefore a SYNTAX ERROR, raised
    # on every single request — the binding runs in `get_session` before any
    # handler.
    #
    # This code was written in SEC-001 and never executed until VER-001 stood
    # a real PostgreSQL up: SQLite short-circuits `is_postgres()` on the line
    # above, so the whole function was dead in the test suite. The platform
    # was completely non-functional on its production engine.
    #
    # `set_config(name, value, is_local)` is an ordinary function, so it takes
    # parameters, and `is_local = true` gives exactly `SET LOCAL` semantics —
    # transaction-scoped, so a pooled connection cannot carry one request's
    # tenant into the next.
    await session.execute(
        text("SELECT set_config(:name, :value, true)"),
        {"name": TENANT_SETTING, "value": str(tenant_id) if tenant_id else ""},
    )
    await session.execute(text("SELECT set_config(:name, 'off', true)"), {"name": BYPASS_SETTING})


async def rebind_tenant(session: AsyncSession, tenant_id: uuid.UUID | None) -> None:
    """Re-bind mid-request, once the authoritative tenant is known.

    SEC-002: `bind_tenant` runs when the session is created, which is BEFORE
    the request has proven anything. Several flows learn their tenant later —
    a token is decoded, an invitation is looked up, a login names a tenant in
    its body — and every one of them then reads or writes tenant-owned rows.
    Changing `set_current_tenant()` alone is not enough and was the shape of
    a real defect: the context variable moved, the database binding did not,
    and the row was invisible to the very request that owned it.

    Always pair a mid-request `set_current_tenant()` with this call.
    """
    from platform_core.core.tenancy import set_current_tenant

    set_current_tenant(tenant_id)
    await bind_tenant(session, tenant_id)


async def bind_platform_context(session: AsyncSession, *, reason: str) -> None:
    """Grant this transaction cross-tenant visibility.

    Used only by machinery that is definitionally multi-tenant — the relay
    dispatcher, consumers, projection rebuilds, and platform-admin operations.
    The reason is logged so an auditor can see every place the guarantee was
    deliberately stepped around.
    """
    if not is_postgres() or not get_settings().rls_enabled:
        return
    await session.execute(text("SELECT set_config(:name, 'on', true)"), {"name": BYPASS_SETTING})
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


def identity_policy_statements(table: str, *, column: str = "id") -> list[str]:
    """Protection for a table that IS the tenant (SEC-002).

    `organization` has no `tenant_id` because it is what every `tenant_id`
    refers to. Isolating it therefore compares its own primary key against
    the bound tenant: a bound session sees exactly its own organization and
    no other, which is the same guarantee the tenant policy gives — reached
    through a different column.

    There is no `tenant_id IS NULL` escape here, and there must not be: the
    identity column is NOT NULL, so an unbound session sees nothing at all.
    That is correct. Creating an organization, and listing organizations as
    a platform administrator, are cross-tenant acts and run under the audited
    bypass rather than through a hole in the policy.
    """
    predicate = (
        f"current_setting('{BYPASS_SETTING}', true) = 'on' "
        f"OR {column}::text = current_setting('{TENANT_SETTING}', true)"
    )
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"""
        CREATE POLICY {table}_tenant_isolation ON {table}
        USING ({predicate})
        WITH CHECK ({predicate})
        """,
    ]


def unclassified_tables() -> tuple[str, ...]:
    """Tables that declare no isolation strategy at all — always empty.

    SEC-002's whole premise is that "every table has an explicit isolation
    strategy". This is the function that makes the premise checkable rather
    than aspirational; a test asserts it returns nothing.
    """
    from platform_core.core.db import Base

    declared = set(tenant_tables()) | set(PLATFORM_GLOBAL) | set(MIXED)
    return tuple(sorted(name for name in Base.metadata.tables if name not in declared))


def drop_statements(table: str) -> list[str]:
    """The rollback path (see SECURITY.md): policies come off cleanly."""
    return [
        f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
    ]


# --- Sessions for work that is definitionally cross-tenant (MT-001) --------
#
# THE DEFECT THIS EXISTS TO FIX.
#
# SEC-001 wrote that "the relay dispatcher, consumers, and projection rebuilds
# set `lacteva.bypass_rls`". Nothing did. Those loops build their sessions from
# `get_session_factory()` directly, which binds neither a tenant nor a bypass —
# so on PostgreSQL the policy evaluated:
#
#   bypass          -> current_setting(...) is NULL, not 'on'   -> false
#   tenant_id IS NULL -> true only for platform-global rows
#   tenant_id = ''    -> NULL                                    -> not true
#
# Meaning the entire asynchronous half of the platform could see only
# platform-global rows. The relay would find no tenant events to dispatch,
# consumers would find nothing to consume, and every projection write would be
# refused by WITH CHECK.
#
# Nothing would have errored. Requests would succeed, milk would be recorded,
# and no receipt would be generated, no notification sent, no projection
# updated — the failure shape this platform's own docs call the most dangerous
# it has, because it looks healthy.
#
# SQLite cannot execute a policy, so no test caught it. This is the fourth
# defect of that exact shape.
#
# The fix is a factory rather than a call at each of ~25 sites: a component
# built with a platform factory CANNOT forget, and a component built with the
# ordinary factory is visibly request-scoped.


async def _relax_statement_timeout(session: AsyncSession) -> None:
    """Give cross-tenant work the time its job actually takes (ARCH-001).

    The engine sets a 30-second `statement_timeout` for the request path,
    which is right: no HTTP request should hold a snapshot longer than that.
    But the same engine serves a projection rebuild replaying a million
    events, a backup reading every row, and an integrity check rebuilding
    every projection — all of which legitimately exceed it, and all of which
    would start failing the moment the pool configuration landed.

    Raised, never removed: "unbounded" is the condition that made a timeout
    necessary in the first place.
    """
    if not is_postgres():
        return
    timeout_ms = int(get_settings().db_background_statement_timeout_ms)
    # Same rule as above: `SET` takes no parameters, so this goes through
    # `set_config`. The value is coerced to int rather than interpolated raw.
    await session.execute(
        text("SELECT set_config('statement_timeout', :value, true)"),
        {"value": str(timeout_ms)},
    )


@asynccontextmanager
async def platform_session(reason: str) -> AsyncIterator[AsyncSession]:
    """One session, bound to the platform context, for cross-tenant work."""
    from platform_core.core.db import get_session_factory

    async with get_session_factory()() as session:
        await bind_platform_context(session, reason=reason)
        await _relax_statement_timeout(session)
        yield session


class PlatformSessionFactory:
    """A session factory whose sessions are already bound to the platform.

    Drop-in for `async_sessionmaker`: every `async with factory()` yields a
    session that may cross tenants, and says in the log why it was allowed to.

    Give this to the relay, the consumer runner, the projection rebuilder, the
    backup engine and the health probes — the components whose whole job spans
    tenants. Give the ORDINARY factory to anything request-scoped, so the
    difference is visible at the construction site rather than buried in a
    method.
    """

    def __init__(self, factory: async_sessionmaker[AsyncSession], reason: str) -> None:
        self._factory = factory
        self._reason = reason

    def __call__(self) -> "AbstractAsyncContextManager[AsyncSession]":
        return self._bound()

    @asynccontextmanager
    async def _bound(self) -> AsyncIterator[AsyncSession]:
        async with self._factory() as session:
            await bind_platform_context(session, reason=self._reason)
            await _relax_statement_timeout(session)
            yield session

    def __repr__(self) -> str:  # pragma: no cover - diagnostics
        return f"PlatformSessionFactory(reason={self._reason!r})"


def platform_factory(reason: str) -> PlatformSessionFactory:
    """`PlatformSessionFactory` over the process's session factory."""
    from platform_core.core.db import get_session_factory

    return PlatformSessionFactory(get_session_factory(), reason)
