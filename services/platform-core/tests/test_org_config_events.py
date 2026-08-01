import uuid

from tests.conftest import register_and_login


async def test_create_and_get_organization_emits_event(client, bus):
    _, headers = await register_and_login(client, admin=True)
    r = await client.post(
        "/v1/organizations",
        json={"name": "Kilima Dairy Cooperative", "slug": "kilima", "country_code": "ke"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    org = r.json()
    assert org["country_code"] == "KE"

    r = await client.get(f"/v1/organizations/{org['id']}", headers=headers)
    assert r.status_code == 200

    types = [e.type for e in bus.published]
    assert "organization.organization-created.v1" in types
    created = next(e for e in bus.published if e.type == "organization.organization-created.v1")
    assert created.data["slug"] == "kilima"
    assert created.source == "platform-core"
    assert created.id and created.time


async def test_duplicate_slug_conflicts(client):
    _, headers = await register_and_login(client, admin=True)
    body = {"name": "Amul Cooperative", "slug": "same-slug", "country_code": "in"}
    assert (await client.post("/v1/organizations", json=body, headers=headers)).status_code == 201
    assert (await client.post("/v1/organizations", json=body, headers=headers)).status_code == 409


async def test_config_global_and_tenant_resolution(client):
    _, headers = await register_and_login(client, admin=True)
    # Global value
    r = await client.put(
        "/v1/config/collect.variance-tolerance-percent",
        json={"value": 2.0, "scope": "global"},
        headers=headers,
    )
    assert r.status_code == 200
    r = await client.get("/v1/config/collect.variance-tolerance-percent", headers=headers)
    assert r.status_code == 200
    assert r.json()["value"] == 2.0
    # Unknown key
    assert (await client.get("/v1/config/unknown.key", headers=headers)).status_code == 404


async def test_tenant_config_overrides_global():
    """Service-level: tenant-scoped value shadows the global one."""
    from platform_core.core.db import Base, get_engine, get_session_factory
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.modules.audit.service import AuditService
    from platform_core.modules.configuration.service import ConfigurationService

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    tenant = uuid.uuid4()
    async with get_session_factory()() as session:
        svc = ConfigurationService(session, AuditService(session))
        set_current_tenant(None)
        await svc.set_value("rule.tolerance", 2.0, scope="global", actor_id=None)
        set_current_tenant(tenant)
        assert await svc.resolve("rule.tolerance") == 2.0  # falls back to global
        await svc.set_value("rule.tolerance", 0.5, scope="tenant", actor_id=None)
        assert await svc.resolve("rule.tolerance") == 0.5  # tenant shadows global
        set_current_tenant(None)
        assert await svc.resolve("rule.tolerance") == 2.0  # global unaffected

    from platform_core.core.db import reset_engine

    await reset_engine()
