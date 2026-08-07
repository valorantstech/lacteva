"""Production readiness (ARCH-001).

An independent pass over the whole platform, reviewed as if the first dairy
goes live tomorrow. These tests pin the fixes that pass found — not style,
not coverage: the things that would have cost money or availability.
"""

import inspect

import pytest

# --- concurrency: the money path -------------------------------------------


def test_allocating_a_payment_locks_the_settlement():
    """The bug this test exists for.

    Allocating is a read-modify-write: read the live allocations, compute
    what is outstanding, refuse anything larger, insert the line. With no
    lock, two concurrent payments against one settlement both read the same
    sum, both see the full balance, both pass the check, and both insert —
    **the settlement is paid twice**, and nothing detects it, because partial
    payment is legitimate so no unique constraint can collide.

    READ COMMITTED does not save it: `SELECT sum(...)` takes no locks, so the
    two transactions never conflict.
    """
    from platform_core.modules.payment.service import PaymentService

    source = inspect.getsource(PaymentService._payable_settlement)
    assert "with_for_update=True" in source, (
        "the settlement must be locked before its balance is read, or two "
        "concurrent payments can each allocate the full outstanding amount"
    )


def test_the_lock_is_taken_before_the_balance_is_read():
    """Locking after the read would protect nothing — the stale sum is
    already in hand."""
    from platform_core.modules.payment.service import PaymentService

    source = inspect.getsource(PaymentService.create)
    lock_at = source.index("_payable_settlement")
    read_at = source.index("_resolve_allocation")
    assert lock_at < read_at, "the balance is read before the row is locked"


async def test_over_allocation_is_still_refused(client):
    """The guard the lock protects, unchanged."""
    from tests.test_payments import _payable, _post

    headers, _center, supplier, settlement = await _payable(client)
    body = {
        "supplier_id": supplier["id"],
        "currency": "KES",
        "method": "MOBILE_MONEY",
        "allocations": [{"settlement_id": settlement["id"]}],
    }
    first = await client.post("/v1/payments", json=body, headers=headers)
    assert first.status_code == 201
    second = await client.post("/v1/payments", json=body, headers=headers)
    assert second.status_code == 409, "a second payment claimed an already-allocated settlement"
    assert _post is not None


# --- connection pool and timeouts ------------------------------------------


def test_the_engine_configures_its_pool_on_postgresql():
    """SQLAlchemy's defaults — 5 connections, no pre-ping, no recycle, no
    statement or lock timeout — were the highest-probability cause of the
    first production incident, and survived four work orders."""
    from platform_core.core import db

    source = inspect.getsource(db.get_engine)
    for setting in (
        "pool_size",
        "max_overflow",
        "pool_pre_ping",
        "pool_recycle",
        "pool_timeout",
        "statement_timeout",
        "lock_timeout",
        "idle_in_transaction_session_timeout",
    ):
        assert setting in source, f"{setting} is not configured"


def test_sqlite_keeps_its_static_pool():
    """The test engine must not inherit PostgreSQL pool settings — StaticPool
    accepts none of them and the suite would fail to start."""
    from platform_core.core import db

    source = inspect.getsource(db.get_engine)
    sqlite_branch = source.index("StaticPool")
    postgres_branch = source.index("pool_pre_ping")
    assert sqlite_branch < postgres_branch
    assert "else:" in source


def test_every_pool_setting_is_configurable():
    from platform_core.core.config import Settings

    settings = Settings()
    for name in (
        "db_pool_size",
        "db_max_overflow",
        "db_pool_timeout_seconds",
        "db_pool_recycle_seconds",
        "db_statement_timeout_ms",
        "db_lock_timeout_ms",
        "db_idle_in_transaction_timeout_ms",
        "db_background_statement_timeout_ms",
    ):
        assert hasattr(settings, name), name


def test_background_work_gets_longer_than_a_request():
    """A projection rebuild replaying a million events, a backup reading
    every row, a deep integrity check — all legitimately exceed the request
    ceiling, and all would start failing the moment the pool landed."""
    from platform_core.core.config import Settings

    settings = Settings()
    assert settings.db_background_statement_timeout_ms > settings.db_statement_timeout_ms * 10


def test_the_background_timeout_is_raised_not_removed():
    """`unbounded` is the condition that made a timeout necessary."""
    from platform_core.core import rls

    source = inspect.getsource(rls._relax_statement_timeout)
    # VER-001: `set_config(..., true)`, not `SET LOCAL`. The `true` is the
    # is_local flag, so this keeps the transaction scope that made the raised
    # timeout safe to grant — while being a function call, which can take a
    # bind parameter. `SET` cannot, and that was a syntax error on every call.
    assert "set_config('statement_timeout'" in source
    assert "true" in source, "the raised timeout must stay transaction-local"
    assert "= 0" not in source.replace("!= 0", "")


def test_platform_sessions_relax_the_timeout():
    from platform_core.core import rls

    for func in (rls.platform_session, rls.PlatformSessionFactory._bound):
        assert "_relax_statement_timeout" in inspect.getsource(func), func


def test_the_pool_cannot_exceed_the_documented_connection_budget():
    """The runbook rule: replicas x (pool_size + max_overflow) + workers +
    operator headroom < max_connections. Exhausting max_connections makes NEW
    connections fail — including the operator's, during the incident."""
    import re
    from pathlib import Path

    from platform_core.core.config import Settings

    settings = Settings()
    env = (Path(__file__).resolve().parents[3] / ".env.production.example").read_text()
    workers = int(re.search(r"^API_WORKERS=(\d+)", env, re.M).group(1))
    max_conns = int(re.search(r"^POSTGRES_MAX_CONNECTIONS=(\d+)", env, re.M).group(1))
    per_worker = settings.db_pool_size + settings.db_max_overflow
    # Background loops and an operator need room on top.
    assert workers * per_worker + 10 < max_conns, (
        f"{workers} workers x {per_worker} connections leaves no headroom under "
        f"max_connections={max_conns}"
    )


# --- data integrity ---------------------------------------------------------


def test_the_payables_selector_has_an_index_that_matches_its_filter():
    """The screen an operator opens to pay people filters (tenant, status).
    Without this, PostgreSQL reads every settlement the tenant has ever had
    to find the handful that are unpaid."""
    from platform_core.modules.settlement.models import Settlement

    indexes = {i.name: [c.name for c in i.columns] for i in Settlement.__table__.indexes}
    assert indexes.get("ix_settlement_payable") == ["tenant_id", "status"], indexes


def test_a_payment_amount_cannot_be_non_positive_at_the_database():
    """The service refuses it; the database did not. This is the column whose
    corruption costs money, and a constraint closes every path the service
    layer does not sit in front of."""
    from platform_core.modules.payment.models import Payment

    checks = {
        c.name: str(c.sqltext)
        for c in Payment.__table__.constraints
        if type(c).__name__ == "CheckConstraint"
    }
    assert "ck_payment_amount_positive" in checks
    assert "amount > 0" in checks["ck_payment_amount_positive"]


async def test_the_database_refuses_a_non_positive_payment(client):
    """The constraint, executed — not just declared."""
    import uuid
    from decimal import Decimal

    from sqlalchemy.exc import IntegrityError

    from platform_core.core import db
    from platform_core.modules.payment.models import Payment

    async with db.get_session_factory()() as session:
        session.add(
            Payment(
                tenant_id=uuid.uuid4(),
                supplier_id=uuid.uuid4(),
                payment_number="PAY-BAD",
                currency="KES",
                method="CASH",
                amount=Decimal("0.00"),
                method_details={},
                status="draft",
                attempt_count=0,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


# --- client compatibility ---------------------------------------------------


def test_no_client_requests_a_page_larger_than_the_api_allows():
    """API-001 made an out-of-range page size a 422 rather than a silent
    clamp. That is correct, and it means a client asking for 500 now breaks —
    so the clients are checked rather than assumed."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    offenders = []
    for source in (
        list((root / "apps").rglob("*.dart"))
        + list((root / "apps").rglob("*.ts"))
        + list((root / "apps").rglob("*.tsx"))
    ):
        for match in re.finditer(r"limit=(\d+)", source.read_text()):
            if int(match.group(1)) > 200:
                offenders.append(f"{source.name}: limit={match.group(1)}")
    assert offenders == [], f"clients requesting more than the API permits: {offenders}"


# --------------------------------------------------------------------------
# VER-001 — the startup refusal.
#
# Executed here rather than in the PostgreSQL suite because it must hold for
# ANY database that answers this query, and because staging a superuser
# connection just to assert we refuse it would be a strange thing to require
# of the pipeline. The query itself is proven against a real server in
# tests/test_rls_postgres.py::test_a_role_that_bypasses_rls_is_refused.
# --------------------------------------------------------------------------


class _RoleStub:
    """A session that answers the role query and nothing else."""

    def __init__(self, role, is_super, bypasses):
        self._row = (role, is_super, bypasses)

    async def execute(self, *_args, **_kwargs):
        row = self._row

        class _Result:
            def first(self):
                return row

        return _Result()


@pytest.mark.parametrize(
    ("is_super", "bypasses", "reason"),
    [(True, False, "SUPERUSER"), (False, True, "BYPASSRLS")],
)
async def test_production_refuses_a_role_that_ignores_rls(monkeypatch, is_super, bypasses, reason):
    """The finding that justified a startup assertion rather than a note.

    A superuser ignores every row-level security policy. `FORCE ROW LEVEL
    SECURITY` does not help: it closes the loophole for the table OWNER and
    says nothing about superusers. The production stack connected as
    `${POSTGRES_USER}`, which the official postgres image creates as a
    superuser — so every policy SEC-001, SEC-002 and MT-001 built was inert.

    Nothing would have alerted. `verify-deployment.sh` checks that policies
    EXIST, and they did. So the platform refuses to start instead.
    """
    from platform_core.core.config import get_settings
    from platform_core.core.rls import RlsNotEnforceable, assert_rls_is_enforceable

    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://x/y")
    monkeypatch.setattr(settings, "rls_enabled", True)
    monkeypatch.setattr(settings, "env", "prod")

    with pytest.raises(RlsNotEnforceable) as caught:
        await assert_rls_is_enforceable(_RoleStub("postgres", is_super, bypasses))
    assert reason in str(caught.value)
    assert "NOSUPERUSER" in str(caught.value), "the error must say how to fix it"


async def test_a_normal_role_starts_cleanly(monkeypatch):
    from platform_core.core.config import get_settings
    from platform_core.core.rls import assert_rls_is_enforceable

    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://x/y")
    monkeypatch.setattr(settings, "rls_enabled", True)
    monkeypatch.setattr(settings, "env", "prod")
    await assert_rls_is_enforceable(_RoleStub("lacteva_app", False, False))
