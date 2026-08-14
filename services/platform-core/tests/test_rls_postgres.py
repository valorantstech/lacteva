"""Row Level Security — policy EXECUTION (SEC-001).

These tests need a real PostgreSQL: SQLite has no row-level security, so the
main suite can only prove the application-level isolation and that the policy
set covers every tenant-owned table. This module proves the database itself
refuses cross-tenant access — the guarantee that makes application filters
defense-in-depth rather than the only defense.

It SKIPS when no PostgreSQL is reachable, and the CI workflow provides one so
it is never skipped where it matters. A skip in local development is expected;
a skip in CI is a configuration failure.

Point it at an instance with:
    LACTEVA_TEST_POSTGRES_URL=postgresql+asyncpg://user:pass@localhost:5432/db
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from platform_core.core.rls import (
    BYPASS_SETTING,
    TENANT_SETTING,
    bind_platform_context,
    bind_tenant,
)
from tests import postgres_support

# OPS-001: one guard for every PostgreSQL-only suite. A skip is allowed on a
# laptop and impossible in the verification pipeline (see postgres_support).
POSTGRES_URL = postgres_support.POSTGRES_URL
# DDL only — see postgres_support.ADMIN_URL. The tests themselves always
# run over POSTGRES_URL, which is the unprivileged application role.
ADMIN_URL = postgres_support.ADMIN_URL
pytestmark = postgres_support.requires_postgres

# A minimal stand-in for a tenant-owned table: the policy under test is
# identical for every real one, and this keeps the fixture independent of any
# module's schema.
_TABLE = "rls_probe"

_PREDICATE = (
    f"current_setting('{BYPASS_SETTING}', true) = 'on' "
    "OR tenant_id IS NULL "
    f"OR tenant_id::text = current_setting('{TENANT_SETTING}', true)"
)


@pytest.fixture(autouse=True)
def _settings_point_at_postgres(monkeypatch):
    """Make `is_postgres()` true for the code under test.

    VER-001. Every binding below now goes through the PRODUCTION
    `bind_tenant` / `bind_platform_context` instead of re-implementing their
    SQL — which is the whole reason this suite passed for two work orders
    while the real function raised a syntax error on every call.

    `is_postgres()` reads `settings.database_url`, and that is SQLite in the
    test process, so without this the production functions would return early
    and prove nothing at all.
    """
    from platform_core.core.config import get_settings

    monkeypatch.setattr(get_settings(), "database_url", POSTGRES_URL)
    monkeypatch.setattr(get_settings(), "rls_enabled", True)


@pytest_asyncio.fixture
async def pg():
    # VER-001: two engines. `admin` owns the probe table; `engine` is the
    # unprivileged application role the assertions run as. They were one
    # engine, which meant the tests ran as a role that could have turned the
    # policy off — and, in the proof pipeline, as a superuser that ignored it.
    admin = create_async_engine(ADMIN_URL)
    engine = create_async_engine(POSTGRES_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with admin.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {_TABLE}"))
        await conn.execute(
            text(f"CREATE TABLE {_TABLE} (id uuid PRIMARY KEY, tenant_id uuid, label text)")
        )
        await conn.execute(text(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY"))
        # FORCE: without it the table owner — which is who the application
        # connects as — silently bypasses its own policy.
        await conn.execute(text(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY"))
        await conn.execute(
            text(
                f"CREATE POLICY {_TABLE}_tenant_isolation ON {_TABLE} "
                f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
            )
        )
        # The application role owns nothing; grant it the DML the tests use.
        await conn.execute(text(f"GRANT ALL PRIVILEGES ON {_TABLE} TO PUBLIC"))
    yield factory
    async with admin.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {_TABLE}"))
    await engine.dispose()
    await admin.dispose()


async def _seed(factory, tenant_a, tenant_b):
    """Insert one row per tenant with the policy bypassed — the same escape
    hatch the relay and consumers use."""
    async with factory() as s:
        await bind_platform_context(s, reason="test")
        for tenant, label in ((tenant_a, "alpha"), (tenant_b, "beta")):
            await s.execute(
                text(f"INSERT INTO {_TABLE} (id, tenant_id, label) VALUES (:i, :t, :l)"),
                {"i": uuid.uuid4(), "t": tenant, "l": label},
            )
        await s.commit()


async def test_reads_are_confined_to_the_bound_tenant(pg):
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await bind_tenant(s, a)
        rows = (await s.execute(text(f"SELECT label FROM {_TABLE}"))).scalars().all()
    assert rows == ["alpha"]  # the other tenant's row is not merely filtered — it is absent


async def test_a_query_that_forgets_its_filter_still_cannot_leak(pg):
    """The whole point: `SELECT *` with no WHERE is safe."""
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await bind_tenant(s, b)
        rows = (await s.execute(text(f"SELECT * FROM {_TABLE}"))).all()
    assert len(rows) == 1


async def test_cross_tenant_update_affects_nothing(pg):
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await bind_tenant(s, a)
        result = await s.execute(text(f"UPDATE {_TABLE} SET label = 'stolen'"))
        await s.commit()
        assert result.rowcount == 1  # only its own row
    async with pg() as s:
        await bind_platform_context(s, reason="test")
        labels = sorted((await s.execute(text(f"SELECT label FROM {_TABLE}"))).scalars().all())
    assert labels == ["beta", "stolen"]  # tenant B untouched


async def test_cross_tenant_delete_affects_nothing(pg):
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await bind_tenant(s, a)
        result = await s.execute(text(f"DELETE FROM {_TABLE}"))
        await s.commit()
        assert result.rowcount == 1
    async with pg() as s:
        await bind_platform_context(s, reason="test")
        labels = (await s.execute(text(f"SELECT label FROM {_TABLE}"))).scalars().all()
    assert labels == ["beta"]


async def test_a_row_cannot_be_written_into_another_tenant(pg):
    """WITH CHECK is what stops a caller MOVING a row across the boundary —
    USING alone would allow the write and merely hide the result."""
    from sqlalchemy.exc import DBAPIError

    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await bind_tenant(s, a)
        with pytest.raises(DBAPIError):
            await s.execute(
                text(f"INSERT INTO {_TABLE} (id, tenant_id, label) VALUES (:i, :t, 'smuggled')"),
                {"i": uuid.uuid4(), "t": b},
            )


async def test_no_tenant_bound_means_no_rows(pg):
    """An unbound session is not a privileged session. Forgetting to bind
    must fail closed."""
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        rows = (await s.execute(text(f"SELECT * FROM {_TABLE}"))).all()
    assert rows == []


async def test_the_bypass_is_explicit_and_scoped_to_its_transaction(pg):
    """Platform machinery sees everything — but only inside the transaction
    that asked, so a pooled connection cannot carry the privilege onward."""
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await bind_platform_context(s, reason="test")
        assert len((await s.execute(text(f"SELECT * FROM {_TABLE}"))).all()) == 2
    # A fresh transaction on the same pool starts unprivileged again.
    async with pg() as s:
        assert (await s.execute(text(f"SELECT * FROM {_TABLE}"))).all() == []


async def test_the_platform_binding_helpers_drive_the_policy(pg):
    """`bind_tenant` / `bind_platform_context` are what the application calls;
    they must produce exactly the behaviour proven above."""
    from platform_core.core import rls
    from platform_core.core.config import get_settings

    settings = get_settings()
    original_url, original_rls = settings.database_url, settings.rls_enabled
    settings.database_url, settings.rls_enabled = POSTGRES_URL, True
    try:
        a, b = uuid.uuid4(), uuid.uuid4()
        await _seed(pg, a, b)
        async with pg() as s:
            await rls.bind_tenant(s, a)
            assert len((await s.execute(text(f"SELECT * FROM {_TABLE}"))).all()) == 1
        async with pg() as s:
            await rls.bind_platform_context(s, reason="test")
            assert len((await s.execute(text(f"SELECT * FROM {_TABLE}"))).all()) == 2
    finally:
        settings.database_url, settings.rls_enabled = original_url, original_rls


async def test_platform_global_rows_are_visible_to_everyone(pg):
    """Rows with `tenant_id IS NULL` belong to no tenant — a self-registered
    user, a seeded system role, a platform audit entry.

    `NULL = 'anything'` is NULL in SQL, and a policy predicate that is NULL is
    not true, so the original SEC-001 policy made these rows invisible AND
    un-insertable. With RLS on, registration itself failed. No SQLite test
    could catch it; this is the one that does.
    """
    tenant = uuid.uuid4()
    async with pg() as s:
        await bind_platform_context(s, reason="test")
        await s.execute(
            text(f"INSERT INTO {_TABLE} (id, tenant_id, label) VALUES (:i, NULL, 'global')"),
            {"i": uuid.uuid4()},
        )
        await s.commit()

    # A tenant-bound session can READ the platform-global row...
    async with pg() as s:
        await bind_tenant(s, tenant)
        labels = (await s.execute(text(f"SELECT label FROM {_TABLE}"))).scalars().all()
    assert labels == ["global"]

    # ...and can INSERT one, which is what registration does.
    async with pg() as s:
        await bind_tenant(s, tenant)
        await s.execute(
            text(f"INSERT INTO {_TABLE} (id, tenant_id, label) VALUES (:i, NULL, 'registered')"),
            {"i": uuid.uuid4()},
        )
        await s.commit()

    async with pg() as s:
        await bind_platform_context(s, reason="test")
        count = (await s.execute(text(f"SELECT count(*) FROM {_TABLE}"))).scalar()
    assert count == 2


async def test_a_tenant_still_cannot_see_another_tenants_rows(pg):
    """The NULL allowance must not have widened anything else."""
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await bind_platform_context(s, reason="test")
        await s.execute(
            text(f"INSERT INTO {_TABLE} (id, tenant_id, label) VALUES (:i, NULL, 'global')"),
            {"i": uuid.uuid4()},
        )
        await s.commit()
    async with pg() as s:
        await bind_tenant(s, a)
        labels = sorted((await s.execute(text(f"SELECT label FROM {_TABLE}"))).scalars().all())
    assert labels == ["alpha", "global"], "tenant B's row must remain invisible"


async def test_the_migration_protects_every_snapshotted_table(pg):
    """Run the real migration DDL and confirm PostgreSQL reports the policies
    as present and FORCED — a policy that exists but is not forced protects
    nothing from the application's own role."""
    from migrations.versions.a1c7f3b90e22_row_level_security import TENANT_TABLES

    async with pg() as s:
        rows = (
            (
                await s.execute(
                    text(
                        "SELECT relname FROM pg_class WHERE relrowsecurity AND relforcerowsecurity"
                    )
                )
            )
            .scalars()
            .all()
        )
    # The probe table is created with the same DDL the migration emits.
    assert _TABLE in rows
    assert TENANT_TABLES, "the migration must protect a non-empty set of tables"


# --------------------------------------------------------------------------
# SEC-002 — the REAL schema, not a probe table.
#
# Everything above proves the policy predicate behaves correctly on a table
# built for the test. That is necessary and not sufficient: it says nothing
# about whether the tables the platform actually stores money and PII in are
# covered. These tests run against the migrated database itself.
# --------------------------------------------------------------------------


@pytest_asyncio.fixture
async def live():
    """A session factory against the MIGRATED database (no probe table).

    VER-001: seeds the system-role catalog through the SAME call the
    application makes at startup. Two tests below assert the global catalog
    stays readable to an unbound session, and they used to read whatever the
    database happened to contain — passing only if some earlier run had left
    rows behind, and failing on a freshly migrated database. A test whose
    result depends on execution order proves nothing.
    """
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.authz.service import AuthzService

    engine = create_async_engine(POSTGRES_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await bind_platform_context(s, reason="seed the system-role catalog")
        await AuthzService(s).ensure_system_roles()
        await s.commit()
    yield factory
    await engine.dispose()


async def test_every_tenant_owned_table_is_enabled_and_forced(live):
    """`ENABLE` without `FORCE` protects nothing here — the application
    connects as the table owner, which bypasses its own policies."""
    from platform_core.core.model_registry import import_all_models
    from platform_core.core.rls import tenant_tables

    import_all_models()
    async with live() as s:
        rows = dict(
            (
                await s.execute(
                    text(
                        "SELECT relname, relrowsecurity AND relforcerowsecurity "
                        "FROM pg_class WHERE relkind = 'r'"
                    )
                )
            ).all()
        )
    missing = [t for t in tenant_tables() if not rows.get(t)]
    assert missing == [], f"tenant-owned tables without enabled+forced RLS: {missing}"


async def test_every_tenant_owned_table_has_using_and_with_check(live):
    """A policy with only `USING` hides other tenants' rows but still lets a
    caller WRITE one — the row simply disappears afterwards."""
    from platform_core.core.model_registry import import_all_models
    from platform_core.core.rls import tenant_tables

    import_all_models()
    async with live() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT tablename, policyname, qual IS NOT NULL, with_check IS NOT NULL "
                    "FROM pg_policies WHERE schemaname = 'public'"
                )
            )
        ).all()
    by_table = {r[0]: r for r in rows}
    for table in tenant_tables():
        assert table in by_table, f"{table} has no policy at all"
        _, name, has_using, has_check = by_table[table]
        assert name == f"{table}_tenant_isolation", f"{table} policy is named {name}"
        assert has_using, f"{table} policy has no USING clause"
        assert has_check, f"{table} policy has no WITH CHECK clause"


async def test_platform_global_tables_are_deliberately_unprotected(live):
    """Category B is a decision, not an omission — so it is asserted too.
    If one of these ever gains a policy, the flow that reads it breaks and
    this test says which table and why it was left alone."""
    from platform_core.core.rls import PLATFORM_GLOBAL

    async with live() as s:
        protected = set(
            (await s.execute(text("SELECT relname FROM pg_class WHERE relrowsecurity"))).scalars()
        )
    unexpected = sorted(set(PLATFORM_GLOBAL) & protected)
    assert unexpected == [], (
        f"platform-global tables must NOT have RLS: {unexpected}. "
        f"Reasons on record: { {t: PLATFORM_GLOBAL[t] for t in unexpected} }"
    )


async def test_no_table_is_left_without_an_isolation_strategy(live):
    """SEC-002's premise, made checkable."""
    from platform_core.core.model_registry import import_all_models
    from platform_core.core.rls import unclassified_tables

    import_all_models()
    assert unclassified_tables() == ()


# --------------------------------------------------------------------------
# VER-001 — parent rows for the money tables.
#
# The tests below insert into `settlement_line` and `payment_line`, both of
# which carry a foreign key. They used to point at a freshly generated UUID
# that matched nothing, and passed anyway: SQLite does not enforce foreign
# keys unless `PRAGMA foreign_keys=ON`, and the suite never set it. On
# PostgreSQL the insert is simply rejected.
#
# These helpers are deliberately minimal — the isolation guarantee is what is
# under test, not settlement arithmetic.
# --------------------------------------------------------------------------


async def _parent_settlement(session, tenant, settlement_id):
    await session.execute(
        text(
            "INSERT INTO settlement (id, tenant_id, supplier_id, center_id,"
            " settlement_number, period_from, period_to, currency, gross_amount,"
            " adjustments_amount, net_amount, status, created_at, updated_at)"
            " VALUES (:i, :t, :sup, :c, :n, CURRENT_DATE, CURRENT_DATE, 'EUR',"
            " 1, 0, 1, 'draft', now(), now())"
        ),
        {
            "i": settlement_id,
            "t": tenant,
            "sup": uuid.uuid4(),
            "c": uuid.uuid4(),
            "n": f"STL-{settlement_id.hex[:8]}",
        },
    )


async def _parent_payment(session, tenant, payment_id):
    await session.execute(
        text(
            "INSERT INTO payment (id, tenant_id, supplier_id, payment_number, currency,"
            " method, amount, method_details, status, attempt_count, created_at,"
            " updated_at) VALUES (:i, :t, :sup, :n, 'EUR', 'bank_transfer', 10,"
            " '{}', 'pending', 0, now(), now())"
        ),
        {"i": payment_id, "t": tenant, "sup": uuid.uuid4(), "n": f"PAY-{payment_id.hex[:8]}"},
    )


async def test_settlement_lines_do_not_leak_across_tenants(live):
    """The money table that had no protection at all before SEC-002."""
    a, b = uuid.uuid4(), uuid.uuid4()
    ids = {}
    parents = {}
    async with live() as s:
        await bind_platform_context(s, reason="test")
        for tenant in (a, b):
            ids[tenant] = uuid.uuid4()
            parents[tenant] = uuid.uuid4()
            # VER-001: the parent must exist. This used to insert a line
            # against a random settlement_id — invisible on SQLite, which does
            # not enforce foreign keys unless asked to.
            await _parent_settlement(s, tenant, parents[tenant])
            await s.execute(
                text(
                    "INSERT INTO settlement_line (id, tenant_id, settlement_id, calculation_id,"
                    " transaction_date, quantity, quantity_unit, unit_price, gross_amount,"
                    " trace_reference, created_at) VALUES (:i, :t, :s, :c, CURRENT_DATE,"
                    " 1, 'kg', 1, 1, :r, now())"
                ),
                {
                    "i": ids[tenant],
                    "t": tenant,
                    "s": parents[tenant],
                    "c": uuid.uuid4(),
                    "r": uuid.uuid4(),
                },
            )
        await s.commit()
    try:
        async with live() as s:
            await bind_tenant(s, a)
            visible = (await s.execute(text("SELECT tenant_id FROM settlement_line"))).scalars()
            assert set(visible) == {a}
    finally:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(
                text("DELETE FROM settlement_line WHERE id = ANY(:ids)"),
                {"ids": list(ids.values())},
            )
            await s.commit()


async def test_supplier_pii_does_not_leak_across_tenants(live):
    """`supplier_profile` holds names, phones and national IDs, and a lookup
    by phone is exactly the query a support feature would write."""
    a, b = uuid.uuid4(), uuid.uuid4()
    made = []
    async with live() as s:
        await bind_platform_context(s, reason="test")
        for tenant in (a, b):
            row = uuid.uuid4()
            made.append(row)
            await s.execute(
                text(
                    "INSERT INTO supplier_profile (id, tenant_id, supplier_id, full_name, phone,"
                    " national_id, village, locale, extra) VALUES (:i, :t, :s, 'Amina',"
                    " '+254700000009', 'NID', 'v', 'en', '{}')"
                ),
                {"i": row, "t": tenant, "s": uuid.uuid4()},
            )
        await s.commit()
    try:
        async with live() as s:
            await bind_tenant(s, a)
            found = (
                await s.execute(
                    text("SELECT tenant_id FROM supplier_profile WHERE phone = '+254700000009'")
                )
            ).scalars()
            assert set(found) == {a}
    finally:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(
                text("DELETE FROM supplier_profile WHERE id = ANY(:ids)"), {"ids": made}
            )
            await s.commit()


async def test_a_tenant_sees_only_its_own_organization(live):
    """`organization` is isolated by IDENTITY, not by a tenant_id column —
    it IS the tenant. Before SEC-002 it had no policy, so any bound session
    could enumerate the platform's entire customer list."""
    from sqlalchemy.exc import DBAPIError

    a, b = uuid.uuid4(), uuid.uuid4()
    async with live() as s:
        await bind_platform_context(s, reason="test")
        for org, slug in ((a, f"alpha-{a.hex[:8]}"), (b, f"beta-{b.hex[:8]}")):
            await s.execute(
                text(
                    "INSERT INTO organization (id, name, slug, country_code, org_type, status,"
                    " default_locale, created_at) VALUES (:i, 'X', :s, 'KE', 'cooperative',"
                    " 'active', 'en', now())"
                ),
                {"i": org, "s": slug},
            )
        await s.commit()
    try:
        async with live() as s:
            await bind_tenant(s, a)
            visible = set((await s.execute(text("SELECT id FROM organization"))).scalars())
            assert visible == {a}, "a tenant must see exactly its own organization"

        # And cannot create one for anybody — including itself under another id.
        async with live() as s:
            await bind_tenant(s, a)
            with pytest.raises(DBAPIError):
                await s.execute(
                    text(
                        "INSERT INTO organization (id, name, slug, country_code, org_type,"
                        " status, default_locale, created_at) VALUES (:i, 'Y', :s, 'KE',"
                        " 'cooperative', 'active', 'en', now())"
                    ),
                    {"i": uuid.uuid4(), "s": f"sneak-{uuid.uuid4().hex[:8]}"},
                )
    finally:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(text("DELETE FROM organization WHERE id = ANY(:ids)"), {"ids": [a, b]})
            await s.commit()


async def test_an_unbound_session_sees_no_organization(live):
    """Anonymous callers exist — registration, password reset, login. None of
    them may enumerate tenants."""
    async with live() as s:
        rows = (await s.execute(text("SELECT id FROM organization"))).all()
    assert rows == []


async def test_registration_can_still_create_a_tenantless_user(live):
    """The bootstrap flow: someone self-registers before belonging anywhere.
    `user_account.tenant_id` is NULL and the row must be both insertable and
    readable by an unbound session, or nobody can ever sign up."""
    made = uuid.uuid4()
    email = f"bootstrap-{made.hex[:8]}@example.test"
    try:
        async with live() as s:  # no tenant bound — an anonymous request
            await s.execute(
                text(
                    "INSERT INTO user_account (id, tenant_id, email, password_hash, full_name,"
                    " locale, is_active, created_at) VALUES (:i, NULL, :e, 'x', 'Boot', 'en',"
                    " true, now())"
                ),
                {"i": made, "e": email},
            )
            await s.commit()
        async with live() as s:
            found = (
                await s.execute(text("SELECT id FROM user_account WHERE email = :e"), {"e": email})
            ).scalars()
            assert list(found) == [made], "login could not find a self-registered account"
    finally:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(text("DELETE FROM user_account WHERE id = :i"), {"i": made})
            await s.commit()


async def test_the_system_role_catalog_stays_readable_to_everyone(live):
    """System roles carry `tenant_id IS NULL` and are a shared catalog. If
    they became invisible, every permission check would fail closed and the
    platform would be unusable rather than merely unsafe."""
    async with live() as s:  # unbound
        count = (
            await s.execute(text("SELECT count(*) FROM role WHERE tenant_id IS NULL"))
        ).scalar()
    assert count and count > 0, "the global role catalog is not visible to an unbound session"


async def test_role_permissions_follow_their_role(live):
    """`role_permission` is Category C: global for system roles, tenant-owned
    for tenant roles. Both halves must work."""
    async with live() as s:
        globals_visible = (
            await s.execute(text("SELECT count(*) FROM role_permission WHERE tenant_id IS NULL"))
        ).scalar()
    assert globals_visible and globals_visible > 0

    tenant = uuid.uuid4()
    row = uuid.uuid4()
    try:
        async with live() as s:
            await bind_tenant(s, tenant)
            await s.execute(
                text(
                    "INSERT INTO role_permission (id, tenant_id, role_id, permission_key)"
                    " VALUES (:i, :t, :r, 'probe.read')"
                ),
                {"i": row, "t": tenant, "r": uuid.uuid4()},
            )
            await s.commit()
        async with live() as s:  # a DIFFERENT tenant
            await bind_tenant(s, uuid.uuid4())
            seen = (
                await s.execute(
                    text("SELECT id FROM role_permission WHERE permission_key = 'probe.read'")
                )
            ).scalars()
            assert list(seen) == []
    finally:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(text("DELETE FROM role_permission WHERE id = :i"), {"i": row})
            await s.commit()


async def test_an_invitation_is_invisible_until_its_tenant_is_bound(live):
    """Invitation acceptance is anonymous, and `invitation` is tenant-owned —
    which is why the accept flow takes an audited bypass to resolve the token,
    then binds immediately. This test pins BOTH halves: invisible unbound,
    visible once bound."""
    tenant = uuid.uuid4()
    row = uuid.uuid4()
    token_hash = uuid.uuid4().hex + uuid.uuid4().hex
    try:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(
                text(
                    "INSERT INTO invitation (id, tenant_id, email, role_name, token_hash,"
                    " invited_by, created_at, expires_at) VALUES (:i, :t, 'x@example.test',"
                    " 'tenant-admin', :h, :u, now(), now() + interval '7 days')"
                ),
                {"i": row, "t": tenant, "h": token_hash, "u": uuid.uuid4()},
            )
            await s.commit()
        async with live() as s:  # anonymous — cannot see it
            found = (
                await s.execute(
                    text("SELECT id FROM invitation WHERE token_hash = :h"), {"h": token_hash}
                )
            ).all()
            assert found == []
        async with live() as s:  # the accept flow's bypass
            await bind_platform_context(s, reason="test")
            found = (
                await s.execute(
                    text("SELECT tenant_id FROM invitation WHERE token_hash = :h"),
                    {"h": token_hash},
                )
            ).scalars()
            assert list(found) == [tenant]
    finally:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(text("DELETE FROM invitation WHERE id = :i"), {"i": row})
            await s.commit()


async def test_a_tenant_session_cannot_insert_update_or_delete_across_the_boundary(live):
    """The four verbs, on a real money table, in one place."""
    from sqlalchemy.exc import DBAPIError

    a, b = uuid.uuid4(), uuid.uuid4()
    theirs = uuid.uuid4()
    parent = uuid.uuid4()
    async with live() as s:
        await bind_platform_context(s, reason="test")
        await _parent_payment(s, b, parent)
        await s.execute(
            text(
                "INSERT INTO payment_line (id, tenant_id, payment_id, settlement_id,"
                " settlement_number, amount, created_at) VALUES (:i, :t, :p, :s, 'STL-1', 10,"
                " now())"
            ),
            {"i": theirs, "t": b, "p": parent, "s": uuid.uuid4()},
        )
        await s.commit()
    try:
        async with live() as s:
            await bind_tenant(s, a)
            # read
            assert (await s.execute(text("SELECT * FROM payment_line"))).all() == []
            # update
            r = await s.execute(text("UPDATE payment_line SET amount = 0"))
            assert r.rowcount == 0
            # delete
            r = await s.execute(text("DELETE FROM payment_line"))
            assert r.rowcount == 0
            await s.commit()
        async with live() as s:
            await bind_tenant(s, a)
            with pytest.raises(DBAPIError):  # insert into another tenant
                await s.execute(
                    text(
                        "INSERT INTO payment_line (id, tenant_id, payment_id, settlement_id,"
                        " settlement_number, amount, created_at) VALUES (:i, :t, :p, :s,"
                        " 'STL-2', 10, now())"
                    ),
                    {"i": uuid.uuid4(), "t": b, "p": uuid.uuid4(), "s": uuid.uuid4()},
                )
    finally:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(text("DELETE FROM payment_line WHERE id = :i"), {"i": theirs})
            await s.commit()


# --------------------------------------------------------------------------
# MT-001 — the bypass boundary, executed.
#
# The SQLite tests above assert that background components RECEIVE a
# platform-bound factory. Only a real engine can show what that binding buys,
# and what its absence costs — which is the whole defect: an unbound session
# sees no tenant rows at all, so the asynchronous half of the platform goes
# quiet without erroring.
# --------------------------------------------------------------------------


async def test_an_unbound_background_session_sees_no_tenant_events(live):
    """The defect MT-001 fixed, demonstrated rather than argued.

    The relay and the consumer runner used to build sessions this way. On
    PostgreSQL that means the outbox looks empty of tenant events, so nothing
    is dispatched and nothing is consumed — silently.
    """
    tenant = uuid.uuid4()
    row = uuid.uuid4()
    try:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(
                text(
                    "INSERT INTO event_outbox (id, tenant_id, event_name, payload, occurred_at,"
                    " version, status, attempts, next_attempt_at, created_at) VALUES (:i, :t,"
                    " 'mt001.probe.v1', '{}', now(), 1, 'pending', 0, now(), now())"
                ),
                {"i": row, "t": tenant},
            )
            await s.commit()

        async with live() as s:  # unbound — the old background behaviour
            found = (
                await s.execute(
                    text("SELECT id FROM event_outbox WHERE event_name = 'mt001.probe.v1'")
                )
            ).all()
        assert found == [], (
            "an unbound session should see no tenant-owned events — if it does, "
            "the policy is not being enforced"
        )

        async with live() as s:  # platform-bound — the fixed behaviour
            await bind_platform_context(s, reason="test")
            found = (
                await s.execute(
                    text("SELECT tenant_id FROM event_outbox WHERE event_name = 'mt001.probe.v1'")
                )
            ).scalars()
            assert list(found) == [tenant]
    finally:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(text("DELETE FROM event_outbox WHERE id = :i"), {"i": row})
            await s.commit()


async def test_a_projection_write_is_refused_without_the_platform_binding(live):
    """The other half: even if a consumer could read, it could not write.
    `WITH CHECK` refuses a row whose tenant does not match the binding, so a
    projection update from an unbound session is rejected outright."""
    from sqlalchemy.exc import DBAPIError

    tenant = uuid.uuid4()
    async with live() as s:  # unbound
        with pytest.raises(DBAPIError):
            await s.execute(
                text(
                    "INSERT INTO projection_daily_totals (id, tenant_id, day, transactions,"
                    " accepted, rejected, total_net_weight, payable_amount, updated_at)"
                    " VALUES (:i, :t, CURRENT_DATE, 1, 1, 0, 1.0, 1.0, now())"
                ),
                {"i": uuid.uuid4(), "t": tenant},
            )


async def test_the_platform_binding_lets_a_consumer_do_its_job(live):
    """And with the binding, the same write succeeds — for any tenant, which
    is exactly what a cross-tenant consumer needs."""
    tenant = uuid.uuid4()
    row = uuid.uuid4()
    try:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(
                text(
                    "INSERT INTO projection_daily_totals (id, tenant_id, day, transactions,"
                    " accepted, rejected, total_net_weight, payable_amount, updated_at)"
                    " VALUES (:i, :t, CURRENT_DATE, 1, 1, 0, 1.0, 1.0, now())"
                ),
                {"i": row, "t": tenant},
            )
            await s.commit()
        async with live() as s:
            await bind_tenant(s, tenant)
            seen = (
                await s.execute(
                    text("SELECT id FROM projection_daily_totals WHERE id = :i"), {"i": row}
                )
            ).scalars()
            assert list(seen) == [row], "the tenant cannot see its own projection row"
    finally:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(text("DELETE FROM projection_daily_totals WHERE id = :i"), {"i": row})
            await s.commit()


# --------------------------------------------------------------------------
# IDM-001 — the concurrency guarantee, on an engine that can stage the race.
#
# SQLite's StaticPool gives the test process one connection, so two
# "concurrent" requests share a transaction and the unique constraint never
# fires. Only a real engine can show that the second insert is refused.
# --------------------------------------------------------------------------


async def test_two_concurrent_reservations_of_one_key_cannot_both_win(live):
    """The check-then-act gap, closed by the database rather than by timing.

    Two sessions reserve the same `(tenant, key)` at once. One commits; the
    other must fail on the unique index — which is what makes the framework's
    duplicate protection a guarantee instead of a race that usually works.
    """
    from sqlalchemy.exc import IntegrityError

    tenant = uuid.uuid4()
    key = uuid.uuid4().hex

    async def reserve(session):
        await bind_platform_context(session, reason="test")
        await session.execute(
            text(
                "INSERT INTO idempotency_record (id, tenant_id, idempotency_key, fingerprint,"
                " method, path, status, created_at, expires_at) VALUES (:i, :t, :k, 'x', 'POST',"
                " '/v1/suppliers', 'in_progress', now(), now() + interval '1 day')"
            ),
            {"i": uuid.uuid4(), "t": tenant, "k": key},
        )

    try:
        async with live() as first, live() as second:
            await reserve(first)
            await first.commit()
            with pytest.raises(IntegrityError):
                await reserve(second)
                await second.commit()
    finally:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(
                text("DELETE FROM idempotency_record WHERE idempotency_key = :k"), {"k": key}
            )
            await s.commit()


async def test_the_same_key_in_two_tenants_is_two_reservations(live):
    """Keys are namespaced by tenant. A client library that derives keys from
    a request hash makes collisions across tenants certain, not unlikely."""
    key = uuid.uuid4().hex
    a, b = uuid.uuid4(), uuid.uuid4()
    try:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            for tenant in (a, b):
                await s.execute(
                    text(
                        "INSERT INTO idempotency_record (id, tenant_id, idempotency_key,"
                        " fingerprint, method, path, status, created_at, expires_at) VALUES"
                        " (:i, :t, :k, 'x', 'POST', '/v1/suppliers', 'in_progress', now(),"
                        " now() + interval '1 day')"
                    ),
                    {"i": uuid.uuid4(), "t": tenant, "k": key},
                )
            await s.commit()
            # VER-001: `set_config(..., is_local => true)` ends AT COMMIT, so
            # the bypass granted above is already gone here. Without re-binding
            # this counts as an unbound session and sees nothing — which read
            # as "the keys collided" rather than as the fixture error it was.
            await bind_platform_context(s, reason="test")
            count = await s.scalar(
                text("SELECT count(*) FROM idempotency_record WHERE idempotency_key = :k"),
                {"k": key},
            )
        assert count == 2, "the same key in two tenants collided"
    finally:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(
                text("DELETE FROM idempotency_record WHERE idempotency_key = :k"), {"k": key}
            )
            await s.commit()


async def test_idempotency_records_are_isolated_by_rls(live):
    """The table is tenant-owned, so one tenant must not see another's keys —
    which would leak what operations they perform and when."""
    key_a, key_b = uuid.uuid4().hex, uuid.uuid4().hex
    a, b = uuid.uuid4(), uuid.uuid4()
    try:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            for tenant, key in ((a, key_a), (b, key_b)):
                await s.execute(
                    text(
                        "INSERT INTO idempotency_record (id, tenant_id, idempotency_key,"
                        " fingerprint, method, path, status, created_at, expires_at) VALUES"
                        " (:i, :t, :k, 'x', 'POST', '/v1/x', 'completed', now(),"
                        " now() + interval '1 day')"
                    ),
                    {"i": uuid.uuid4(), "t": tenant, "k": key},
                )
            await s.commit()
        async with live() as s:
            await bind_tenant(s, a)
            visible = set(
                (
                    await s.execute(
                        text(
                            "SELECT idempotency_key FROM idempotency_record "
                            "WHERE idempotency_key IN (:x, :y)"
                        ),
                        {"x": key_a, "y": key_b},
                    )
                ).scalars()
            )
        assert visible == {key_a}, f"tenant A saw {visible}"
    finally:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(
                text("DELETE FROM idempotency_record WHERE idempotency_key IN (:x, :y)"),
                {"x": key_a, "y": key_b},
            )
            await s.commit()


# --------------------------------------------------------------------------
# ARCH-001 — the double-payment race, on an engine that can stage it.
#
# SQLite ignores FOR UPDATE and shares one connection, so the race cannot be
# staged there. This is the test that proves money is safe.
# --------------------------------------------------------------------------


async def test_two_concurrent_payments_cannot_both_claim_one_settlement(live):
    """The lock, doing its job.

    Two sessions read the same settlement to compute its outstanding balance.
    Without `FOR UPDATE` both proceed and the settlement is paid twice —
    partial payment is legitimate, so no constraint catches it. With the
    lock, the second waits for the first to commit and then sees the truth.
    """
    import asyncio

    tenant = uuid.uuid4()
    settlement_id = uuid.uuid4()
    try:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(
                text(
                    "INSERT INTO settlement (id, tenant_id, supplier_id, center_id,"
                    " settlement_number, period_from, period_to, currency, gross_amount,"
                    " adjustments_amount, net_amount, status, created_at, updated_at)"
                    " VALUES (:i, :t, :sup, :c, :n, CURRENT_DATE, CURRENT_DATE, 'KES',"
                    " 100, 0, 100, 'finalized', now(), now())"
                ),
                {
                    "i": settlement_id,
                    "t": tenant,
                    "sup": uuid.uuid4(),
                    "c": uuid.uuid4(),
                    "n": f"STL-{settlement_id.hex[:6]}",
                },
            )
            await s.commit()

        order: list[str] = []

        async def claim(label: str, hold: float) -> None:
            async with live() as session:
                await bind_platform_context(session, reason="test")
                await session.execute(
                    text("SELECT net_amount FROM settlement WHERE id = :i FOR UPDATE"),
                    {"i": settlement_id},
                )
                order.append(f"{label}:locked")
                await asyncio.sleep(hold)
                order.append(f"{label}:done")
                await session.commit()

        await asyncio.gather(claim("a", 0.3), claim("b", 0.0))

        # The second lock cannot be taken until the first transaction ends,
        # so the two never interleave — which is exactly what makes the
        # read-modify-write safe.
        assert order in (
            ["a:locked", "a:done", "b:locked", "b:done"],
            ["b:locked", "b:done", "a:locked", "a:done"],
        ), f"the settlement lock did not serialise: {order}"
    finally:
        async with live() as s:
            await bind_platform_context(s, reason="test")
            await s.execute(text("DELETE FROM settlement WHERE id = :i"), {"i": settlement_id})
            await s.commit()


async def test_the_request_path_carries_a_statement_timeout(live):
    """An unbounded query holds its snapshot and blocks VACUUM across the
    WHOLE database, turning one slow query into a cluster-wide problem."""
    from platform_core.core.config import get_settings
    from platform_core.core.db import get_engine, reset_engine

    settings = get_settings()
    original = settings.database_url
    settings.database_url = POSTGRES_URL
    await reset_engine()
    try:
        async with get_engine().connect() as conn:
            value = await conn.scalar(text("SHOW statement_timeout"))
        assert value not in ("0", "0ms"), "the request path has no statement timeout"
    finally:
        settings.database_url = original
        await reset_engine()


# --------------------------------------------------------------------------
# VER-001 — the binding statements themselves.
#
# Every test above uses `bind_tenant` / `bind_platform_context`, so a syntax
# error in either now fails the suite loudly. These three assert the contract
# directly, so the failure names the cause instead of showing up as thirty
# unrelated isolation failures.
# --------------------------------------------------------------------------


async def test_the_tenant_binding_is_valid_sql_and_takes_effect(live):
    """The regression test for the defect that motivated VER-001.

    `SET LOCAL lacteva.tenant_id = $1` is a PostgreSQL SYNTAX ERROR — `SET` is
    utility syntax and accepts no bind parameter, and asyncpg sends every
    statement as a prepared statement. This ran in `get_session`, before any
    handler, so the platform could not serve a single request on its
    production engine. It survived two work orders because SQLite made
    `is_postgres()` false and the function never executed.
    """
    tenant = uuid.uuid4()
    async with live() as s:
        await bind_tenant(s, tenant)
        assert (await s.scalar(text(f"SELECT current_setting('{TENANT_SETTING}', true)"))) == str(
            tenant
        )
        # bind_tenant must also CLEAR any bypass it inherited on a pooled
        # connection, or one platform task would leak into the next request.
        assert (await s.scalar(text(f"SELECT current_setting('{BYPASS_SETTING}', true)"))) == "off"


async def test_the_binding_does_not_survive_the_transaction(live):
    """Transaction scope is what makes a pooled connection safe."""
    tenant = uuid.uuid4()
    async with live() as s:
        await bind_tenant(s, tenant)
        await s.commit()
        after = await s.scalar(text(f"SELECT current_setting('{TENANT_SETTING}', true)"))
    assert after in (None, ""), (
        f"the tenant binding outlived its transaction ({after!r}) — the next request "
        "on this pooled connection would run as the previous request's tenant"
    )


async def test_a_role_that_bypasses_rls_is_refused(live):
    """VER-001's second finding: a SUPERUSER ignores every policy.

    The proof pipeline connects as a NOSUPERUSER NOBYPASSRLS role precisely so
    the isolation tests above mean something. Assert that here — if this
    database is ever pointed at a superuser, every other test in this file
    silently stops proving anything.
    """
    from platform_core.core.rls import assert_rls_is_enforceable

    async with live() as s:
        role, is_super, bypasses = (
            await s.execute(
                text(
                    "SELECT current_user, rolsuper, rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            )
        ).one()
        assert not is_super and not bypasses, (
            f"the verification pipeline is connected as {role!r}, which bypasses row-level "
            "security. Every isolation assertion in this file would pass vacuously."
        )
        await assert_rls_is_enforceable(s)  # must not raise


async def test_one_dairys_locale_is_invisible_to_another(live):
    """DEMO-013, and the reason this assertion lives HERE.

    An Indian dairy must not be able to read a Kenyan one's row — including
    the currency and timezone DEMO-013 added to it, which say what a
    competitor counts in and when their day closes.

    Nothing in the application enforces that. `organization` is isolated by
    IDENTITY (`id = current tenant`), so the only thing standing between one
    dairy and another's settings is the database policy. On SQLite there is no
    policy and the row comes back, which is exactly why the SQLite suite
    deliberately does not assert it: a guarantee tested only where it cannot
    fail is a guarantee nobody has tested.
    """
    india, kenya = uuid.uuid4(), uuid.uuid4()
    async with live() as s:
        await bind_platform_context(s, reason="test: seed two dairies")
        for tenant, name, currency, tz in (
            (india, "India Dairy", "INR", "Asia/Kolkata"),
            (kenya, "Kenya Dairy", "KES", "Africa/Nairobi"),
        ):
            await s.execute(
                text(
                    "INSERT INTO organization (id, name, slug, country_code, org_type, status, "
                    "default_locale, currency_code, timezone, supported_languages, created_at) "
                    "VALUES (:id, :name, :slug, :cc, 'cooperative', 'active', 'en', "
                    ":currency, :tz, :langs, now())"
                ),
                {
                    "id": tenant,
                    "name": name,
                    "slug": f"rls-{tenant}",
                    "cc": "IN" if currency == "INR" else "KE",
                    "currency": currency,
                    "tz": tz,
                    "langs": '["en"]',
                },
            )
        await s.commit()

    async with live() as s:
        await bind_tenant(s, india)
        mine = (await s.execute(text("SELECT currency_code, timezone FROM organization"))).all()
    assert mine == [("INR", "Asia/Kolkata")], (
        f"an Indian dairy saw {mine} — another tenant's currency and business clock"
    )

    async with live() as s:
        await bind_tenant(s, kenya)
        theirs = (await s.execute(text("SELECT currency_code, timezone FROM organization"))).all()
    assert theirs == [("KES", "Africa/Nairobi")]
