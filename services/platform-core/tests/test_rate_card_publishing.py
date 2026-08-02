"""Rate Card publishing: immutability, effective-date overlap, versioning, archive."""

from tests.test_collection_centers import _center_fixture
from tests.test_rate_cards import PRODUCT, _assign_scope, _create_card


async def _second_center(client, headers, branch, code="KH-C2"):
    r = await client.post(
        "/v1/collection-centers",
        json={"branch_id": branch["id"], "name": f"Center {code}", "code": code},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _approve(client, headers, card_id):
    assert (
        await client.post(f"/v1/rate-cards/{card_id}/submit", headers=headers)
    ).status_code == 200
    assert (
        await client.post(f"/v1/rate-cards/{card_id}/approve", headers=headers)
    ).status_code == 200


async def _published(client, headers, center_id, *, product=PRODUCT, **overrides):
    card = await _create_card(client, headers, **overrides)
    await _assign_scope(client, headers, card["id"], center_id, product=product)
    await _approve(client, headers, card["id"])
    r = await client.post(f"/v1/rate-cards/{card['id']}/publish", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# --- publishing --------------------------------------------------------------


async def test_publish_happy_path(client, bus):
    headers, _, center = await _center_fixture(client)
    card = await _published(client, headers, center["id"])
    assert card["status"] == "published"
    assert card["published_at"] is not None
    assert "pricing.rate-card-published.v1" in [e.type for e in bus.published]


async def test_publish_requires_approved(client):
    headers, _, center = await _center_fixture(client)
    card = await _create_card(client, headers)
    await _assign_scope(client, headers, card["id"], center["id"])
    r = await client.post(f"/v1/rate-cards/{card['id']}/publish", headers=headers)
    assert r.status_code == 409  # draft
    await client.post(f"/v1/rate-cards/{card['id']}/submit", headers=headers)
    r = await client.post(f"/v1/rate-cards/{card['id']}/publish", headers=headers)
    assert r.status_code == 409  # under_review


async def test_publish_requires_center_assignment(client):
    headers, _, _ = await _center_fixture(client)
    card = await _create_card(client, headers)
    await client.post(
        f"/v1/rate-cards/{card['id']}/products", json={"product_code": PRODUCT}, headers=headers
    )
    await _approve(client, headers, card["id"])
    r = await client.post(f"/v1/rate-cards/{card['id']}/publish", headers=headers)
    assert r.status_code == 409
    assert "collection center" in r.json()["extra"]


async def test_publish_requires_product_assignment(client):
    headers, _, center = await _center_fixture(client)
    card = await _create_card(client, headers)
    await client.post(
        f"/v1/rate-cards/{card['id']}/centers", json={"center_id": center["id"]}, headers=headers
    )
    await _approve(client, headers, card["id"])
    r = await client.post(f"/v1/rate-cards/{card['id']}/publish", headers=headers)
    assert r.status_code == 409
    assert "product" in r.json()["extra"]


async def test_published_card_is_immutable(client):
    headers, _, center = await _center_fixture(client)
    card = await _published(client, headers, center["id"])
    cid = card["id"]
    r = await client.put(
        f"/v1/rate-cards/{cid}",
        json={"name": "Mutate", "currency": "KES", "effective_from": "2026-09-01"},
        headers=headers,
    )
    assert r.status_code == 409
    r = await client.post(
        f"/v1/rate-cards/{cid}/centers", json={"center_id": center["id"]}, headers=headers
    )
    assert r.status_code == 409
    r = await client.post(
        f"/v1/rate-cards/{cid}/products", json={"product_code": "GOAT-MILK"}, headers=headers
    )
    assert r.status_code == 409
    r = await client.post(f"/v1/rate-cards/{cid}/submit", headers=headers)
    assert r.status_code == 409


# --- effective-date overlap rule --------------------------------------------


async def test_overlap_same_scope_rejected(client):
    headers, _, center = await _center_fixture(client)
    await _published(
        client,
        headers,
        center["id"],
        code="SEASON-A",
        effective_from="2026-09-01",
        effective_until="2027-08-31",
    )
    second = await _create_card(
        client, headers, code="SEASON-B", effective_from="2027-01-01", effective_until="2027-12-31"
    )
    await _assign_scope(client, headers, second["id"], center["id"])
    await _approve(client, headers, second["id"])
    r = await client.post(f"/v1/rate-cards/{second['id']}/publish", headers=headers)
    assert r.status_code == 409
    assert "overlap" in r.json()["extra"]
    # The failed publish leaves the card approved, not published.
    detail = (await client.get(f"/v1/rate-cards/{second['id']}", headers=headers)).json()
    assert detail["card"]["status"] == "approved"


async def test_non_overlapping_ranges_both_publish(client):
    headers, _, center = await _center_fixture(client)
    await _published(
        client,
        headers,
        center["id"],
        code="Y-2026",
        effective_from="2026-09-01",
        effective_until="2027-08-31",
    )
    second = await _published(
        client,
        headers,
        center["id"],
        code="Y-2027",
        effective_from="2027-09-01",
        effective_until="2028-08-31",
    )
    assert second["status"] == "published"


async def test_same_center_different_product_publishes(client):
    headers, _, center = await _center_fixture(client)
    await _published(client, headers, center["id"], code="COW", product="RAW-COW-MILK")
    goat = await _published(client, headers, center["id"], code="GOAT", product="RAW-GOAT-MILK")
    assert goat["status"] == "published"


async def test_same_product_different_center_publishes(client):
    headers, branch, center1 = await _center_fixture(client)
    center2 = await _second_center(client, headers, branch)
    await _published(client, headers, center1["id"], code="NORTH")
    south = await _published(client, headers, center2["id"], code="SOUTH")
    assert south["status"] == "published"


async def test_open_ended_card_blocks_future_ranges(client):
    headers, _, center = await _center_fixture(client)
    await _published(
        client, headers, center["id"], code="FOREVER", effective_from="2026-09-01"
    )  # no effective_until: applies forever
    later = await _create_card(
        client, headers, code="LATER", effective_from="2030-01-01", effective_until="2030-12-31"
    )
    await _assign_scope(client, headers, later["id"], center["id"])
    await _approve(client, headers, later["id"])
    r = await client.post(f"/v1/rate-cards/{later['id']}/publish", headers=headers)
    assert r.status_code == 409


# --- versioning --------------------------------------------------------------


async def test_new_version_copies_fields_and_scope(client, bus):
    headers, _, center = await _center_fixture(client)
    v1 = await _published(client, headers, center["id"], code="STD", name="Season 26/27")
    r = await client.post(f"/v1/rate-cards/{v1['id']}/versions", headers=headers)
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["code"] == "STD" and v2["version"] == 2 and v2["status"] == "draft"
    assert v2["name"] == "Season 26/27" and v2["currency"] == v1["currency"]
    detail = (await client.get(f"/v1/rate-cards/{v2['id']}", headers=headers)).json()
    assert detail["center_ids"] == [center["id"]]
    assert detail["products"][0]["product_code"] == PRODUCT


async def test_new_version_leaves_history_untouched(client):
    headers, _, center = await _center_fixture(client)
    v1 = await _published(client, headers, center["id"], code="HIST", name="Original")
    v2 = (await client.post(f"/v1/rate-cards/{v1['id']}/versions", headers=headers)).json()
    r = await client.put(
        f"/v1/rate-cards/{v2['id']}",
        json={"name": "Rewritten", "currency": "KES", "effective_from": "2027-09-01"},
        headers=headers,
    )
    assert r.status_code == 200
    # Historical version is never updated.
    old = (await client.get(f"/v1/rate-cards/{v1['id']}", headers=headers)).json()["card"]
    assert old["name"] == "Original" and old["status"] == "published" and old["version"] == 1


async def test_new_version_requires_published_or_archived(client):
    headers, _, _ = await _center_fixture(client)
    draft = await _create_card(client, headers)
    r = await client.post(f"/v1/rate-cards/{draft['id']}/versions", headers=headers)
    assert r.status_code == 409


async def test_only_one_open_version_per_code(client):
    headers, _, center = await _center_fixture(client)
    v1 = await _published(client, headers, center["id"], code="ONE")
    assert (
        await client.post(f"/v1/rate-cards/{v1['id']}/versions", headers=headers)
    ).status_code == 201
    r = await client.post(f"/v1/rate-cards/{v1['id']}/versions", headers=headers)
    assert r.status_code == 409  # v2 draft still open


async def test_new_version_overlap_resolved_by_archiving_predecessor(client):
    headers, _, center = await _center_fixture(client)
    v1 = await _published(client, headers, center["id"], code="ROLL", effective_from="2026-09-01")
    v2 = (await client.post(f"/v1/rate-cards/{v1['id']}/versions", headers=headers)).json()
    await _approve(client, headers, v2["id"])
    r = await client.post(f"/v1/rate-cards/{v2['id']}/publish", headers=headers)
    assert r.status_code == 409  # same dates as v1 -> overlap on same scope
    r = await client.post(f"/v1/rate-cards/{v1['id']}/archive", headers=headers)
    assert r.status_code == 200
    r = await client.post(f"/v1/rate-cards/{v2['id']}/publish", headers=headers)
    assert r.status_code == 200, r.text
    # Both versions still exist: history preserved.
    page = (await client.get("/v1/rate-cards?q=ROLL", headers=headers)).json()
    assert page["total"] == 2
    assert {c["version"]: c["status"] for c in page["items"]} == {1: "archived", 2: "published"}


async def test_duplicate_code_blocked_even_after_archive(client):
    headers, _, center = await _center_fixture(client)
    v1 = await _published(client, headers, center["id"], code="KEEP")
    await client.post(f"/v1/rate-cards/{v1['id']}/archive", headers=headers)
    r = await client.post(
        "/v1/rate-cards",
        json={"name": "Reuse", "currency": "KES", "effective_from": "2026-09-01", "code": "KEEP"},
        headers=headers,
    )
    assert r.status_code == 409  # history is preserved; use a new version instead


# --- archive -----------------------------------------------------------------


async def test_archive_draft_and_terminal(client, bus):
    headers, _, _ = await _center_fixture(client)
    card = await _create_card(client, headers)
    r = await client.post(f"/v1/rate-cards/{card['id']}/archive", headers=headers)
    assert r.status_code == 200
    archived = r.json()
    assert archived["status"] == "archived" and archived["archived_at"] is not None
    assert "pricing.rate-card-archived.v1" in [e.type for e in bus.published]
    for action in ("archive", "submit", "approve", "publish"):
        r = await client.post(f"/v1/rate-cards/{card['id']}/{action}", headers=headers)
        assert r.status_code == 409, action
    r = await client.put(
        f"/v1/rate-cards/{card['id']}",
        json={"name": "Zombie", "currency": "KES", "effective_from": "2026-09-01"},
        headers=headers,
    )
    assert r.status_code == 409


async def test_archive_published_preserves_history(client):
    headers, _, center = await _center_fixture(client)
    card = await _published(client, headers, center["id"], code="RETIRE")
    r = await client.post(f"/v1/rate-cards/{card['id']}/archive", headers=headers)
    assert r.status_code == 200
    detail = (await client.get(f"/v1/rate-cards/{card['id']}", headers=headers)).json()
    assert detail["card"]["status"] == "archived"
    assert detail["card"]["published_at"] is not None  # publication history retained
    assert detail["center_ids"] == [center["id"]]  # scope retained
    hits = (await client.get("/v1/rate-cards?status=archived", headers=headers)).json()
    assert hits["total"] == 1


async def test_active_on_filter(client):
    headers, _, center = await _center_fixture(client)
    await _published(
        client,
        headers,
        center["id"],
        code="ACT",
        effective_from="2026-09-01",
        effective_until="2027-08-31",
    )
    await _create_card(client, headers, code="DRAFT-ONLY", effective_from="2026-09-01")
    hits = (await client.get("/v1/rate-cards?active_on=2027-01-15", headers=headers)).json()
    assert hits["total"] == 1 and hits["items"][0]["code"] == "ACT"
    hits = (await client.get("/v1/rate-cards?active_on=2028-01-15", headers=headers)).json()
    assert hits["total"] == 0


# --- domain events -----------------------------------------------------------


async def test_full_lifecycle_emits_all_events(client, bus):
    headers, _, center = await _center_fixture(client)
    card = await _published(client, headers, center["id"], code="EVT")
    await client.post(f"/v1/rate-cards/{card['id']}/archive", headers=headers)
    types = {e.type for e in bus.published}
    assert {
        "pricing.rate-card-created.v1",
        "pricing.rate-card-updated.v1",  # scope assignments
        "pricing.rate-card-submitted.v1",
        "pricing.rate-card-approved.v1",
        "pricing.rate-card-published.v1",
        "pricing.rate-card-archived.v1",
    } <= types
    # Envelopes carry aggregate metadata for the relay/consumers.
    published = next(e for e in bus.published if e.type == "pricing.rate-card-published.v1")
    assert published.aggregate_type == "rate_card"
    assert str(published.aggregate_id) == card["id"]
    assert published.data["code"] == "EVT" and published.data["status"] == "published"
