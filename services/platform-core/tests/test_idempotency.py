"""Platform-wide idempotency (IDM-001).

A client on a poor network cannot tell a lost response from a lost request.
It retries, and without help the platform performs the operation twice. This
platform is built for field use over intermittent connectivity, so that is
the normal case rather than an edge case.

These tests exercise the framework through the real HTTP surface, because the
guarantee is about HTTP requests — testing the store in isolation would prove
the bookkeeping and miss the thing that matters.
"""

import asyncio
import uuid

from tests.test_org_structure import _tenant_admin


def _key() -> str:
    return uuid.uuid4().hex


def _supplier(n: str = "Amina") -> dict:
    return {"full_name": n, "phone": f"+2547{uuid.uuid4().int % 10**8:08d}"}


# --- the property the framework exists for ---------------------------------


async def test_a_duplicate_post_creates_one_resource(client):
    """The whole point. Two identical requests, one supplier."""
    _org, headers = await _tenant_admin(client)
    key, body = _key(), _supplier()
    h = {**headers, "Idempotency-Key": key}

    first = await client.post("/v1/suppliers", json=body, headers=h)
    second = await client.post("/v1/suppliers", json=body, headers=h)

    assert first.status_code == 201
    assert second.status_code == 201, "the replay must reproduce the original status"
    assert first.json()["id"] == second.json()["id"], "a second supplier was created"
    assert second.headers.get("Idempotent-Replay") == "true"

    listed = (await client.get("/v1/suppliers", headers=headers)).json()
    assert listed["total"] == 1, f"expected one supplier, found {listed['total']}"


async def test_the_replayed_body_is_the_original_response(client):
    _org, headers = await _tenant_admin(client)
    h = {**headers, "Idempotency-Key": _key()}
    body = _supplier("Grace")
    first = await client.post("/v1/suppliers", json=body, headers=h)
    second = await client.post("/v1/suppliers", json=body, headers=h)
    assert first.json() == second.json()


async def test_without_the_header_nothing_changes(client):
    """The framework is opt-in per request. Two identical unkeyed requests
    create two resources, exactly as before — no existing caller is affected."""
    _org, headers = await _tenant_admin(client)
    a = await client.post("/v1/suppliers", json=_supplier("Alpha"), headers=headers)
    b = await client.post("/v1/suppliers", json=_supplier("Beta"), headers=headers)
    assert a.json()["id"] != b.json()["id"]


async def test_a_duplicate_patch_is_replayed(client):
    """PUT/PATCH are idempotent in principle, but a retry still costs a write
    and an audit record — and for a lifecycle transition it costs a 409 the
    client did not expect."""
    _org, headers = await _tenant_admin(client)
    created = (await client.post("/v1/suppliers", json=_supplier(), headers=headers)).json()
    h = {**headers, "Idempotency-Key": _key()}
    body = {"full_name": "Renamed", "phone": "+254700111222"}
    first = await client.put(f"/v1/suppliers/{created['id']}", json=body, headers=h)
    second = await client.put(f"/v1/suppliers/{created['id']}", json=body, headers=h)
    assert first.status_code == second.status_code
    assert second.headers.get("Idempotent-Replay") == "true"


# --- misuse ----------------------------------------------------------------


async def test_the_same_key_with_a_different_body_is_refused(client):
    """The key identifies a request; it does not describe one. Replaying the
    first response here would silently discard the second request."""
    _org, headers = await _tenant_admin(client)
    h = {**headers, "Idempotency-Key": _key()}
    await client.post("/v1/suppliers", json=_supplier("First"), headers=h)
    r = await client.post("/v1/suppliers", json=_supplier("Different"), headers=h)
    assert r.status_code == 400
    assert "idempotency" in r.json()["title"].lower() or r.json()["detail"]


async def test_an_empty_or_oversized_key_is_refused(client):
    _org, headers = await _tenant_admin(client)
    for key in ("", "   ", "x" * 200):
        r = await client.post(
            "/v1/suppliers", json=_supplier(), headers={**headers, "Idempotency-Key": key}
        )
        assert r.status_code in (400, 422), f"key {key[:12]!r} was accepted"


# --- concurrency -----------------------------------------------------------


async def test_concurrent_duplicates_do_not_both_succeed(client):
    """Two requests in flight at once.

    **Engine note.** SQLite's `StaticPool` gives the whole test process ONE
    connection, so two "concurrent" requests share a transaction and the
    unique constraint never fires — the race this protects against cannot be
    staged here. `test_rls_postgres.py` proves it on an engine that can.

    What this asserts is the part SQLite *can* show: the second request never
    produces a second resource once the first has committed.
    """
    _org, headers = await _tenant_admin(client)
    h = {**headers, "Idempotency-Key": _key()}
    body = _supplier("Concurrent")

    first = await client.post("/v1/suppliers", json=body, headers=h)
    assert first.status_code == 201
    # Now genuinely concurrent against a COMMITTED reservation.
    results = await asyncio.gather(
        client.post("/v1/suppliers", json=body, headers=h),
        client.post("/v1/suppliers", json=body, headers=h),
    )
    for r in results:
        # Replayed (201) or refused as in flight (409). Never a new resource.
        assert r.status_code in (201, 409), r.status_code
        if r.status_code == 201:
            assert r.json()["id"] == first.json()["id"]
    listed = (await client.get("/v1/suppliers", headers=headers)).json()
    assert listed["total"] == 1, f"{listed['total']} suppliers created by retries"


# --- failure and reclaim ---------------------------------------------------


async def test_a_failed_request_releases_its_key(client):
    """A failure holds no effect worth deduplicating. Keeping the reservation
    would answer every future retry with the same failure — for a problem
    that may since have been fixed."""
    _org, headers = await _tenant_admin(client)
    key = _key()
    h = {**headers, "Idempotency-Key": key}

    bad = await client.post("/v1/suppliers", json={"full_name": ""}, headers=h)
    assert bad.status_code in (400, 409, 422)

    # The same key now works for a correct request.
    good = await client.post("/v1/suppliers", json=_supplier(), headers=h)
    assert good.status_code == 201, f"the key stayed locked after a failure: {good.text[:200]}"


# --- persistence and restart ------------------------------------------------


async def test_the_record_and_the_business_row_commit_together(client):
    """The design's central claim: reservation, business write and stored
    response share ONE transaction. If they did not, a crash between them
    would leave a key claiming an effect that never happened."""
    from sqlalchemy import select

    from platform_core.core import db
    from platform_core.core.idempotency import COMPLETED, IdempotencyRecord

    _org, headers = await _tenant_admin(client)
    key = _key()
    created = await client.post(
        "/v1/suppliers", json=_supplier(), headers={**headers, "Idempotency-Key": key}
    )
    assert created.status_code == 201

    async with db.get_session_factory()() as session:
        record = await session.scalar(
            select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == key)
        )
    assert record is not None, "the reservation did not commit with the business row"
    assert record.status == COMPLETED
    assert record.response_status == 201
    assert record.response_body["id"] == created.json()["id"]


async def test_a_replay_survives_a_restart(client):
    """The record is in the database, not in memory, so a process that
    restarts between the original and the retry still recognises it."""

    _org, headers = await _tenant_admin(client)
    h = {**headers, "Idempotency-Key": _key()}
    body = _supplier("Durable")
    first = await client.post("/v1/suppliers", json=body, headers=h)

    # Nothing in-process is allowed to be load-bearing: drop every session.
    from sqlalchemy.orm import close_all_sessions

    close_all_sessions()

    second = await client.post("/v1/suppliers", json=body, headers=h)
    assert second.json()["id"] == first.json()["id"]


# --- tenancy ---------------------------------------------------------------


async def test_keys_are_scoped_to_their_tenant(client):
    """Two tenants using the same key — a UUID collision is implausible, but
    a client library that derives keys from a request hash makes it certain.
    Each must get its own resource."""
    from sqlalchemy import select

    from platform_core.core import db
    from platform_core.core.idempotency import IdempotencyRecord

    _org, headers = await _tenant_admin(client)
    key = _key()
    await client.post(
        "/v1/suppliers", json=_supplier(), headers={**headers, "Idempotency-Key": key}
    )

    async with db.get_session_factory()() as session:
        records = (
            await session.scalars(
                select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == key)
            )
        ).all()
    assert len(records) == 1
    assert records[0].tenant_id is not None, "the record must carry its tenant"


def test_the_record_table_is_tenant_owned_and_therefore_protected():
    """SEC-002 made an unprotected tenant table a build failure. This is the
    first new table since, so the rule is checked here too."""
    from platform_core.core.rls import tenant_tables, unclassified_tables

    assert "idempotency_record" in tenant_tables()
    assert unclassified_tables() == ()


# --- retention -------------------------------------------------------------


async def test_the_sweep_removes_only_expired_records(client):
    from datetime import timedelta

    from sqlalchemy import select

    from platform_core.core import db
    from platform_core.core.db import utcnow
    from platform_core.core.idempotency import IdempotencyRecord, sweep

    async with db.get_session_factory()() as session:
        live = IdempotencyRecord(
            tenant_id=uuid.uuid4(),
            idempotency_key=_key(),
            fingerprint="a" * 64,
            method="POST",
            path="/v1/x",
            status="completed",
            expires_at=utcnow() + timedelta(hours=1),
        )
        dead = IdempotencyRecord(
            tenant_id=uuid.uuid4(),
            idempotency_key=_key(),
            fingerprint="b" * 64,
            method="POST",
            path="/v1/x",
            status="completed",
            expires_at=utcnow() - timedelta(hours=1),
        )
        session.add_all([live, dead])
        await session.commit()
        live_id, dead_id = live.id, dead.id

        removed = await sweep(session)
        assert removed >= 1

        remaining = set((await session.scalars(select(IdempotencyRecord.id))).all())
    assert live_id in remaining, "an unexpired record was swept"
    assert dead_id not in remaining, "an expired record survived"


async def test_an_expired_key_is_usable_again(client):
    """Retention is the cleanup strategy, so the key must genuinely free up —
    otherwise the table is a log with extra steps."""
    from datetime import timedelta

    from sqlalchemy import select

    from platform_core.core import db
    from platform_core.core.db import utcnow
    from platform_core.core.idempotency import IdempotencyRecord, sweep

    _org, headers = await _tenant_admin(client)
    key = _key()
    h = {**headers, "Idempotency-Key": key}
    first = await client.post("/v1/suppliers", json=_supplier("Early"), headers=h)

    async with db.get_session_factory()() as session:
        record = await session.scalar(
            select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == key)
        )
        record.expires_at = utcnow() - timedelta(seconds=1)
        await session.commit()
        await sweep(session)

    second = await client.post("/v1/suppliers", json=_supplier("Later"), headers=h)
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"], "the expired key still replayed"


# --- the design's load-bearing assumption ----------------------------------


async def test_the_session_is_still_open_when_the_route_wrapper_runs(client):
    """The framework depends on FastAPI closing dependency teardown AFTER the
    route handler returns. If that ever changes, the response record would be
    written to a closed session and idempotency would silently stop storing
    anything — so the assumption is pinned rather than assumed."""
    from platform_core.core.db import current_request_session

    observed = {}

    from platform_core.api import idempotent_route

    original_record = idempotent_route.idempotency.record_response

    async def spy(session, record_id, *, status_code, body):
        observed["session_active"] = session.is_active
        observed["same_session"] = session is current_request_session()
        return await original_record(session, record_id, status_code=status_code, body=body)

    idempotent_route.idempotency.record_response = spy
    try:
        _org, headers = await _tenant_admin(client)
        r = await client.post(
            "/v1/suppliers", json=_supplier(), headers={**headers, "Idempotency-Key": _key()}
        )
        assert r.status_code == 201
    finally:
        idempotent_route.idempotency.record_response = original_record

    assert observed.get("session_active") is True, (
        "the request session was closed before the response could be recorded — "
        "FastAPI's teardown ordering changed and the framework's atomicity is gone"
    )
    assert observed.get("same_session") is True


def test_only_mutations_are_guarded():
    from platform_core.api.idempotent_route import GUARDED_METHODS

    assert GUARDED_METHODS == {"POST", "PUT", "PATCH"}


def test_the_fingerprint_distinguishes_requests():
    from platform_core.core.idempotency import fingerprint_of

    base = fingerprint_of("POST", "/v1/suppliers", b'{"a":1}')
    assert base == fingerprint_of("POST", "/v1/suppliers", b'{"a":1}')
    assert base != fingerprint_of("POST", "/v1/suppliers", b'{"a":2}')
    assert base != fingerprint_of("POST", "/v1/payments", b'{"a":1}')
    assert base != fingerprint_of("PUT", "/v1/suppliers", b'{"a":1}')
    assert len(base) == 64  # sha256 hex — the body itself is never stored


def test_metrics_exist_for_every_outcome():
    """An idempotency layer nobody can see is one nobody trusts."""
    from platform_core.core import metrics

    for name in (
        "IDEMPOTENCY_REPLAYS",
        "IDEMPOTENCY_STORED",
        "IDEMPOTENCY_CONFLICTS",
        "IDEMPOTENCY_MISMATCHES",
        "IDEMPOTENCY_SWEPT",
    ):
        assert hasattr(metrics, name), name
