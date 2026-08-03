async def test_liveness(client):
    r = await client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_readiness_reports_database(client):
    r = await client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] is True


async def test_metrics_exposed(client):
    await client.get("/health/live")
    r = await client.get("/metrics")
    assert r.status_code == 200
    assert "http_requests_total" in r.text


async def test_cors_preflight_allows_portal_origin(client):
    """The browser preflight from the admin portal must succeed (regression:
    the portal at :3000 could not log in — OPTIONS returned 405)."""
    r = await client.options(
        "/v1/auth/token",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )
    assert r.status_code == 200, r.text
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "POST" in r.headers["access-control-allow-methods"]

    # Unknown origins get no CORS grant (the request itself is not blocked
    # server-side; the browser enforces the missing header).
    r = await client.options(
        "/v1/auth/token",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in r.headers


async def test_openapi_generated(client):
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/v1/auth/token" in paths
    assert "/v1/organizations" in paths
