"""A shop owner can no longer make anyone a Lacteva platform admin (WO-109 · LACTEVA-SEC-004).

Found by the architect as the rehearsal shop's owner: Staff → Invite offered
"Platform Admin". `invite()` checked nothing about the role, `_resolve_role`
found the global `platform-admin` inside the tenant by name, and no route
insisted on a platform session — so a tenant account came to hold `*` and
reached the relay, security administration and organisation creation.

Every proof below is from the TENANT's side through the real routes.
"""

import inspect
import uuid

import pytest
from sqlalchemy import select

from platform_core.api import routes as routes_module
from platform_core.core.errors import RoleScopeError
from platform_core.modules.authz.audit import find_platform_grants, render
from platform_core.modules.authz.models import Role, UserRole
from platform_core.modules.authz.permissions import PLATFORM_ROLES, is_platform_grant
from platform_core.modules.authz.service import AuthzService
from tests import conftest as ct
from tests.test_org_structure import _tenant_admin


async def _member(client, admin, org_id, *, email, role_name="SALES_OFFICER"):
    _inv, token = await ct.invite(client, admin, email=email, role_name=role_name)
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "member-password-1", "full_name": "Member"},
    )
    assert r.status_code == 201, r.text
    pair = (
        await client.post(
            "/v1/auth/token",
            json={"email": email, "password": "member-password-1", "tenant_id": org_id},
        )
    ).json()
    return r.json()["id"], {"Authorization": f"Bearer {pair['access_token']}"}


def test_the_registry_knows_which_roles_are_lactevas():
    assert PLATFORM_ROLES == {"platform-admin", "PLATFORM_SUPER_ADMIN"}
    assert is_platform_grant(["*"]) and is_platform_grant(["platform.relay.manage"])
    assert is_platform_grant(["sales.customer.read", "organization.manage"])
    assert not is_platform_grant(["organization.settings.manage", "identity.user.manage"])


@pytest.mark.parametrize("role", ["platform-admin", "PLATFORM_SUPER_ADMIN"])
async def test_a_tenant_admin_cannot_invite_a_platform_role(client, role):
    _org, admin = await _tenant_admin(client)
    r = await client.post(
        "/v1/invitations", json={"email": "mole@kilima.example", "role_name": role}, headers=admin
    )
    assert r.status_code == 403, r.text
    body = r.json()
    assert body["title"] == "role_out_of_scope"
    assert "platform" in body["extra"].lower() or "cannot grant" in body["extra"]
    # Nothing was written: no invitation waits with that role.
    listed = (await client.get("/v1/invitations", headers=admin)).json()
    assert all(i["role_name"] != role for i in listed), listed


async def test_a_tenant_admin_cannot_assign_a_platform_role_by_hand(client):
    org, admin = await _tenant_admin(client)
    user_id, _ = await _member(client, admin, org["id"], email="staff@kilima.example")
    for role in ("platform-admin", "PLATFORM_SUPER_ADMIN"):
        r = await client.post(
            "/v1/authz/assignments", json={"user_id": user_id, "role_name": role}, headers=admin
        )
        assert r.status_code in (403, 404), (role, r.text)
    # A tenant's custom role cannot smuggle platform permissions in either.
    for keys in (["*"], ["platform.relay.manage"], ["sales.customer.read", "organization.manage"]):
        r = await client.post(
            "/v1/authz/roles",
            json={"name": f"sneaky-{len(keys)}", "permission_keys": keys},
            headers=admin,
        )
        assert r.status_code == 403, (keys, r.text)
        assert r.json()["title"] == "role_out_of_scope"


async def test_assign_role_refuses_a_platform_role_inside_a_tenant_whoever_asks(client):
    """The service itself, with no caller named — the platform's own code
    path — still refuses: (a) is a rule about the grant, not the caller."""
    org, _admin = await _tenant_admin(client)
    tenant_id = uuid.UUID(org["id"])
    async with ct.db.get_session_factory()() as session:
        from platform_core.core.rls import bind_platform_context

        await bind_platform_context(session, reason="WO-109 test: direct assign")
        authz = AuthzService(session)
        with pytest.raises((RoleScopeError, Exception)) as excinfo:
            await authz.assign_role(
                user_id=uuid.uuid4(), role_name="platform-admin", tenant_id=tenant_id
            )
        assert excinfo.type.__name__ in ("RoleScopeError", "NotFoundError"), excinfo.type
        # And the platform's own grant — to a platform account, no tenant — works as before.
        grant = await authz.assign_role(
            user_id=uuid.uuid4(), role_name="platform-admin", tenant_id=None
        )
        assert grant.tenant_id is None


async def test_nobody_grants_beyond_their_own_reach(client):
    """(b): an inviter holding member.manage but not the platform's whole
    tenant-admin set may invite roles inside their own permissions only."""
    org, admin = await _tenant_admin(client)
    # A custom "hiring manager" role: may manage members and read users, and
    # holds the driver's own permissions — nothing more.
    r = await client.post(
        "/v1/authz/roles",
        json={
            "name": "hiring-manager",
            "permission_keys": [
                "organization.member.manage",
                "organization.member.read",
                "identity.user.read",
                "logistics.run.execute",
                "catalog.read",
                "sales.item.record",
            ],
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    hirer_id, hirer = await _member(
        client, admin, org["id"], email="hirer@kilima.example", role_name="hiring-manager"
    )
    # Within reach: a Delivery boy (DRIVER ⊆ hiring-manager's permissions).
    r = await client.post(
        "/v1/invitations",
        json={"email": "boy@kilima.example", "role_name": "DRIVER"},
        headers=hirer,
    )
    assert r.status_code == 201, r.text
    # Beyond reach: the owner's role.
    r = await client.post(
        "/v1/invitations",
        json={"email": "boss@kilima.example", "role_name": "tenant-admin"},
        headers=hirer,
    )
    assert r.status_code == 403, r.text
    assert r.json()["title"] == "role_out_of_scope"
    assert "permissions you do not have" in r.json()["extra"]
    # The same reach rule on direct assignment.
    r = await client.post(
        "/v1/authz/assignments",
        json={"user_id": hirer_id, "role_name": "tenant-admin"},
        headers=hirer,
    )
    assert r.status_code == 403, r.text
    # And the owner, whose permissions cover tenant-admin's, still invites one.
    r = await client.post(
        "/v1/invitations",
        json={"email": "second-owner@kilima.example", "role_name": "tenant-admin"},
        headers=admin,
    )
    assert r.status_code == 201, r.text


async def test_the_role_list_a_tenant_reads_holds_no_platform_role_and_says_what_is_grantable(
    client,
):
    org, admin = await _tenant_admin(client)
    roles = (await client.get("/v1/authz/roles", headers=admin)).json()
    names = {r["name"] for r in roles}
    assert not names & PLATFORM_ROLES, names
    assert {"tenant-admin", "DRIVER", "SALES_OFFICER"} <= names
    assert all(r["grantable"] is True for r in roles), "the owner's reach covers every tenant role"
    # A narrower member sees what THEY may grant.
    r = await client.post(
        "/v1/authz/roles",
        json={"name": "reader", "permission_keys": ["authz.role.read", "organization.member.read"]},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    _id, reader = await _member(
        client, admin, org["id"], email="reader@kilima.example", role_name="reader"
    )
    r = await client.get("/v1/authz/roles", headers=reader)
    assert r.status_code == 200, r.text
    by_name = {x["name"]: x for x in r.json()}
    grantable = {name for name, x in by_name.items() if x["grantable"]}
    assert "tenant-admin" not in grantable and "reader" in grantable
    # The Delivery boy's key is a surface, not a power: the owner grants the
    # role without holding the key; the reader, lacking catalog.read, cannot.
    assert by_name["DRIVER"]["grantable"] is False


#: Every route WO-109 (c) moved onto `require_platform_permission`, as the app
#: actually registers them — the enumeration below asserts the two agree, so a
#: route added to one and not the other fails here. `{…}` is filled with a
#: sample; the guard runs before any lookup, so 403 comes before 404.
PLATFORM_ROUTES = {
    ("GET", "/v1/_security/keys"),
    ("GET", "/v1/_ops/health"),
    ("GET", "/v1/_ops/alerts"),
    ("GET", "/v1/_ops/alert-rules"),
    ("GET", "/v1/_ops/backups/status"),
    ("GET", "/v1/_ops/backups"),
    ("GET", "/v1/_ops/backups/classification"),
    ("POST", "/v1/_ops/backups/verify-integrity"),
    ("GET", "/v1/_ops/overview"),
    ("GET", "/v1/_relay/status"),
    ("GET", "/v1/_relay/events"),
    ("GET", "/v1/_relay/dead-letters"),
    ("POST", "/v1/_relay/dead-letters/{dead_letter_id}/replay"),
    ("POST", "/v1/_relay/events/{event_id}/retry"),
    ("POST", "/v1/_relay/events/{event_id}/replay"),
    ("POST", "/v1/_relay/dispatch"),
    ("GET", "/v1/_consumers/status"),
    ("POST", "/v1/_consumers/run"),
    ("GET", "/v1/_consumers/executions"),
    ("GET", "/v1/_consumers/dead-letters"),
    ("POST", "/v1/_consumers/{name}/pause"),
    ("POST", "/v1/_consumers/{name}/resume"),
    ("POST", "/v1/_consumers/executions/{execution_id}/replay"),
    ("GET", "/v1/_projections"),
    ("POST", "/v1/_projections/rebuild-all"),
    ("GET", "/v1/_projections/{name}"),
    ("POST", "/v1/_projections/{name}/rebuild"),
    ("POST", "/v1/_projections/{name}/cancel"),
    ("POST", "/v1/_projections/{name}/verify"),
    ("DELETE", "/v1/_projections/{name}/reset"),
    ("POST", "/v1/organizations"),
    ("POST", "/v1/organization/subscription/activate"),
}
#: Bodies the routes above validate before the guard would matter — none do;
#: the guard is a dependency and runs first. These are for the two guarded
#: INSIDE their bodies and for the enumerated POSTs' sanity.
BODIES = {
    "/v1/organizations": {"name": "Mole Dairy", "slug": "mole", "country_code": "in"},
    "/v1/organization/subscription/activate": {"plan_code": "growth", "subscribed_centres": 1},
}


def _guarded_routes(app) -> set[tuple[str, str]]:
    """Every (method, path) whose dependency tree holds the platform guard,
    walking the included routers with their prefixes (FastAPI includes a
    router as `_IncludedRouter`)."""

    def walk(router, prefix=""):
        for r in getattr(router, "routes", []):
            if type(r).__name__ == "_IncludedRouter":
                inner = getattr(r.include_context, "prefix", "") or ""
                yield from walk(r.original_router, prefix + inner)
            else:
                yield prefix + getattr(r, "path", ""), r

    found: set[tuple[str, str]] = set()
    for path, route in walk(app):
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        stack = [dependant]
        while stack:
            d = stack.pop()
            if getattr(d.call, "platform_only", False):
                for method in route.methods or []:
                    if method != "HEAD":
                        found.add((method, path))
            stack.extend(d.dependencies)
    return found


async def _compromised_tenant_admin(client):
    """The pre-WO-109 state, planted directly: a tenant-admin's account also
    holding a platform role INSIDE the tenant — `*` from a tenant-bound row."""
    org, admin = await _tenant_admin(client)
    me = (await client.get("/v1/auth/me", headers=admin)).json()
    async with ct.db.get_session_factory()() as session:
        from platform_core.core.rls import bind_platform_context

        await bind_platform_context(session, reason="WO-109 test: plant a bad grant")
        role_id = await session.scalar(
            select(Role.id).where(Role.tenant_id.is_(None), Role.name == "platform-admin")
        )
        session.add(
            UserRole(
                user_id=uuid.UUID(me["user"]["id"]),
                role_id=role_id,
                tenant_id=uuid.UUID(org["id"]),
                center_id=None,
            )
        )
        await session.commit()
    me = (await client.get("/v1/auth/me", headers=admin)).json()
    assert "*" in me["permissions"], "the planted grant is in force — the test is honest"
    return org, admin


async def test_a_tenant_bound_wildcard_is_refused_on_every_platform_route(client, app):
    """(c), enumerated: the app guards exactly the routes listed above, and
    every one refuses a tenant-bound `*` — while the same account still does
    its own tenant's work, and each refusal is a security event."""
    guarded = _guarded_routes(app)
    assert guarded == PLATFORM_ROUTES, {
        "guarded but not listed": sorted(guarded - PLATFORM_ROUTES),
        "listed but not guarded": sorted(PLATFORM_ROUTES - guarded),
    }

    _org, admin = await _compromised_tenant_admin(client)
    sample = {
        "{dead_letter_id}": str(uuid.uuid4()),
        "{event_id}": str(uuid.uuid4()),
        "{execution_id}": str(uuid.uuid4()),
        "{name}": "supplier_directory",
    }
    for method, template in sorted(PLATFORM_ROUTES):
        path = template
        for key, value in sample.items():
            path = path.replace(key, value)
        r = await client.request(method, path, json=BODIES.get(template), headers=admin)
        assert r.status_code == 403, (method, path, r.status_code, r.text[:200])
    # Guarded inside its body: a GLOBAL configuration write.
    r = await client.put(
        "/v1/config/wo109.key", json={"value": 1, "scope": "global"}, headers=admin
    )
    assert r.status_code == 403, r.text
    r = await client.put(
        "/v1/config/wo109.key", json={"value": 1, "scope": "tenant"}, headers=admin
    )
    assert r.status_code == 200, r.text
    # The same account still does its tenant's own work.
    assert (await client.get("/v1/customers", headers=admin)).status_code == 200
    # No `platform.*` permission is guarded by the plain dependency any more.
    routes_source = inspect.getsource(routes_module)
    assert 'require_permission("platform.' not in routes_source
    assert 'require_permission("organization.manage")' not in routes_source


async def test_the_audit_command_finds_what_wo109_forbids(client):
    org, _admin = await _compromised_tenant_admin(client)
    async with ct.db.get_session_factory()() as session:
        from platform_core.core.rls import bind_platform_context
        from platform_core.modules.organization.models import Invitation

        await bind_platform_context(session, reason="WO-109 test: plant an invitation")
        session.add(
            Invitation(
                tenant_id=uuid.UUID(org["id"]),
                email="mole@kilima.example",
                role_name="platform-admin",
                token_hash="0" * 64,
                invited_by=uuid.uuid4(),
                expires_at=ct.utcnow_for_tests()
                if hasattr(ct, "utcnow_for_tests")
                else __import__("platform_core.core.db", fromlist=["utcnow"]).utcnow(),
            )
        )
        await session.commit()
        findings = await find_platform_grants(session)
    kinds = sorted(f.kind for f in findings)
    assert kinds == ["grant", "invitation"], findings
    assert all(f.tenant_id == org["id"] for f in findings)
    text = render(findings)
    assert "incident" in text and "Remedy" in text and "platform-admin" in text
    assert render([]).startswith("WO-109 audit: nothing found")
