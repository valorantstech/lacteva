"""Collection center facility management: lifecycle, hours, calendar, search."""

import uuid

from tests.conftest import invite
from tests.test_org_structure import _tenant_admin


async def _center_fixture(client):
    """Tenant admin + a workspace/branch + one center; returns (headers, branch, center)."""
    _, headers = await _tenant_admin(client)
    ws = (
        await client.post(
            "/v1/workspaces", json={"name": "Northern", "slug": "northern"}, headers=headers
        )
    ).json()
    branch = (
        await client.post(
            "/v1/branches",
            json={"workspace_id": ws["id"], "name": "Kilima Hill", "code": "KH"},
            headers=headers,
        )
    ).json()
    center = (
        await client.post(
            "/v1/collection-centers",
            json={"branch_id": branch["id"], "name": "Kilima Hill Center", "code": "KH-C1"},
            headers=headers,
        )
    ).json()
    return headers, branch, center


async def test_center_belongs_to_existing_branch(client):
    _, headers = await _tenant_admin(client)
    r = await client.post(
        "/v1/collection-centers",
        json={"branch_id": str(uuid.uuid4()), "name": "Orphan", "code": "OR-1"},
        headers=headers,
    )
    assert r.status_code == 404


async def test_center_starts_inactive_and_code_is_unique(client, bus):
    headers, branch, center = await _center_fixture(client)
    assert center["status"] == "inactive"
    r = await client.post(
        "/v1/collection-centers",
        json={"branch_id": branch["id"], "name": "Duplicate", "code": "KH-C1"},
        headers=headers,
    )
    assert r.status_code == 409
    assert "collection.center-created.v1" in [e.type for e in bus.published]


async def test_activation_requires_operating_hours(client, bus):
    headers, _, center = await _center_fixture(client)
    cid = center["id"]
    r = await client.post(
        f"/v1/collection-centers/{cid}/status", json={"status": "active"}, headers=headers
    )
    assert r.status_code == 409  # no operating hours yet

    r = await client.put(
        f"/v1/collection-centers/{cid}/operating-hours",
        json={
            "windows": [
                {"day_of_week": 0, "opens": "06:00", "closes": "09:30"},
                {"day_of_week": 0, "opens": "16:00", "closes": "18:30"},
            ]
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/v1/collection-centers/{cid}/status", json={"status": "active"}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"
    assert "collection.center-status-changed.v1" in [e.type for e in bus.published]


async def test_overlapping_windows_rejected(client):
    headers, _, center = await _center_fixture(client)
    r = await client.put(
        f"/v1/collection-centers/{center['id']}/operating-hours",
        json={
            "windows": [
                {"day_of_week": 1, "opens": "06:00", "closes": "10:00"},
                {"day_of_week": 1, "opens": "09:00", "closes": "12:00"},
            ]
        },
        headers=headers,
    )
    assert r.status_code == 409


async def test_archived_is_terminal(client):
    headers, _, center = await _center_fixture(client)
    cid = center["id"]
    for target, expected in (("maintenance", 200), ("archived", 200), ("active", 409)):
        r = await client.post(
            f"/v1/collection-centers/{cid}/status", json={"status": target}, headers=headers
        )
        assert r.status_code == expected, f"{target}: {r.text}"
    # Archived centers are immutable.
    r = await client.put(
        f"/v1/collection-centers/{cid}",
        json={"name": "New Name", "timezone": "UTC"},
        headers=headers,
    )
    assert r.status_code == 409


async def test_calendar_entries(client):
    headers, _, center = await _center_fixture(client)
    cid = center["id"]
    r = await client.post(
        f"/v1/collection-centers/{cid}/calendar",
        json={"day": "2026-12-25", "kind": "holiday", "note": "Christmas"},
        headers=headers,
    )
    assert r.status_code == 201
    entry = r.json()
    # One entry per day.
    r = await client.post(
        f"/v1/collection-centers/{cid}/calendar",
        json={"day": "2026-12-25", "kind": "closure"},
        headers=headers,
    )
    assert r.status_code == 409
    # Bad kind → validation error.
    r = await client.post(
        f"/v1/collection-centers/{cid}/calendar",
        json={"day": "2026-12-26", "kind": "party"},
        headers=headers,
    )
    assert r.status_code == 422

    detail = (await client.get(f"/v1/collection-centers/{cid}", headers=headers)).json()
    assert len(detail["calendar"]) == 1
    r = await client.delete(f"/v1/collection-centers/{cid}/calendar/{entry['id']}", headers=headers)
    assert r.status_code == 204


async def test_config_and_detail(client):
    headers, branch, center = await _center_fixture(client)
    cid = center["id"]
    r = await client.put(
        f"/v1/collection-centers/{cid}/config",
        json={"settings": {"display_language": "sw", "receipt_footer": "Asante"}},
        headers=headers,
    )
    assert r.status_code == 200
    detail = (await client.get(f"/v1/collection-centers/{cid}", headers=headers)).json()
    assert detail["settings"]["display_language"] == "sw"
    assert detail["center"]["branch_id"] == branch["id"]


async def test_search_and_pagination(client):
    headers, branch, _ = await _center_fixture(client)
    for i in range(2, 6):
        r = await client.post(
            "/v1/collection-centers",
            json={"branch_id": branch["id"], "name": f"Center {i}", "code": f"KH-C{i}"},
            headers=headers,
        )
        assert r.status_code == 201
    page = (await client.get("/v1/collection-centers?limit=2&offset=0", headers=headers)).json()
    assert page["total"] == 5 and len(page["items"]) == 2
    page2 = (await client.get("/v1/collection-centers?limit=2&offset=4", headers=headers)).json()
    assert len(page2["items"]) == 1
    # Search by name and by code fragment.
    hits = (await client.get("/v1/collection-centers?q=center 3", headers=headers)).json()
    assert hits["total"] == 1 and hits["items"][0]["code"] == "KH-C3"
    hits = (await client.get("/v1/collection-centers?q=kh-c", headers=headers)).json()
    assert hits["total"] == 5
    # Status filter.
    hits = (await client.get("/v1/collection-centers?status=active", headers=headers)).json()
    assert hits["total"] == 0


async def test_viewer_can_read_but_not_manage(client):
    headers, branch, center = await _center_fixture(client)
    _inv, inv_token = await invite(
        client,
        headers,
        email="cv@kilima.example",
        role_name="tenant-viewer",
    )
    await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv_token,
            "password": "viewer-password-1",
            "full_name": "Center Viewer",
        },
    )
    assert center["status"] == "inactive"
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    pair = (
        await client.post(
            "/v1/auth/token",
            json={
                "email": "cv@kilima.example",
                "password": "viewer-password-1",
                "tenant_id": me["tenant_id"],
            },
        )
    ).json()
    viewer = {"Authorization": f"Bearer {pair['access_token']}"}
    assert (await client.get("/v1/collection-centers", headers=viewer)).status_code == 200
    r = await client.post(
        "/v1/collection-centers",
        json={"branch_id": branch["id"], "name": "Nope", "code": "NO-1"},
        headers=viewer,
    )
    assert r.status_code == 403
