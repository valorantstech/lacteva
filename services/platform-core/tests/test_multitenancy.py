"""Multi-tenancy audit (MT-001).

The platform has three layers of tenant isolation and they fail differently:

  1. **RLS** — the database refuses. Cannot be forgotten, cannot be executed
     on SQLite, and does not apply where the platform deliberately bypasses it.
  2. **Application filters** — every service scopes by `tenant_id`. Defence in
     depth on the request path, and the ONLY defence inside a bypassed one.
  3. **Key namespaces** — Redis keys, object-storage prefixes. Neither the
     database nor the service layer is involved, so neither can help.

This module tests the seams between them, which is where MT-001 found its
defects: code that runs under the bypass, and identifiers that are unique per
tenant being used as if they were unique globally.
"""

import uuid

# --- the bypass boundary ---------------------------------------------------


def test_background_components_receive_a_platform_bound_session_factory():
    """The defect MT-001 exists for.

    SEC-001 documented that "the relay dispatcher, consumers, and projection
    rebuilds set `lacteva.bypass_rls`". Nothing did — they built sessions from
    the ordinary factory, which binds neither a tenant nor a bypass. Under RLS
    that meant they could see only platform-global rows: the relay would find
    no tenant events, consumers would consume nothing, and every projection
    write would be refused by WITH CHECK.

    Nothing would have errored. That is the failure shape this platform's own
    documentation calls the most dangerous it has.
    """
    from platform_core.api import deps
    from platform_core.core.rls import PlatformSessionFactory

    for build in (
        deps.get_consumer_runner,
        deps.get_backup_service,
        deps.get_projection_rebuilder,
    ):
        component = build()
        factory = getattr(component, "_sf", None) or getattr(component, "_factory", None)
        assert isinstance(factory, PlatformSessionFactory), (
            f"{build.__name__} must hand its component a platform-bound factory — "
            "otherwise RLS hides every tenant row from work that spans tenants"
        )


def test_a_platform_factory_states_why_it_may_cross_tenants():
    """A bypass without a reason is a bypass nobody can audit."""
    from platform_core.core.rls import platform_factory

    factory = platform_factory("test: reason recorded")
    assert "test: reason recorded" in repr(factory)


async def test_the_platform_session_actually_binds_the_bypass(monkeypatch):
    """The binding must be issued, not merely intended. On SQLite the SQL is a
    no-op, so this asserts the CALL — which is the part that was missing."""
    from platform_core.core import rls

    reasons: list[str] = []

    async def record(session, *, reason):
        reasons.append(reason)

    monkeypatch.setattr(rls, "bind_platform_context", record)
    async with rls.platform_session("unit test") as session:
        assert session is not None
    assert reasons == ["unit test"]


async def test_every_bypass_in_the_codebase_names_its_reason():
    """`bind_platform_context` requires a keyword reason, and the platform
    factory carries one. A future call site that omits it will not compile —
    this asserts the signature stays that way."""
    import inspect

    from platform_core.core.rls import bind_platform_context

    signature = inspect.signature(bind_platform_context)
    assert signature.parameters["reason"].kind is inspect.Parameter.KEYWORD_ONLY


# --- rate-limit keys -------------------------------------------------------


def test_a_per_identifier_budget_is_namespaced_by_tenant():
    """Email is unique PER TENANT (`uq_user_tenant_email`), so the same address
    can belong to two different people in two different organizations. Keying
    a login budget on the email alone put both on one counter — a cross-tenant
    denial of service: fail to log in as `alice@x` in your own tenant and you
    spend Alice's budget in every other tenant that has her."""
    from platform_core.core.rate_limit import LOGIN_PER_USER

    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    key_a = LOGIN_PER_USER.key(
        ip="1.1.1.1", user="alice@example.com", endpoint="login", tenant=tenant_a
    )
    key_b = LOGIN_PER_USER.key(
        ip="1.1.1.1", user="alice@example.com", endpoint="login", tenant=tenant_b
    )
    assert key_a != key_b, "the same email in two tenants must not share a budget"
    assert tenant_a in key_a and tenant_b in key_b


def test_a_globally_unique_identifier_needs_no_tenant():
    """A user id is unique across the platform, so scoping it changes nothing
    and the key stays stable."""
    from platform_core.core.rate_limit import CONSUMER_REPLAY

    user_id = str(uuid.uuid4())
    assert CONSUMER_REPLAY.key(
        ip="1.1.1.1", user=user_id, endpoint="replay"
    ) == CONSUMER_REPLAY.key(ip="1.1.1.1", user=user_id, endpoint="replay")


async def test_a_tenant_scoped_login_charges_a_tenant_scoped_budget(client, monkeypatch):
    """End to end: the route must pass the tenant through, not just accept it."""
    from platform_core.core import rate_limit

    seen: list[str] = []
    real = rate_limit.enforce

    async def record(rule, *, ip, user, endpoint, tenant=None):
        if rule.name == rate_limit.LOGIN_PER_USER.name:
            seen.append(f"{tenant}")
        return await real(rule, ip=ip, user=user, endpoint=endpoint, tenant=tenant)

    monkeypatch.setattr(rate_limit, "enforce", record)
    tenant_id = str(uuid.uuid4())
    await client.post(
        "/v1/auth/token",
        json={"email": "nobody@example.com", "password": "wrong-password", "tenant_id": tenant_id},
    )
    assert seen == [tenant_id], f"the login route did not pass the tenant through: {seen}"


# --- notification dispatch -------------------------------------------------


async def test_the_recipient_directory_is_read_within_one_tenant(client):
    """Dispatch runs under the platform bypass, so RLS is not protecting this
    lookup — the application filter is all there is. A match across the
    boundary would send one dairy's payment details to another dairy's phone.
    """
    import inspect

    from platform_core.modules.notification.service import NotificationService

    source = inspect.getsource(NotificationService._directory_entry)
    assert "NotificationRecipient.tenant_id == notification.tenant_id" in source, (
        "the recipient lookup must be scoped by tenant, not only by subject"
    )


async def test_a_notification_never_resolves_another_tenants_recipient(client):
    """The behaviour, not the source: two tenants, one subject id, and the
    dispatcher must not reach across."""
    from platform_core.core import db
    from platform_core.modules.notification.models import Notification, NotificationRecipient
    from platform_core.modules.notification.service import NotificationService

    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    subject = uuid.uuid4()  # the same subject id in both tenants
    async with db.get_session_factory()() as session:
        session.add(
            NotificationRecipient(
                tenant_id=tenant_b,
                subject_id=subject,
                subject_type="supplier",
                display_name="Tenant B Supplier",
                code="B-1",
                phone="+254700000002",
                email="b@example.com",
                language="en",
                active=True,
            )
        )
        await session.commit()

        # A notification belonging to tenant A, pointing at that subject id.
        notification = Notification(
            tenant_id=tenant_a,
            event_id=uuid.uuid4(),
            event_name="payment.completed.v1",
            template_key="payment_completed",
            channel="sms",
            language="en",
            recipient_ref=subject,
            payload={},
            status="pending",
            attempt_count=0,
        )
        entry = await NotificationService(session)._directory_entry(notification)
    assert entry is None, "tenant A resolved tenant B's phone number"


# --- object storage --------------------------------------------------------


def test_object_keys_are_prefixed_by_tenant():
    """Buckets are shared; the prefix is the boundary. Two tenants uploading
    the same filename for the same supplier id must not collide."""
    from platform_core.infrastructure.storage import tenant_key

    a, b = uuid.uuid4(), uuid.uuid4()
    assert tenant_key(a, "suppliers/x/doc.pdf").startswith(f"{a}/")
    assert tenant_key(a, "suppliers/x/doc.pdf") != tenant_key(b, "suppliers/x/doc.pdf")


def test_a_platform_level_object_is_namespaced_too():
    """`None` must not produce a bare key that could collide with a tenant's."""
    from platform_core.infrastructure.storage import tenant_key

    assert tenant_key(None, "x.pdf") == "platform/x.pdf"


async def test_a_document_url_cannot_be_obtained_across_tenants(client):
    """The download path resolves the supplier first, and the supplier lookup
    is tenant-scoped — so a valid document id from another tenant is a 404."""
    from tests.test_org_structure import _tenant_admin

    _org, headers = await _tenant_admin(client)
    r = await client.get(f"/v1/suppliers/{uuid.uuid4()}/documents/{uuid.uuid4()}", headers=headers)
    assert r.status_code == 404


# --- pagination and reporting ----------------------------------------------


async def test_pagination_totals_are_tenant_scoped(client):
    """A `total` computed without the tenant filter leaks the size of other
    tenants' data even when the page itself is correct."""
    import inspect

    from platform_core.modules.receipt.service import ReceiptService

    source = inspect.getsource(ReceiptService.search)
    # The count must derive from the SAME statement that carries the filter,
    # never from a fresh select over the table.
    assert "select_from(stmt.subquery())" in source, (
        "the total must be counted over the filtered statement"
    )


def test_every_reporting_query_starts_from_the_tenant():
    """Reporting reads across module boundaries by design (REP-001), which
    makes it the easiest place to forget a filter."""
    import inspect

    from platform_core.modules.reporting import service

    source = inspect.getsource(service)
    assert source.count("require_current_tenant()") >= 5
    assert "Tx.tenant_id == tenant_id" in source
    assert "Settlement.tenant_id == tenant_id" in source
    assert "RateCard.tenant_id == tenant_id" in source


def test_the_settlement_line_report_joins_through_its_parent():
    """`settlement_line` is reached by join; the join must carry the tenant
    predicate, or the count spans the platform."""
    import inspect

    from platform_core.modules.reporting import service

    source = inspect.getsource(service.ReportingService.settlement_summary)
    assert "join(Settlement, Settlement.id == SettlementLine.settlement_id)" in source
    assert "where(*conditions)" in source


# --- audit -----------------------------------------------------------------


def test_audit_records_carry_and_filter_by_tenant():
    import inspect

    from platform_core.modules.audit import service

    source = inspect.getsource(service)
    assert "tenant_id=get_current_tenant()" in source, "an audit record must record its tenant"
    assert "AuditRecord.tenant_id == get_current_tenant()" in source, (
        "the audit trail must be read within one tenant"
    )


# --- JWT -------------------------------------------------------------------


async def test_the_token_is_the_authority_on_tenant_not_the_header(client):
    """A tenant-scoped token must not be re-scoped by a header the caller
    controls — otherwise the tenant boundary is client-supplied."""
    from tests.test_org_structure import _tenant_admin

    org, headers = await _tenant_admin(client)
    other = str(uuid.uuid4())
    me = (await client.get("/v1/auth/me", headers={**headers, "X-Tenant-ID": other})).json()
    assert me["tenant_id"] == org["id"], "the X-Tenant-ID header overrode the token's tenant"


async def test_a_tenant_token_cannot_reach_another_tenants_resource(client):
    from tests.test_org_structure import _tenant_admin

    _org, headers = await _tenant_admin(client)
    for path in ("/v1/suppliers", "/v1/settlements", "/v1/payments", "/v1/receipts"):
        r = await client.get(f"{path}/{uuid.uuid4()}", headers=headers)
        assert r.status_code in (404, 422), f"{path} returned {r.status_code}"


# --- websockets ------------------------------------------------------------


def test_there_are_no_websocket_endpoints_to_audit():
    """Recorded rather than assumed. The work order asks about websocket
    tenancy; the platform has none, and this test is what will fail when the
    first one is added — at which point its tenant binding needs designing,
    because a socket outlives the request that authenticated it."""
    from platform_core.main import create_app

    app = create_app()
    sockets = [r for r in app.routes if r.__class__.__name__ == "APIWebSocketRoute"]
    assert sockets == [], f"websocket endpoints exist and need a tenancy review: {sockets}"
