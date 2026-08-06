"""REST API contract (API-001).

Reviewed as if preparing a public SaaS release, which changes what counts as
a defect. Internally, an undocumented error response is untidy. Published, it
means every generated client treats an error body as an unknown shape and
every integrator learns the real contract by causing errors in production.

These tests assert the contract itself — the OpenAPI document a client is
generated from — rather than any single handler. A rule enforced per-route is
a rule that drifts silently; a rule enforced over the whole document cannot.
"""

import uuid

import pytest


@pytest.fixture(scope="module")
def spec():
    from platform_core.main import create_app

    return create_app().openapi()


def _operations(spec):
    return [
        (method.upper(), path, op)
        for path, methods in spec["paths"].items()
        for method, op in methods.items()
    ]


# --- the error contract ----------------------------------------------------


def test_the_error_shape_is_published(spec):
    """The platform has always RETURNED RFC 9457 problem details. Until
    API-001 it never documented them."""
    schema = spec["components"]["schemas"]["ProblemDetail"]
    assert set(schema["properties"]) >= {"type", "title", "status", "detail", "extra"}


def test_every_v1_operation_documents_the_universal_errors(spec):
    """401, 403, 422 and 429 are reachable from any operation. A client that
    cannot see them in the schema cannot generate handling for them."""
    missing = []
    for method, path, op in _operations(spec):
        if not path.startswith("/v1"):
            continue
        declared = set(op.get("responses", {}))
        for code in ("401", "403", "422", "429"):
            if code not in declared:
                missing.append(f"{method} {path} lacks {code}")
    assert missing == [], missing[:10]


def test_operations_that_address_a_resource_document_404(spec):
    missing = [
        f"{m} {p}"
        for m, p, op in _operations(spec)
        if p.startswith("/v1") and "{" in p and "404" not in op.get("responses", {})
    ]
    assert missing == [], missing[:10]


def test_mutating_operations_document_409(spec):
    """A duplicate unique value or a refused state transition. Retrying it
    unchanged will fail identically, and a client should know that."""
    missing = [
        f"{m} {p}"
        for m, p, op in _operations(spec)
        if p.startswith("/v1")
        and m in {"POST", "PUT", "PATCH", "DELETE"}
        and "409" not in op.get("responses", {})
    ]
    assert missing == [], missing[:10]


def test_error_responses_use_the_problem_media_type(spec):
    """`application/problem+json` is what the handlers actually send. A schema
    that claims `application/json` would be a documented lie."""
    for method, path, op in _operations(spec):
        if not path.startswith("/v1"):
            continue
        body = op.get("responses", {}).get("403", {})
        assert "application/problem+json" in body.get("content", {}), f"{method} {path}"


async def test_a_real_error_matches_its_documented_shape(client):
    """The contract is only worth publishing if the runtime honours it."""
    r = await client.get("/v1/suppliers")  # no credentials
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert set(body) >= {"type", "title", "status", "detail"}
    assert body["status"] == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"


async def test_a_rate_limited_response_says_when_to_come_back(client):
    """429 without `Retry-After` makes every client guess, and they guess
    aggressively."""
    from platform_core.core.errors import UNIVERSAL_PROBLEMS

    assert "Retry-After" in UNIVERSAL_PROBLEMS[429]["description"]


# --- list semantics --------------------------------------------------------

#: A list whose length grows with business volume MUST be paginated. A list
#: bounded by structure (a tenant's workspaces, a supplier's bank accounts)
#: may be a bare array — that is the rule this suite enforces, rather than
#: "everything must paginate", which would add ceremony to fixed-size lists.
UNBOUNDED_LISTS = {
    "/v1/collection-sessions",
    "/v1/milk-transactions",
    "/v1/suppliers",
    "/v1/settlements",
    "/v1/payments",
    "/v1/receipts",
    "/v1/notifications",
    "/v1/sync/operations",
    "/v1/collection-centers",
    "/v1/devices",
    "/v1/rate-cards",
    "/v1/pricing-matrices",
}


def test_every_list_that_grows_with_business_volume_is_paginated(spec):
    """The failure this prevents is gradual: a response that is fine in
    month one and a timeout in year two, with nothing in between to notice."""
    unpaginated = []
    for path in UNBOUNDED_LISTS:
        op = spec["paths"][path]["get"]
        schema = op["responses"]["200"]["content"]["application/json"]["schema"]
        if "$ref" not in schema:
            unpaginated.append(path)
            continue
        model = spec["components"]["schemas"][schema["$ref"].split("/")[-1]]
        if not {"items", "total", "limit", "offset"} <= set(model["properties"]):
            unpaginated.append(path)
    assert unpaginated == [], f"unbounded lists without a page envelope: {unpaginated}"


def test_paginated_endpoints_cap_their_page_size(spec):
    """A `limit` a client can set to 100000 is not a limit."""
    uncapped = []
    for path in UNBOUNDED_LISTS:
        params = {q["name"]: q for q in spec["paths"][path]["get"].get("parameters", [])}
        limit = params.get("limit")
        if limit is None or limit.get("schema", {}).get("maximum") is None:
            uncapped.append(path)
    assert uncapped == [], f"page size not capped: {uncapped}"


async def test_the_session_list_pages_and_reports_a_total(client):
    from tests.test_org_structure import _tenant_admin

    _org, headers = await _tenant_admin(client)
    r = await client.get("/v1/collection-sessions?limit=1", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"items", "total", "limit", "offset"}
    assert body["limit"] == 1


async def test_a_page_size_above_the_cap_is_rejected_not_silently_clamped(client):
    """Silently clamping teaches a client that its request succeeded when it
    did not, and the truncation is discovered as missing data."""
    from tests.test_org_structure import _tenant_admin

    _org, headers = await _tenant_admin(client)
    r = await client.get("/v1/collection-sessions?limit=5000", headers=headers)
    assert r.status_code == 422


# --- retry safety ----------------------------------------------------------


def test_payment_creation_accepts_the_conventional_idempotency_header(spec):
    """Paying twice is the worst outcome this API has, and a mobile client on
    a village connection cannot distinguish a lost response from a lost
    request."""
    op = spec["paths"]["/v1/payments"]["post"]
    headers = [q for q in op.get("parameters", []) if q.get("in") == "header"]
    assert any(q["name"] == "Idempotency-Key" for q in headers), (
        "payment creation must accept an Idempotency-Key header"
    )


async def test_a_repeated_payment_request_does_not_pay_twice(client):
    """The behaviour, not the documentation."""
    from tests.test_payments import _payable

    headers, _center, supplier, settlement = await _payable(client)
    key = uuid.uuid4().hex
    body = {
        "supplier_id": supplier["id"],
        "currency": "KES",
        "method": "MOBILE_MONEY",
        "allocations": [{"settlement_id": settlement["id"]}],
    }
    first = await client.post(
        "/v1/payments", json=body, headers={**headers, "Idempotency-Key": key}
    )
    second = await client.post(
        "/v1/payments", json=body, headers={**headers, "Idempotency-Key": key}
    )
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"], "the retry created a second payment"


# --- REST semantics --------------------------------------------------------


def test_deletes_return_204_with_no_body(spec):
    offenders = [
        p
        for p, ms in spec["paths"].items()
        if "delete" in ms
        and p.startswith("/v1")
        and not p.startswith("/v1/_")  # operator endpoints report what they did
        and "204" not in ms["delete"].get("responses", {})
    ]
    assert offenders == [], offenders


def test_creations_return_201(spec):
    """A POST that creates a resource says so. A POST that acts on an existing
    one correctly returns 200 — the distinction is the point."""
    from platform_core.main import create_app

    app = create_app()
    creations = {
        "/v1/organizations",
        "/v1/workspaces",
        "/v1/branches",
        "/v1/suppliers",
        "/v1/collection-centers",
        "/v1/rate-cards",
        "/v1/settlements",
        "/v1/payments",
        "/v1/devices",
        "/v1/invitations",
    }
    assert app  # keep the import meaningful
    wrong = [p for p in creations if "201" not in spec["paths"][p]["post"].get("responses", {})]
    assert wrong == [], f"creations not returning 201: {wrong}"


def test_every_operation_declares_a_response_schema_or_204(spec):
    """An operation with no documented success body cannot be generated into
    a typed client."""
    undocumented = []
    for method, path, op in _operations(spec):
        if not path.startswith("/v1"):
            continue
        ok = {c for c in op.get("responses", {}) if c.startswith("2")}
        if ok == {"204"}:
            continue
        if not any(op["responses"][c].get("content") for c in ok):
            undocumented.append(f"{method} {path}")
    assert undocumented == [], undocumented


# --- authentication surface ------------------------------------------------


PUBLIC = {
    ("POST", "/v1/auth/register"),
    ("POST", "/v1/auth/token"),
    ("POST", "/v1/auth/refresh"),
    ("POST", "/v1/auth/password-reset/request"),
    ("POST", "/v1/auth/password-reset/confirm"),
    ("POST", "/v1/invitations/accept"),
    ("GET", "/v1/.well-known/jwks.json"),
}


def test_only_the_expected_endpoints_are_public(spec):
    """The list is short and every entry is a deliberate decision. A new
    unauthenticated endpoint has to be added here, which is the point."""
    public = {
        (m, p) for m, p, op in _operations(spec) if p.startswith("/v1") and "security" not in op
    }
    assert public == PUBLIC, f"unexpected: {public - PUBLIC}, missing: {PUBLIC - public}"
