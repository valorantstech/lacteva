"""Supplier lifecycle, placement, banking, documents, QR, search, import."""

import base64
import uuid

from tests.test_collection_centers import _center_fixture


async def _create_supplier(client, headers, name="Amina Njoroge", **extra):
    r = await client.post(
        "/v1/suppliers",
        json={"full_name": name, "phone": "+254700000001", **extra},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_draft_with_generated_code(client, bus):
    headers, _, _ = await _center_fixture(client)
    supplier = await _create_supplier(client, headers)
    assert supplier["status"] == "draft"
    assert supplier["code"].startswith("S-")
    assert "supplier.supplier-registered.v1" in [e.type for e in bus.published]

    # Explicit code respected; duplicates rejected.
    s2 = await _create_supplier(client, headers, name="Baraka Otieno", code="SUP-77")
    assert s2["code"] == "SUP-77"
    r = await client.post(
        "/v1/suppliers",
        json={"full_name": "Dup", "code": "SUP-77"},
        headers=headers,
    )
    assert r.status_code == 409


async def test_activation_requires_center_assignment(client):
    headers, _, center = await _center_fixture(client)
    supplier = await _create_supplier(client, headers)
    sid = supplier["id"]
    r = await client.post(f"/v1/suppliers/{sid}/status", json={"status": "active"}, headers=headers)
    assert r.status_code == 409  # no center assignment yet

    r = await client.post(
        f"/v1/suppliers/{sid}/centers", json={"center_id": center["id"]}, headers=headers
    )
    assert r.status_code == 201
    r = await client.post(f"/v1/suppliers/{sid}/status", json={"status": "active"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "active"


async def test_supplier_belongs_to_multiple_centers(client, bus):
    headers, branch, center1 = await _center_fixture(client)
    center2 = (
        await client.post(
            "/v1/collection-centers",
            json={"branch_id": branch["id"], "name": "Second Center", "code": "KH-C2"},
            headers=headers,
        )
    ).json()
    supplier = await _create_supplier(client, headers)
    sid = supplier["id"]
    for center in (center1, center2):
        r = await client.post(
            f"/v1/suppliers/{sid}/centers", json={"center_id": center["id"]}, headers=headers
        )
        assert r.status_code == 201
    # Duplicate assignment rejected; unknown center 404.
    r = await client.post(
        f"/v1/suppliers/{sid}/centers", json={"center_id": center1["id"]}, headers=headers
    )
    assert r.status_code == 409
    r = await client.post(
        f"/v1/suppliers/{sid}/centers", json={"center_id": str(uuid.uuid4())}, headers=headers
    )
    assert r.status_code == 404

    detail = (await client.get(f"/v1/suppliers/{sid}", headers=headers)).json()
    assert set(detail["center_ids"]) == {center1["id"], center2["id"]}
    assert "supplier.supplier-assigned-to-center.v1" in [e.type for e in bus.published]

    # Unassign one; searching by the other still finds the supplier.
    r = await client.delete(f"/v1/suppliers/{sid}/centers/{center1['id']}", headers=headers)
    assert r.status_code == 204
    hits = (await client.get(f"/v1/suppliers?center_id={center2['id']}", headers=headers)).json()
    assert hits["total"] == 1


async def test_status_lifecycle_archived_terminal(client):
    headers, _, center = await _center_fixture(client)
    supplier = await _create_supplier(client, headers)
    sid = supplier["id"]
    await client.post(
        f"/v1/suppliers/{sid}/centers", json={"center_id": center["id"]}, headers=headers
    )
    for target, expected in (
        ("suspended", 409),  # draft cannot suspend
        ("active", 200),
        ("suspended", 200),
        ("active", 200),
        ("archived", 200),
        ("active", 409),  # archived is terminal
    ):
        r = await client.post(
            f"/v1/suppliers/{sid}/status", json={"status": target}, headers=headers
        )
        assert r.status_code == expected, f"{target}: {r.text}"
    # Archived suppliers are immutable.
    r = await client.put(f"/v1/suppliers/{sid}", json={"full_name": "New Name"}, headers=headers)
    assert r.status_code == 409


async def test_bank_accounts_masked_and_single_primary(client):
    headers, _, _ = await _center_fixture(client)
    supplier = await _create_supplier(client, headers)
    sid = supplier["id"]
    r = await client.post(
        f"/v1/suppliers/{sid}/bank-accounts",
        json={
            "account_name": "Amina Njoroge",
            "account_number": "0011223344556677",
            "bank_code": "KCB",
            "is_primary": True,
        },
        headers=headers,
    )
    assert r.status_code == 201
    first = r.json()
    assert first["account_number_masked"].endswith("6677")
    assert "0011" not in first["account_number_masked"]

    r = await client.post(
        f"/v1/suppliers/{sid}/bank-accounts",
        json={
            "account_name": "Amina M-Pesa",
            "account_number": "254700000001",
            "bank_code": "MPESA",
            "is_primary": True,
        },
        headers=headers,
    )
    assert r.status_code == 201
    accounts = (await client.get(f"/v1/suppliers/{sid}/bank-accounts", headers=headers)).json()
    primaries = [a for a in accounts if a["is_primary"]]
    assert len(accounts) == 2 and len(primaries) == 1
    assert primaries[0]["bank_code"] == "MPESA"


async def test_documents_roundtrip(client):
    headers, _, _ = await _center_fixture(client)
    supplier = await _create_supplier(client, headers)
    sid = supplier["id"]
    content = base64.b64encode(b"national id scan bytes").decode()
    r = await client.post(
        f"/v1/suppliers/{sid}/documents",
        json={
            "kind": "national_id",
            "file_name": "id-front.jpg",
            "content_type": "image/jpeg",
            "content_base64": content,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    document = r.json()
    docs = (await client.get(f"/v1/suppliers/{sid}/documents", headers=headers)).json()
    assert len(docs) == 1 and docs[0]["kind"] == "national_id"
    r = await client.get(f"/v1/suppliers/{sid}/documents/{document['id']}/url", headers=headers)
    assert r.status_code == 200 and r.json()["url"].startswith("memory://")
    # Invalid base64 and bad kind rejected.
    r = await client.post(
        f"/v1/suppliers/{sid}/documents",
        json={
            "kind": "national_id",
            "file_name": "x.jpg",
            "content_type": "image/jpeg",
            "content_base64": "!!!not-base64!!!",
        },
        headers=headers,
    )
    assert r.status_code == 400
    r = await client.post(
        f"/v1/suppliers/{sid}/documents",
        json={
            "kind": "meme",
            "file_name": "x.jpg",
            "content_type": "image/jpeg",
            "content_base64": content,
        },
        headers=headers,
    )
    assert r.status_code == 422


async def test_qr_roundtrip_and_tamper_rejection(client):
    headers, _, _ = await _center_fixture(client)
    supplier = await _create_supplier(client, headers)
    qr = (await client.get(f"/v1/suppliers/{supplier['id']}/qr", headers=headers)).json()
    assert qr["payload"].startswith("LCT1.") and qr["code"] == supplier["code"]

    r = await client.post(
        "/v1/suppliers/qr/resolve", json={"payload": qr["payload"]}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["id"] == supplier["id"]

    tampered = qr["payload"][:-1] + ("0" if qr["payload"][-1] != "0" else "1")
    r = await client.post("/v1/suppliers/qr/resolve", json={"payload": tampered}, headers=headers)
    assert r.status_code == 400


async def test_search_filters(client):
    headers, branch, center = await _center_fixture(client)
    a = await _create_supplier(client, headers, name="Amina Njoroge")
    await _create_supplier(client, headers, name="Baraka Otieno", branch_id=branch["id"])
    await client.post(
        f"/v1/suppliers/{a['id']}/centers", json={"center_id": center["id"]}, headers=headers
    )

    page = (await client.get("/v1/suppliers?limit=1&offset=0", headers=headers)).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    hits = (await client.get("/v1/suppliers?q=amina", headers=headers)).json()
    assert hits["total"] == 1 and hits["items"][0]["full_name"] == "Amina Njoroge"
    hits = (await client.get("/v1/suppliers?q=%2B254700", headers=headers)).json()
    assert hits["total"] == 2  # phone search
    hits = (await client.get(f"/v1/suppliers?center_id={center['id']}", headers=headers)).json()
    assert hits["total"] == 1
    hits = (await client.get(f"/v1/suppliers?branch_id={branch['id']}", headers=headers)).json()
    assert hits["total"] == 1 and hits["items"][0]["full_name"] == "Baraka Otieno"
    hits = (await client.get("/v1/suppliers?status=draft", headers=headers)).json()
    assert hits["total"] == 2


async def test_import_mixed_results(client, bus):
    headers, _, center = await _center_fixture(client)
    rows = [
        {"full_name": "Import One", "phone": "+254711", "center_codes": [center["code"]]},
        {"full_name": "Import Two", "center_codes": ["NO-SUCH-CENTER"]},
        {"full_name": "X"},  # too short -> validation error inside create
    ]
    r = await client.post("/v1/suppliers/import", json={"rows": rows}, headers=headers)
    assert r.status_code == 200, r.text
    results = r.json()
    assert [x["status"] for x in results] == ["created", "error", "error"]
    assert "unknown center code" in results[1]["error"]
    assert "supplier.supplier-import-completed.v1" in [e.type for e in bus.published]

    # The successful row is active-capable: it has a center assignment.
    sid = results[0]["supplier_id"]
    r = await client.post(f"/v1/suppliers/{sid}/status", json={"status": "active"}, headers=headers)
    assert r.status_code == 200
