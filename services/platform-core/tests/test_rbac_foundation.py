"""Authentication and authorization, executed (DEMO-008).

The claim this work order makes is that authorization is database-driven and
that the BACKEND is the authority. Neither half can be shown by reading code:
a permission set is only real if the platform refuses when it is absent, and
"the backend is the authority" only means something if a request that skips the
portal entirely is still refused.

So every test below drives the real API with a real token, and most of them
assert a refusal.

The roles under test are rows. Nothing here branches on a role NAME — the tests
grant a named role and then assert what the platform will and will not do,
which is the only way to tell a database-driven decision from a hard-coded one.
"""

import uuid

import pytest

from tests.conftest import invite, register_and_login
from tests.test_org_structure import _tenant_admin


async def _member(client, admin, org_id, *, email, role_name, center_id=None, password=None):
    """A user in `org_id` holding `role_name`, optionally scoped to a centre."""
    password = password or "member-password-1"
    _inv, token = await invite(
        client,
        {**admin, "X-Tenant-ID": org_id},
        email=email,
        role_name="tenant-viewer",  # a placeholder grant; the real one follows
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": password, "full_name": email.split("@")[0]},
    )
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]

    # Swap the placeholder for the role under test, at the requested scope.
    r = await client.delete(
        f"/v1/authz/assignments?user_id={user_id}&role_name=tenant-viewer",
        headers={**admin, "X-Tenant-ID": org_id},
    )
    assert r.status_code == 204, r.text
    body = {"user_id": user_id, "role_name": role_name}
    if center_id is not None:
        body["center_id"] = str(center_id)
    r = await client.post(
        "/v1/authz/assignments", json=body, headers={**admin, "X-Tenant-ID": org_id}
    )
    assert r.status_code == 201, r.text

    pair = (
        await client.post(
            "/v1/auth/token",
            json={"email": email, "password": password, "tenant_id": org_id},
        )
    ).json()
    return user_id, {"Authorization": f"Bearer {pair['access_token']}"}


async def _org_with_centres(client):
    """An organization, its admin, and two collection centres."""
    org, admin = await _tenant_admin(client)
    r = await client.post(
        "/v1/workspaces", json={"name": "Central Region", "slug": "central"}, headers=admin
    )
    assert r.status_code == 201, r.text
    ws = r.json()
    r = await client.post(
        "/v1/branches",
        json={"workspace_id": ws["id"], "name": "Central Hub", "code": "CDH"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    branch = r.json()
    centres = []
    for name, code in (("Centre A", "CA"), ("Centre B", "CB")):
        r = await client.post(
            "/v1/collection-centers",
            json={"branch_id": branch["id"], "name": name, "code": code},
            headers=admin,
        )
        assert r.status_code == 201, r.text
        centres.append(r.json())
    return org, admin, centres


# --- 1. unauthenticated -------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/v1/milk-transactions",
        "/v1/collection-centers",
        "/v1/settlements",
        "/v1/payments",
        "/v1/receipts",
        "/v1/audit",
        "/v1/auth/me",
    ],
)
async def test_unauthenticated_cannot_reach_a_protected_endpoint(client, path):
    r = await client.get(path)
    assert r.status_code == 401, f"{path} -> {r.status_code}"


async def test_a_forged_token_is_refused(client):
    r = await client.get("/v1/milk-transactions", headers={"Authorization": "Bearer not.a.token"})
    assert r.status_code == 401


# --- 2. a permitted user can act ---------------------------------------------


async def test_an_organization_admin_can_reach_what_the_role_grants(client):
    org, admin, _centres = await _org_with_centres(client)
    _uid, headers = await _member(
        client, admin, org["id"], email="admin2@kilima.example", role_name="ORGANIZATION_ADMIN"
    )
    for path in (
        "/v1/collection-centers",
        "/v1/suppliers",
        "/v1/milk-transactions",
        "/v1/settlements",
        "/v1/payments",
        "/v1/audit",
        "/v1/identity/users/" + _uid,
    ):
        r = await client.get(path, headers=headers)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:120]}"


# --- 3. a user without the permission is refused ------------------------------


async def test_an_organization_manager_cannot_do_finance_manager_work(client):
    """§15.6. The manager may READ settlements and may not finalize one — and
    the difference is a row in `role_permission`, not a branch in the code."""
    org, admin, _c = await _org_with_centres(client)
    _uid, manager = await _member(
        client, admin, org["id"], email="mgr@kilima.example", role_name="ORGANIZATION_MANAGER"
    )

    assert (await client.get("/v1/settlements", headers=manager)).status_code == 200
    r = await client.post(f"/v1/settlements/{uuid.uuid4()}/finalize", json={}, headers=manager)
    assert r.status_code == 403
    r = await client.post(
        "/v1/settlements",
        json={
            "supplier_id": str(uuid.uuid4()),
            "center_id": str(uuid.uuid4()),
            "period_from": "2026-09-01",
            "period_to": "2026-09-07",
            "currency": "KES",
        },
        headers=manager,
    )
    assert r.status_code == 403
    # ...nor administer people or publish prices.
    assert (
        await client.post(
            "/v1/authz/roles", json={"name": "x", "permission_keys": []}, headers=manager
        )
    ).status_code == 403


async def test_a_finance_officer_cannot_finalize_or_administer_users(client):
    """§15.6 in the other direction, and §8's "a Finance Officer should not
    automatically receive user administration"."""
    org, admin, _c = await _org_with_centres(client)
    _uid, officer = await _member(
        client, admin, org["id"], email="fo@kilima.example", role_name="FINANCE_OFFICER"
    )

    assert (await client.get("/v1/settlements", headers=officer)).status_code == 200
    assert (await client.get("/v1/payments", headers=officer)).status_code == 200
    # Finalization belongs to the manager.
    r = await client.post(f"/v1/settlements/{uuid.uuid4()}/finalize", json={}, headers=officer)
    assert r.status_code == 403
    # User administration does not come with the finance job.
    assert (await client.get("/v1/members", headers=officer)).status_code == 403
    assert (
        await client.post(
            "/v1/authz/roles", json={"name": "y", "permission_keys": []}, headers=officer
        )
    ).status_code == 403
    # Nor does publishing a rate card.
    assert (
        await client.post(f"/v1/rate-cards/{uuid.uuid4()}/publish", json={}, headers=officer)
    ).status_code == 403


async def test_a_finance_manager_may_finalize(client):
    """The mirror image: the permission is what differs, and it is granted by
    a row, so the same request succeeds far enough to hit business logic."""
    org, admin, _c = await _org_with_centres(client)
    _uid, manager = await _member(
        client, admin, org["id"], email="fm@kilima.example", role_name="FINANCE_MANAGER"
    )
    r = await client.post(f"/v1/settlements/{uuid.uuid4()}/finalize", json={}, headers=manager)
    # 404 — permitted, then refused by the domain because that id does not
    # exist. NOT 403, which is the point.
    assert r.status_code == 404, r.text


# --- 4. cross-organization ----------------------------------------------------


async def test_a_user_cannot_read_another_organizations_data(client):
    """§15.4 — and the platform's established answer is 404, never 403, so the
    existence of the row is not confirmed. DEMO-003..007 depend on this."""
    org_a, admin_a, centres_a = await _org_with_centres(client)
    _uid, member_a = await _member(
        client, admin_a, org_a["id"], email="a@kilima.example", role_name="ORGANIZATION_ADMIN"
    )

    _, root_b = await register_and_login(client, "root-b@example.com", admin=True)
    org_b = (
        await client.post(
            "/v1/organizations",
            json={"name": "Rift Dairy", "slug": "rift-rbac", "country_code": "ke"},
            headers=root_b,
        )
    ).json()
    ws = (
        await client.post(
            "/v1/workspaces",
            json={"name": "Rift Region", "slug": "rift-region"},
            headers={**root_b, "X-Tenant-ID": org_b["id"]},
        )
    ).json()
    branch = (
        await client.post(
            "/v1/branches",
            json={"workspace_id": ws["id"], "name": "Rift Hub", "code": "RFH"},
            headers={**root_b, "X-Tenant-ID": org_b["id"]},
        )
    ).json()
    centre_b = (
        await client.post(
            "/v1/collection-centers",
            json={"branch_id": branch["id"], "name": "Foreign", "code": "FC"},
            headers={**root_b, "X-Tenant-ID": org_b["id"]},
        )
    ).json()

    # A holds every permission its own organization can grant, and still cannot
    # see B's centre.
    assert (
        await client.get(f"/v1/collection-centers/{centre_b['id']}", headers=member_a)
    ).status_code == 404
    listed = (await client.get("/v1/collection-centers", headers=member_a)).json()
    assert {c["id"] for c in listed["items"]} == {c["id"] for c in centres_a}


# --- 5. centre scope ----------------------------------------------------------


async def test_a_centre_scoped_user_cannot_reach_another_centre(client):
    """§15.5. Within one organization, so this is NOT tenant isolation — it is
    the centre scope on the grant doing the work."""
    org, admin, centres = await _org_with_centres(client)
    a, b = centres
    _uid, scoped = await _member(
        client,
        admin,
        org["id"],
        email="centre-a@kilima.example",
        role_name="CENTRE_MANAGER",
        center_id=a["id"],
    )

    # Their own centre: fine.
    assert (
        await client.get(f"/v1/collection-centers/{a['id']}", headers=scoped)
    ).status_code == 200
    assert (
        await client.get(f"/v1/collection-centers/{a['id']}/readiness", headers=scoped)
    ).status_code == 200

    # The other centre in the SAME organization: refused, and deliberately 403
    # rather than 404 — its existence is not a secret from a colleague.
    r = await client.get(f"/v1/collection-centers/{b['id']}", headers=scoped)
    assert r.status_code == 403, r.text
    assert (
        await client.get(f"/v1/collection-centers/{b['id']}/readiness", headers=scoped)
    ).status_code == 403

    # And the list shows only what they may act at.
    listed = (await client.get("/v1/collection-centers", headers=scoped)).json()
    assert [c["id"] for c in listed["items"]] == [a["id"]]


async def test_a_centre_scoped_user_cannot_open_a_session_elsewhere(client):
    """The centre arrives in the body here, so it is checked in the handler.
    Opening a session is where a person starts working somewhere."""
    org, admin, centres = await _org_with_centres(client)
    a, b = centres
    _uid, scoped = await _member(
        client,
        admin,
        org["id"],
        email="op-a@kilima.example",
        role_name="COLLECTION_OPERATOR",
        center_id=a["id"],
    )
    r = await client.post(
        "/v1/collection-sessions", json={"center_id": b["id"], "label": "morning"}, headers=scoped
    )
    assert r.status_code == 403, r.text


async def test_an_unscoped_grant_stays_organization_wide(client):
    """The column is nullable and NULL means everything — otherwise this work
    order would have silently narrowed every user that existed before it."""
    org, admin, centres = await _org_with_centres(client)
    _uid, wide = await _member(
        client, admin, org["id"], email="wide@kilima.example", role_name="ORGANIZATION_MANAGER"
    )
    listed = (await client.get("/v1/collection-centers", headers=wide)).json()
    assert {c["id"] for c in listed["items"]} == {c["id"] for c in centres}
    for centre in centres:
        assert (
            await client.get(f"/v1/collection-centers/{centre['id']}", headers=wide)
        ).status_code == 200


# --- 6/7. auditor is read-only ------------------------------------------------


async def test_an_auditor_reads_everything_and_changes_nothing(client):
    """§5: "Auditor must not receive create/update/finalize/payment
    permissions." Asserted by making the platform refuse each one."""
    org, admin, centres = await _org_with_centres(client)
    _uid, auditor = await _member(
        client, admin, org["id"], email="auditor@kilima.example", role_name="AUDITOR"
    )

    for path in (
        "/v1/collection-centers",
        "/v1/suppliers",
        "/v1/milk-transactions",
        "/v1/settlements",
        "/v1/payments",
        "/v1/receipts",
        "/v1/audit",
        "/v1/reports/settlements",
    ):
        assert (await client.get(path, headers=auditor)).status_code == 200, path

    refusals = [
        (
            "post",
            "/v1/collection-centers",
            {"branch_id": str(uuid.uuid4()), "name": "New Centre", "code": "NCX"},
        ),
        ("post", "/v1/suppliers", {"full_name": "X", "phone": "+254700000000"}),
        ("post", f"/v1/settlements/{uuid.uuid4()}/finalize", {}),
        (
            "post",
            "/v1/payments",
            {
                "supplier_id": str(uuid.uuid4()),
                "currency": "KES",
                "method": "CASH",
                "allocations": [],
            },
        ),
        ("post", "/v1/collection-sessions", {"center_id": centres[0]["id"], "label": "x"}),
        ("post", "/v1/authz/roles", {"name": "z", "permission_keys": []}),
    ]
    for method, path, body in refusals:
        r = await getattr(client, method)(path, json=body, headers=auditor)
        assert r.status_code == 403, f"{path} -> {r.status_code} {r.text[:100]}"


async def test_the_auditor_role_grants_no_mutating_permission(client):
    """A structural check to go with the behavioural ones: no key in the role
    can perform a change. This catches a permission added to the registry and
    carelessly copied into the read-only role."""
    from platform_core.modules.authz.permissions import NAMED_ROLES

    forbidden = ("manage", "record", "finalize", "retry", "approve", "write", "delete", "export")
    offenders = [k for k in NAMED_ROLES["AUDITOR"] if k.rsplit(".", 1)[-1] in forbidden]
    assert offenders == []


# --- 8. a collection operator is not an administrator -------------------------


async def test_a_collection_operator_can_collect_but_not_administer(client):
    org, admin, centres = await _org_with_centres(client)
    _uid, operator = await _member(
        client,
        admin,
        org["id"],
        email="op@kilima.example",
        role_name="COLLECTION_OPERATOR",
        center_id=centres[0]["id"],
    )

    # The job.
    assert (await client.get("/v1/suppliers", headers=operator)).status_code == 200
    assert (await client.get("/v1/milk-transactions", headers=operator)).status_code == 200
    r = await client.post(
        "/v1/collection-sessions",
        json={"center_id": centres[0]["id"], "label": "morning"},
        headers=operator,
    )
    # AUTHORIZED is the claim here. A bare centre is not ready to receive milk
    # (no scale, no operating hours), and the platform says so with a 409 —
    # which is the domain talking, not the guard. A 403 would mean the
    # operator was refused the centre they are assigned to.
    assert r.status_code != 403, r.text
    assert r.status_code in (201, 409), r.text

    # Not the job — every one of these is an administration surface the
    # navigation must also hide, but hiding is not what refuses them.
    for method, path in (
        ("get", "/v1/rate-cards"),
        ("get", "/v1/pricing-matrices"),
        ("get", "/v1/payments"),
        ("get", "/v1/settlements"),
        ("get", "/v1/members"),
        ("get", "/v1/authz/roles"),
        ("get", "/v1/audit"),
        ("get", "/v1/config/anything"),
    ):
        r = await getattr(client, method)(path, headers=operator)
        assert r.status_code == 403, f"{path} -> {r.status_code}"


# --- 9. suspended membership --------------------------------------------------


async def test_a_suspended_member_stops_working_immediately(client):
    """§15.9, and the defect this work order found.

    Membership was checked at LOGIN and never again, so suspending someone did
    nothing until their access token expired — and their refresh token kept
    minting new ones. The token below is issued while the member is in good
    standing and must stop working the moment the membership does.
    """
    org, admin, _c = await _org_with_centres(client)
    user_id, member = await _member(
        client, admin, org["id"], email="suspendme@kilima.example", role_name="ORGANIZATION_MANAGER"
    )
    assert (await client.get("/v1/collection-centers", headers=member)).status_code == 200

    r = await client.post(
        f"/v1/members/{user_id}/status",
        json={"status": "suspended"},
        headers={**admin, "X-Tenant-ID": org["id"]},
    )
    assert r.status_code in (200, 204), r.text

    # The SAME token, already issued, is now refused.
    assert (await client.get("/v1/collection-centers", headers=member)).status_code == 401
    assert (await client.get("/v1/auth/me", headers=member)).status_code == 401


# --- 10. the backend is the authority ----------------------------------------


async def test_the_backend_refuses_regardless_of_what_a_client_believes(client):
    """§15.10. The portal hides what a user may not do; that is a courtesy.
    These requests are what a client that ignored the courtesy would send —
    straight at the API, with a valid token and no portal involved."""
    org, admin, centres = await _org_with_centres(client)
    _uid, operator = await _member(
        client,
        admin,
        org["id"],
        email="determined@kilima.example",
        role_name="COLLECTION_OPERATOR",
        center_id=centres[0]["id"],
    )

    # Guessing a URL the navigation never showed:
    assert (await client.get("/v1/authz/roles", headers=operator)).status_code == 403
    # Sending a body that names another organization:
    r = await client.post(
        "/v1/collection-sessions",
        json={"center_id": centres[1]["id"], "label": "wherever"},
        headers=operator,
    )
    assert r.status_code == 403
    # Claiming a different tenant in a header:
    r = await client.get(
        "/v1/collection-centers",
        headers={**operator, "X-Tenant-ID": str(uuid.uuid4())},
    )
    # The token's tenant is authoritative; the header cannot widen it.
    assert r.status_code in (200, 403)
    if r.status_code == 200:
        assert [c["id"] for c in r.json()["items"]] == [centres[0]["id"]]


# --- the session endpoint -----------------------------------------------------


async def test_auth_me_carries_the_authorization_context_and_no_secrets(client):
    """§13. Everything the portal needs to decide what to show, and nothing
    that would help anyone log in as this user."""
    org, admin, centres = await _org_with_centres(client)
    _uid, scoped = await _member(
        client,
        admin,
        org["id"],
        email="me@kilima.example",
        role_name="CENTRE_MANAGER",
        center_id=centres[0]["id"],
    )
    body = (await client.get("/v1/auth/me", headers=scoped)).json()

    assert body["organization"]["id"] == org["id"]
    assert body["organization"]["name"]
    assert body["membership"]["status"] == "active"
    assert [r["name"] for r in body["roles"]] == ["CENTRE_MANAGER"]
    assert body["roles"][0]["center_id"] == centres[0]["id"]
    assert body["center_scope"] == [centres[0]["id"]]
    assert "collection.transaction.record" in body["permissions"]

    # Nothing sensitive, at any depth.
    serialized = str(body)
    for secret in ("password", "hash", "token", "secret", "refresh"):
        assert secret not in serialized.lower(), secret


async def test_auth_me_reports_organization_wide_scope_as_null(client):
    org, admin, _c = await _org_with_centres(client)
    _uid, wide = await _member(
        client, admin, org["id"], email="wide2@kilima.example", role_name="ORGANIZATION_MANAGER"
    )
    body = (await client.get("/v1/auth/me", headers=wide)).json()
    assert body["center_scope"] is None


async def test_last_login_is_recorded(client):
    """§9 — an administrator reviewing access needs to see a dormant account."""
    org, admin, _c = await _org_with_centres(client)
    _uid, member = await _member(
        client, admin, org["id"], email="stamp@kilima.example", role_name="ORGANIZATION_MANAGER"
    )
    body = (await client.get("/v1/auth/me", headers=member)).json()
    assert body["user"]["last_login_at"] is not None
    assert "password_hash" not in body["user"]


# --- roles are rows, not code -------------------------------------------------


async def test_every_named_role_exists_in_the_database_after_bootstrap(client):
    """The roles are seeded, idempotently, and resolvable by name — which is
    what makes granting one a database operation rather than a code path."""
    from platform_core.modules.authz.permissions import NAMED_ROLES

    _org, admin = await _tenant_admin(client)
    listed = (await client.get("/v1/authz/roles", headers=admin)).json()
    names = {r["name"] for r in listed}
    for role in NAMED_ROLES:
        assert role in names, f"{role} was not seeded"


async def test_seeding_twice_does_not_duplicate_roles_or_permissions(client):
    """§11: the seed must be idempotent. Running it again is exactly what a
    redeploy does."""
    from sqlalchemy import func, select

    from platform_core.core.rls import platform_factory
    from platform_core.modules.authz.models import Role, RolePermission
    from platform_core.modules.authz.service import AuthzService

    async with platform_factory("test: count roles")() as session:
        before_roles = await session.scalar(select(func.count()).select_from(Role))
        before_perms = await session.scalar(select(func.count()).select_from(RolePermission))

    async with platform_factory("test: reseed")() as session:
        await AuthzService(session).ensure_system_roles()
        await session.commit()

    async with platform_factory("test: recount")() as session:
        after_roles = await session.scalar(select(func.count()).select_from(Role))
        after_perms = await session.scalar(select(func.count()).select_from(RolePermission))

    assert (after_roles, after_perms) == (before_roles, before_perms)


async def test_a_role_grant_is_audited(client):
    """§14 — a change of authority must be traceable through the existing
    audit trail, not a new one."""
    org, admin, centres = await _org_with_centres(client)
    _user_id, _headers = await _member(
        client,
        admin,
        org["id"],
        email="audited@kilima.example",
        role_name="CENTRE_MANAGER",
        center_id=centres[0]["id"],
    )
    # The grant records the ASSIGNMENT as its resource, so the trail is found
    # by action rather than by the user id.
    trail = (
        await client.get(
            "/v1/audit?action=authz.role&limit=50", headers={**admin, "X-Tenant-ID": org["id"]}
        )
    ).json()
    actions = {r["action"] for r in trail["items"]}
    assert "authz.role.granted" in actions, actions
    assert "authz.role.revoked" in actions, actions
    assert trail["total"] >= 2
