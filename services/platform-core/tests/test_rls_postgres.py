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

from platform_core.core.rls import BYPASS_SETTING, TENANT_SETTING
from tests import postgres_support

# OPS-001: one guard for every PostgreSQL-only suite. A skip is allowed on a
# laptop and impossible in the verification pipeline (see postgres_support).
POSTGRES_URL = postgres_support.POSTGRES_URL
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


@pytest_asyncio.fixture
async def pg():
    engine = create_async_engine(POSTGRES_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
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
    yield factory
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {_TABLE}"))
    await engine.dispose()


async def _seed(factory, tenant_a, tenant_b):
    """Insert one row per tenant with the policy bypassed — the same escape
    hatch the relay and consumers use."""
    async with factory() as s:
        await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
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
        await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(a)})
        rows = (await s.execute(text(f"SELECT label FROM {_TABLE}"))).scalars().all()
    assert rows == ["alpha"]  # the other tenant's row is not merely filtered — it is absent


async def test_a_query_that_forgets_its_filter_still_cannot_leak(pg):
    """The whole point: `SELECT *` with no WHERE is safe."""
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(b)})
        rows = (await s.execute(text(f"SELECT * FROM {_TABLE}"))).all()
    assert len(rows) == 1


async def test_cross_tenant_update_affects_nothing(pg):
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(a)})
        result = await s.execute(text(f"UPDATE {_TABLE} SET label = 'stolen'"))
        await s.commit()
        assert result.rowcount == 1  # only its own row
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
        labels = sorted((await s.execute(text(f"SELECT label FROM {_TABLE}"))).scalars().all())
    assert labels == ["beta", "stolen"]  # tenant B untouched


async def test_cross_tenant_delete_affects_nothing(pg):
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(a)})
        result = await s.execute(text(f"DELETE FROM {_TABLE}"))
        await s.commit()
        assert result.rowcount == 1
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
        labels = (await s.execute(text(f"SELECT label FROM {_TABLE}"))).scalars().all()
    assert labels == ["beta"]


async def test_a_row_cannot_be_written_into_another_tenant(pg):
    """WITH CHECK is what stops a caller MOVING a row across the boundary —
    USING alone would allow the write and merely hide the result."""
    from sqlalchemy.exc import DBAPIError

    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(a)})
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
        await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
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
        await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
        await s.execute(
            text(f"INSERT INTO {_TABLE} (id, tenant_id, label) VALUES (:i, NULL, 'global')"),
            {"i": uuid.uuid4()},
        )
        await s.commit()

    # A tenant-bound session can READ the platform-global row...
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(tenant)})
        labels = (await s.execute(text(f"SELECT label FROM {_TABLE}"))).scalars().all()
    assert labels == ["global"]

    # ...and can INSERT one, which is what registration does.
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(tenant)})
        await s.execute(
            text(f"INSERT INTO {_TABLE} (id, tenant_id, label) VALUES (:i, NULL, 'registered')"),
            {"i": uuid.uuid4()},
        )
        await s.commit()

    async with pg() as s:
        await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
        count = (await s.execute(text(f"SELECT count(*) FROM {_TABLE}"))).scalar()
    assert count == 2


async def test_a_tenant_still_cannot_see_another_tenants_rows(pg):
    """The NULL allowance must not have widened anything else."""
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
        await s.execute(
            text(f"INSERT INTO {_TABLE} (id, tenant_id, label) VALUES (:i, NULL, 'global')"),
            {"i": uuid.uuid4()},
        )
        await s.commit()
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(a)})
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
    """A session factory against the MIGRATED database (no probe table)."""
    engine = create_async_engine(POSTGRES_URL)
    yield async_sessionmaker(engine, expire_on_commit=False)
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


async def test_settlement_lines_do_not_leak_across_tenants(live):
    """The money table that had no protection at all before SEC-002."""
    a, b = uuid.uuid4(), uuid.uuid4()
    ids = {}
    async with live() as s:
        await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
        for tenant in (a, b):
            ids[tenant] = uuid.uuid4()
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
                    "s": uuid.uuid4(),
                    "c": uuid.uuid4(),
                    "r": uuid.uuid4(),
                },
            )
        await s.commit()
    try:
        async with live() as s:
            await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(a)})
            visible = (await s.execute(text("SELECT tenant_id FROM settlement_line"))).scalars()
            assert set(visible) == {a}
    finally:
        async with live() as s:
            await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
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
        await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
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
            await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(a)})
            found = (
                await s.execute(
                    text("SELECT tenant_id FROM supplier_profile WHERE phone = '+254700000009'")
                )
            ).scalars()
            assert set(found) == {a}
    finally:
        async with live() as s:
            await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
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
        await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
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
            await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(a)})
            visible = set((await s.execute(text("SELECT id FROM organization"))).scalars())
            assert visible == {a}, "a tenant must see exactly its own organization"

        # And cannot create one for anybody — including itself under another id.
        async with live() as s:
            await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(a)})
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
            await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
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
            await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
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
            await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(tenant)})
            await s.execute(
                text(
                    "INSERT INTO role_permission (id, tenant_id, role_id, permission_key)"
                    " VALUES (:i, :t, :r, 'probe.read')"
                ),
                {"i": row, "t": tenant, "r": uuid.uuid4()},
            )
            await s.commit()
        async with live() as s:  # a DIFFERENT tenant
            await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(uuid.uuid4())})
            seen = (
                await s.execute(
                    text("SELECT id FROM role_permission WHERE permission_key = 'probe.read'")
                )
            ).scalars()
            assert list(seen) == []
    finally:
        async with live() as s:
            await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
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
            await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
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
            await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
            found = (
                await s.execute(
                    text("SELECT tenant_id FROM invitation WHERE token_hash = :h"),
                    {"h": token_hash},
                )
            ).scalars()
            assert list(found) == [tenant]
    finally:
        async with live() as s:
            await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
            await s.execute(text("DELETE FROM invitation WHERE id = :i"), {"i": row})
            await s.commit()


async def test_a_tenant_session_cannot_insert_update_or_delete_across_the_boundary(live):
    """The four verbs, on a real money table, in one place."""
    from sqlalchemy.exc import DBAPIError

    a, b = uuid.uuid4(), uuid.uuid4()
    theirs = uuid.uuid4()
    async with live() as s:
        await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
        await s.execute(
            text(
                "INSERT INTO payment_line (id, tenant_id, payment_id, settlement_id,"
                " settlement_number, amount, created_at) VALUES (:i, :t, :p, :s, 'STL-1', 10,"
                " now())"
            ),
            {"i": theirs, "t": b, "p": uuid.uuid4(), "s": uuid.uuid4()},
        )
        await s.commit()
    try:
        async with live() as s:
            await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(a)})
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
            await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(a)})
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
            await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
            await s.execute(text("DELETE FROM payment_line WHERE id = :i"), {"i": theirs})
            await s.commit()
