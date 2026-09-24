"""WO-85 / D-31 — the organisation says which modules it runs.

Owner decision D-31: "dont remove what we have created earlier … some dairy
firm also have retail, they sell and purchase both. so make everything
customizable." So an organisation has a LIST — `collection`, `sales`, or
both — not a profile, and the properties pinned here are the ones that
protect the dairies that already exist:

  * every organisation that exists when the column lands has BOTH;
  * a new organisation has both unless onboarding says otherwise;
  * `["sales"]` and `["collection"]` are first-class and read back as sent;
  * an empty list, or an unknown key, is refused;
  * turning a module off and on again changes NOTHING but the list — no row
    in any business table moves;
  * `/v1/auth/me` carries the list, so both clients read it from the
    session they already fetch;
  * no permission, policy or business rule branches on it — a grep of the
    platform's own source, because this is the kind of flag that grows
    teeth quietly.
"""

import re
import sqlite3
import uuid
from pathlib import Path

from platform_core.core.modules import DEFAULT_MODULES, MODULES, validate_modules
from tests.test_localization import _make_org, _platform_admin
from tests.test_org_structure import _tenant_admin
from tests.test_units import _alembic

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "platform_core"


def test_the_registry_is_the_two_modules_and_validation_is_canonical():
    assert list(MODULES) == ["collection", "sales"]
    assert list(DEFAULT_MODULES) == ["collection", "sales"]
    assert validate_modules(None) == ["collection", "sales"]
    # De-duplicated, case-folded, registry order — whatever order was sent.
    assert validate_modules(["sales", "Collection", "sales"]) == ["collection", "sales"]
    assert validate_modules(["sales"]) == ["sales"]
    for bad in ([], ["retail"], ["sales", "retail"]):
        try:
            validate_modules(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} was accepted")


async def test_a_new_organisation_runs_the_whole_product_unless_told_otherwise(client):
    headers = await _platform_admin(client)
    r = await _make_org(client, headers, name="Both", slug="both-demo", country_code="IN")
    assert r.status_code == 201, r.text
    assert r.json()["modules"] == ["collection", "sales"]

    r = await _make_org(
        client, headers, name="Gavyam", slug="gavyam", country_code="IN", modules=["sales"]
    )
    assert r.status_code == 201, r.text
    assert r.json()["modules"] == ["sales"]

    r = await _make_org(
        client, headers, name="Classic", slug="classic", country_code="KE", modules=["collection"]
    )
    assert r.status_code == 201, r.text
    assert r.json()["modules"] == ["collection"]


async def test_an_organisation_with_no_module_is_refused(client):
    headers = await _platform_admin(client)
    r = await _make_org(
        client, headers, name="Nothing", slug="nothing", country_code="IN", modules=[]
    )
    assert r.status_code == 422, r.text
    assert "at least one module" in r.text
    r = await _make_org(
        client, headers, name="Retail", slug="retail", country_code="IN", modules=["retail"]
    )
    assert r.status_code == 422, r.text


async def test_the_session_carries_the_list_and_settings_change_it(client):
    _org, admin = await _tenant_admin(client)
    me = (await client.get("/v1/auth/me", headers=admin)).json()
    assert me["organization"]["modules"] == ["collection", "sales"]

    settings = (await client.get("/v1/organizations/settings/locale", headers=admin)).json()
    assert settings["modules"] == ["collection", "sales"]
    assert [m["key"] for m in settings["available_modules"]] == ["collection", "sales"]
    assert all(m["label"] and m["description"] for m in settings["available_modules"])

    r = await client.put(
        "/v1/organizations/settings/locale", json={"modules": ["sales"]}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert r.json()["modules"] == ["sales"]
    me = (await client.get("/v1/auth/me", headers=admin)).json()
    assert me["organization"]["modules"] == ["sales"]

    # Absent means unchanged, as every other setting on this command.
    r = await client.put(
        "/v1/organizations/settings/locale", json={"timezone": "Asia/Kolkata"}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert r.json()["modules"] == ["sales"]

    r = await client.put("/v1/organizations/settings/locale", json={"modules": []}, headers=admin)
    assert r.status_code == 422, r.text


async def test_switching_a_module_off_and_on_changes_nothing_but_the_list(client):
    """A dairy that switches `collection` off for a month and back on finds
    every farmer, rate card and settlement exactly where they were."""
    from sqlalchemy import text

    from platform_core.core import db
    from platform_core.core.rls import rebind_tenant

    org, admin = await _tenant_admin(client)
    # A little of each side, so the count means something.
    r = await client.post(
        "/v1/suppliers",
        json={"full_name": "Farmer One", "phone": "+254700000011"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        "/v1/customers",
        json={
            "name": "Household One",
            "plan": {"unit_price": "56.0000", "default_quantity": "1.000"},
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text

    tables = (
        "supplier",
        "customer",
        "delivery_plan",
        "collection_center",
        "products",
        "rate_card",
        "settlement",
        "milk_collection_transaction",
        "milk_delivery",
        "customer_invoice",
    )

    async def counts() -> dict[str, int]:
        # The whole table: this test database holds one tenant, and a
        # tenant-filtered count would have to spell the id the way each
        # dialect stores it.
        async with db.get_session_factory()() as session:
            await rebind_tenant(session, uuid.UUID(org["id"]))
            return {
                table: int(await session.scalar(text(f"SELECT count(*) FROM {table}")) or 0)
                for table in tables
            }

    before = await counts()
    assert before["supplier"] == 1 and before["customer"] == 1

    for modules in (["sales"], ["collection"], ["collection", "sales"]):
        r = await client.put(
            "/v1/organizations/settings/locale", json={"modules": modules}, headers=admin
        )
        assert r.status_code == 200, r.text
        assert await counts() == before, modules

    # And every API still answers while a module is "off": hiding is not
    # security, and it is not a wall either.
    await client.put(
        "/v1/organizations/settings/locale", json={"modules": ["sales"]}, headers=admin
    )
    assert (await client.get("/v1/suppliers", headers=admin)).status_code == 200
    assert (await client.get("/v1/collection-centers", headers=admin)).status_code == 200


def test_no_business_rule_branches_on_the_modules():
    """Presentation only. The places that may read `modules` are the ones
    that SAY what is enabled: the registry, the organisation model, the
    settings service that writes it, and the two payloads that carry it."""
    allowed = {
        "core/modules.py",
        "modules/organization/models.py",
        "modules/organization/service.py",
        "api/routes.py",  # MeOrganization and the me block
    }
    offenders = []
    # `.modules` as an attribute of a row — not the package path
    # `platform_core.modules.<x>`, which every import in the tree spells.
    pattern = re.compile(
        r"(?<!platform_core)(?<!\bcore)(?<!\bsys)\.modules\b"
        r"|\[\s*['\"]modules['\"]\s*\]"
        r"|\bmodules\s*(==|!=)"
        r"|['\"]\w+['\"]\s+(not\s+)?in\s+\w*\.?modules\b"
    )
    for path in SRC.rglob("*.py"):
        rel = str(path.relative_to(SRC))
        if rel in allowed:
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if pattern.search(code):
                offenders.append(f"{rel}:{n}: {line.strip()}")
    assert not offenders, offenders
    # And even in the allowed places, the organisation service only WRITES
    # the list and echoes it: no `if` on it.
    service = (SRC / "modules/organization/service.py").read_text()
    for n, line in enumerate(service.splitlines(), 1):
        code = line.split("#", 1)[0]
        assert not re.search(r"\bif\b.*\bmodules\b(?!\s+is\s+not\s+None)", code), (
            f"service.py:{n}: a branch on modules: {line.strip()}"
        )


def test_the_migration_turns_both_modules_on_for_every_existing_organisation(tmp_path):
    """D-31 §2 — the single most important property of this work order."""
    db = tmp_path / "before.db"
    _alembic(db, "upgrade", "d1e6b4a92c07")  # the head before this column
    conn = sqlite3.connect(db)
    notnull = {r[1]: (r[3], r[4]) for r in conn.execute("PRAGMA table_info(organization)")}
    rows = []
    for slug in ("kilima", "india-demo"):
        row = {
            "id": uuid.uuid4().hex,
            "name": slug,
            "slug": slug,
            "country_code": "IN",
            "currency_code": "INR",
            "timezone": "Asia/Kolkata",
            "supported_languages": '["en-IN"]',
            "default_locale": "en-IN",
        }
        for name, (nn, default) in notnull.items():
            if nn and name not in row and default is None:
                row[name] = "x"
        conn.execute(
            f"INSERT INTO organization ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
            list(row.values()),
        )
        rows.append(row["id"])
    conn.commit()
    conn.close()

    _alembic(db, "upgrade", "head")
    conn = sqlite3.connect(db)
    for org_id in rows:
        (modules,) = conn.execute(
            "SELECT modules FROM organization WHERE id = ?", (org_id,)
        ).fetchone()
        assert modules is not None
        assert re.sub(r"\s", "", modules) == '["collection","sales"]', modules
    conn.close()

    _alembic(db, "downgrade", "d1e6b4a92c07")
    conn = sqlite3.connect(db)
    columns = [r[1] for r in conn.execute("PRAGMA table_info(organization)")]
    assert "modules" not in columns
    conn.close()
