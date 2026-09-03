"""The intake unit belongs to the dairy, not to the code (D-21 · WO-70).

The platform refused any unit but kilograms and wrote the constant into a
column that could hold anything, because "the NDDB AMCU spec has a scale"
was read as "India collects in kg". In India milk is sold and quoted in
LITRES. These tests pin the correction and, more importantly, the three
things D-21 says go wrong if skimmed:

1. Conversion is a COMMERCIAL TERM the owner declares, pinned at capture and
   printed beside both figures — never a physical constant. A literal 1.03
   in the source is a defect, and a test greps for one.
2. Density stays a quality dimension and never converts quantity.
3. History is never relabelled: every pre-existing row and organisation is
   kilograms, because that is what was measured, and changing a live
   organisation's unit applies to FUTURE transactions only.

And the one that must not be lost on the way: a reading in the wrong unit is
still refused. This did not become "accept anything".
"""

from __future__ import annotations

import os
import pathlib
import re
import sqlite3
import subprocess
import sys
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from platform_core.core.locales import COUNTRIES, UnknownCountryError, resolve
from platform_core.core.units import (
    UNITS,
    ConversionTerms,
    UnknownUnitError,
    normalise_unit,
    trade_quantity,
    unit_label,
    validate_terms,
)
from tests.clock import days_ago
from tests.test_milk_type_reporting import _collect
from tests.test_procurement_e2e import _procurement_env, _run_collection

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "platform_core"


# --- the registry ------------------------------------------------------------


def test_india_and_kenya_trade_in_litres_and_the_us_by_weight():
    assert resolve("IN").quantity_unit == "litre"
    assert resolve("KE").quantity_unit == "litre"
    # Farm milk in the US is priced per hundredweight — weight, not volume.
    assert resolve("US").quantity_unit == "kg"


def test_every_country_names_a_unit_the_platform_measures_in():
    for code, country in COUNTRIES.items():
        assert country.quantity_unit in UNITS, code
        assert resolve(code).quantity_unit == country.quantity_unit


def test_an_organisation_overrides_its_country_like_it_does_its_currency():
    # The cooperative that weighs. Spelling is normalised at the boundary.
    assert resolve("IN", quantity_unit="kg").quantity_unit == "kg"
    assert resolve("IN", quantity_unit="KG").quantity_unit == "kg"
    assert resolve("KE", quantity_unit="L").quantity_unit == "litre"
    with pytest.raises(UnknownUnitError):
        resolve("IN", quantity_unit="lb")


def test_an_unknown_country_must_be_told_its_unit_by_name():
    # Exactly the currency's behaviour: refuse to guess, say what is missing.
    with pytest.raises(UnknownCountryError, match="quantity_unit"):
        resolve("ZZ", currency_code="EUR", timezone="Europe/Berlin")
    assert (
        resolve(
            "ZZ", currency_code="EUR", timezone="Europe/Berlin", quantity_unit="kg"
        ).quantity_unit
        == "kg"
    )


def test_units_have_one_stored_word_and_one_symbol():
    for spelling in ("L", "l", "litre", "Litres", "liter", "ltr"):
        assert normalise_unit(spelling) == "litre"
    for spelling in ("kg", "KG", "kilogram", "kilograms"):
        assert normalise_unit(spelling) == "kg"
    assert unit_label("litre") == "L"
    assert unit_label("kg") == "kg"
    assert unit_label("mixed") == "mixed"  # an aggregate across a unit change says so
    assert unit_label(None) == ""


# --- conversion is a declared commercial term, not physics -------------------


def test_the_factor_is_kilograms_per_litre_in_both_directions():
    f = Decimal("1.0300")
    assert trade_quantity(40.0, measured_unit="litre", trade_unit="kg", factor=f) == 41.2
    assert trade_quantity(41.2, measured_unit="kg", trade_unit="litre", factor=f) == 40.0
    # Rounded once, half-up, to the scale's three places.
    assert trade_quantity(10.0005, measured_unit="litre", trade_unit="kg", factor=f) == 10.301
    # Same unit: nothing converts, whatever factor is lying around.
    assert trade_quantity(12.5, measured_unit="kg", trade_unit="kg", factor=f) == 12.5


def test_conversion_terms_are_validated_together():
    # The ordinary case: measured and traded alike, nothing declared.
    terms = validate_terms("litre", None, None, None)
    assert terms == ConversionTerms(measured_unit="litre")
    assert not terms.converts
    # A trade unit equal to the measured one is the ordinary case too.
    assert not validate_terms("litre", "L", None, None).converts
    # A differing trade unit needs BOTH a factor and a date.
    with pytest.raises(ValueError, match="factor"):
        validate_terms("litre", "kg", None, date(2026, 9, 1))
    with pytest.raises(ValueError, match="date"):
        validate_terms("litre", "kg", Decimal("1.03"), None)
    # A factor with nothing to convert is a dormant number and is refused.
    with pytest.raises(ValueError, match="only applies"):
        validate_terms("litre", None, Decimal("1.03"), date(2026, 9, 1))
    # Commercial bounds: the units the wrong way round, a percentage.
    for bad in ("0.5", "1.5", "103"):
        with pytest.raises(ValueError, match="outside"):
            validate_terms("litre", "kg", Decimal(bad), date(2026, 9, 1))
    good = validate_terms("litre", "kg", Decimal("1.0300"), date(2026, 9, 1))
    assert good.converts and good.in_force(date(2026, 9, 1))
    assert not good.in_force(date(2026, 8, 31)), "not yet in force"


def test_no_physical_constant_is_hard_coded_anywhere():
    """D-21 ruling 3: a literal 1.03 (or 1.026-1.034) in the source is a
    defect. The factor is the owner's, on the organisation, with a date."""
    #: The two places the range may be WRITTEN without being USED: the unit
    #: module's own docstring, which records the ruling, and the mock
    #: analyzer, which fabricates a DENSITY reading — a quality dimension
    #: (ruling 4), never a conversion.
    allowed = {"core/units.py", "infrastructure/hardware.py"}
    offenders = []
    for path in SRC.rglob("*.py"):
        if str(path.relative_to(SRC)) in allowed:
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if re.search(r"(?<![\d.])1\.0(2[6-9]|3[0-4]?)\b", code):
                offenders.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not offenders, offenders


def test_density_never_converts_quantity():
    """Ruling 4. The unit module does not know density exists, and the
    conversion path in the collection service reads the organisation's
    declared factor, never the analyzer's reading."""
    units_src = (SRC / "core" / "units.py").read_text()
    assert "density" not in units_src.split('"""', 2)[2].lower(), (
        "core/units.py must not read density outside its docstring"
    )
    service = (SRC / "modules" / "milk_collection" / "service.py").read_text()
    start = service.index("terms.in_force(")
    pin = service[start : service.index('"WeightCaptured"', start)]
    assert "density" not in pin, "the pinned conversion must not read the density reading"
    assert "terms.factor" in pin


def test_no_source_file_assumes_kilograms_outside_the_declared_places():
    """The grep that measured the defect (12 backend hard-codes), kept as a
    guard. A `"kg"` literal is allowed only where it MEANS "what pre-WO-70
    rows were": the unit registry, the two column defaults documented as
    backfill values, and the migration. Everywhere else the unit is read."""
    allowed = {
        "core/units.py",
        "core/locales.py",
        "core/org_context.py",  # PLATFORM_DEFAULT: the pre-WO-70 context, documented
        "modules/organization/models.py",  # backfill default, documented
        "modules/dispatch/models.py",  # backfill default, documented
        "modules/settlement/models.py",  # column default for pre-WO-70 rows
        "modules/milk_collection/service.py",  # `_paid_unit` last resort for unweighed rows
        "core/types.py",  # a docstring example of a Quantity
    }
    offenders = []
    for path in SRC.rglob("*.py"):
        rel = str(path.relative_to(SRC))
        if rel in allowed or rel.startswith("migrations"):
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if '"kg"' in code or "'kg'" in code:
                offenders.append(f"{rel}:{n}: {line.strip()}")
    assert not offenders, offenders


def test_no_client_script_names_a_unit_the_platform_did_not_give_it():
    """The proofs' seeder, the smoke test, the perf harness and the e2e
    journey all sent `"unit": "kg"` with every weight — and the first
    PostgreSQL proof after WO-70 failed at `weight 1` because the guard
    refused a kilogram reading into a litre tenant, which is the guard
    working. A script has no business asserting the dairy's unit; it omits
    the field and the platform applies the organisation's."""
    offenders = []
    for path in (ROOT.parent.parent / "infra").rglob("*.py"):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r'"unit":\s*"(kg|litre|L)"', line.split("#", 1)[0]):
                offenders.append(f"{path.relative_to(ROOT.parent.parent)}:{n}: {line.strip()}")
    assert not offenders, offenders


def test_every_reporting_quantity_carries_its_unit():
    """The WO-61 guard, for units: a `*_kg`-suffixed figure on a reporting
    DTO must sit beside a `quantity_unit` on the same model, or the client
    has to assume — which is the defect."""
    import inspect

    from platform_core.modules.reporting import service as reporting

    offenders = []
    for name, model in vars(reporting).items():
        if not (inspect.isclass(model) and hasattr(model, "model_fields")):
            continue
        fields = model.model_fields
        if any(f.endswith("_kg") for f in fields) and "quantity_unit" not in fields:
            # `DayBookRow` and `TrendPoint` are rows of a parent that states
            # the unit once for all of them.
            if name in {"DayBookRow", "TrendPoint"}:
                continue
            offenders.append(name)
    assert not offenders, offenders


# --- the organisation ----------------------------------------------------------


async def _locale(client, headers):
    r = await client.get("/v1/organizations/settings/locale", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _set_locale(client, headers, **body):
    return await client.put("/v1/organizations/settings/locale", json=body, headers=headers)


@pytest.mark.asyncio
async def test_the_kenyan_test_tenant_measures_in_litres_and_says_so_everywhere(client):
    headers, _center, _supplier, _session = await _procurement_env(client, with_pricing=False)
    settings = await _locale(client, headers)
    assert settings["quantity_unit"] == "litre"
    assert settings["quantity_unit_label"] == "L"
    assert settings["units"] == ["litre", "kg"]
    assert settings["trade_unit"] is None and settings["conversion_factor"] is None
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    assert me["organization"]["quantity_unit"] == "litre"
    assert me["organization"]["quantity_unit_label"] == "L"


@pytest.mark.asyncio
async def test_a_half_declared_conversion_is_refused_at_the_boundary(client):
    headers, *_ = await _procurement_env(client, with_pricing=False)
    r = await _set_locale(client, headers, trade_unit="kg")
    assert r.status_code == 422, r.text
    assert "factor" in r.text
    r = await _set_locale(client, headers, trade_unit="kg", conversion_factor="1.0300")
    assert r.status_code == 422 and "date" in r.text
    r = await _set_locale(
        client,
        headers,
        trade_unit="kg",
        conversion_factor="2.5",
        conversion_effective_from=str(days_ago(1)),
    )
    assert r.status_code == 422 and "outside" in r.text
    r = await _set_locale(client, headers, quantity_unit="lb")
    assert r.status_code == 422
    # Nothing half-applied.
    settings = await _locale(client, headers)
    assert settings["quantity_unit"] == "litre" and settings["trade_unit"] is None


# --- a litre tenant, end to end --------------------------------------------------


@pytest.mark.asyncio
async def test_a_litre_tenant_captures_prices_slips_and_reports_in_litres_with_no_kg(client):
    headers, center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier, gross=30.0, tare=5.0)
    assert tx["weight_unit"] == "litre"
    assert tx["net_weight"] == 25.0
    assert tx["trade_unit"] is None and tx["trade_quantity"] is None
    assert tx["pricing_status"] == "priced"
    # 25 L at the 45.00 band.
    assert Decimal(str(tx["gross_amount"])) == Decimal("1125.00")
    for step in ("accept", "complete"):
        r = await client.post(f"/v1/milk-transactions/{tx['id']}/{step}", headers=headers)
        assert r.status_code == 200, r.text

    slip = (await client.get(f"/v1/milk-transactions/{tx['id']}/slip", headers=headers)).json()
    assert slip["weight_unit"] == "litre"
    assert "Qty: 25 L" in slip["text"]
    assert "/L" in slip["text"]
    assert "kg" not in slip["text"], slip["text"]
    assert "Paid qty" not in slip["text"], "nothing converts, nothing prints"

    book = (
        await client.get(
            "/v1/reports/day-book", params={"center_id": center["id"]}, headers=headers
        )
    ).json()
    assert book["quantity_unit"] == "litre"
    assert book["total_collected_kg"] == 25.0  # the suffix is historical; the unit is stated

    csv = (
        await client.get(
            "/v1/reports/day-book.csv", params={"center_id": center["id"]}, headers=headers
        )
    ).text
    assert "collected_L" in csv and "remainder_L" in csv
    assert "quantity_unit,L" in csv
    assert "kg" not in csv, csv

    daily = (await client.get("/v1/reports/collection/daily", headers=headers)).json()
    assert daily["quantity_unit"] == "litre"
    assert daily["by_milk_type"][0]["quantity_unit"] == "litre"


@pytest.mark.asyncio
async def test_a_dispatch_in_the_wrong_unit_is_refused(client):
    headers, center, _supplier, _session = await _procurement_env(client, with_pricing=False)
    day = (await client.get("/v1/reports/day-book", headers=headers)).json()["business_date"]
    body = {
        "center_id": center["id"],
        "business_date": day,
        "milk_type": "cow",
        "quantity": "10.000",
        "destination": "Anand Chilling Plant",
    }
    r = await client.post("/v1/dispatches", json={**body, "quantity_unit": "kg"}, headers=headers)
    assert r.status_code == 409, r.text
    assert "measures milk in L" in r.json()["extra"]
    r = await client.post("/v1/dispatches", json=body, headers=headers)
    assert r.status_code == 201, r.text
    assert r.json()["quantity_unit"] == "litre"


# --- a kilogram tenant, and history that does not move --------------------------


@pytest.mark.asyncio
async def test_changing_the_unit_applies_to_future_collections_only(client):
    """THE HISTORICAL-CORRUPTION GUARD. A litre collection exists; the owner
    switches the organisation to kilograms; the litre row keeps its unit, the
    day it belongs to still reports litres, and only the next collection is
    weighed. Relabelling would have turned a volume into a weight on a paid
    receipt — about 3% wrong, silently."""
    headers, center, supplier, session = await _procurement_env(client)
    started = await _collect(client, headers, session["id"], supplier, milk_type="cow", gross=30.0)
    first = (await client.get(f"/v1/milk-transactions/{started['id']}", headers=headers)).json()
    assert first["weight_unit"] == "litre"

    r = await _set_locale(client, headers, quantity_unit="kg")
    assert r.status_code == 200, r.text
    assert r.json()["quantity_unit"] == "kg"

    again = (await client.get(f"/v1/milk-transactions/{first['id']}", headers=headers)).json()
    assert again["weight_unit"] == "litre", "history keeps the unit it was measured in"
    started = await _collect(client, headers, session["id"], supplier, milk_type="cow", gross=20.0)
    second = (await client.get(f"/v1/milk-transactions/{started['id']}", headers=headers)).json()
    assert second["weight_unit"] == "kg"
    assert second["pricing_status"] == "priced"

    # The window now straddles the change: the aggregate says so rather than
    # summing litres with kilograms under either symbol.
    book = (
        await client.get(
            "/v1/reports/day-book", params={"center_id": center["id"]}, headers=headers
        )
    ).json()
    assert book["quantity_unit"] == "mixed"
    # A kg reading is now accepted, a litre one refused — the guard moved
    # with the organisation rather than disappearing.
    tx = (
        await client.post(
            "/v1/milk-transactions", json={"session_id": session["id"]}, headers=headers
        )
    ).json()
    qr = (await client.get(f"/v1/suppliers/{supplier['id']}/qr", headers=headers)).json()
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/identify",
        json={"method": "qr", "value": qr["payload"]},
        headers=headers,
    )
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/milk",
        json={"milk_type": "cow", "container_type": "can", "container_identifier": "C-9"},
        headers=headers,
    )
    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/weight",
        json={"source": "manual", "gross": 10, "tare": 1, "unit": "L"},
        headers=headers,
    )
    assert r.status_code == 409 and "measures milk in kg" in r.json()["extra"]


@pytest.mark.asyncio
async def test_a_kg_tenant_does_the_same_in_kilograms(client):
    headers, center, supplier, session = await _procurement_env(client)
    assert (await _set_locale(client, headers, quantity_unit="kg")).status_code == 200
    tx = await _run_collection(client, headers, session["id"], supplier, gross=30.0, tare=5.0)
    assert tx["weight_unit"] == "kg"
    for step in ("accept", "complete"):
        assert (
            await client.post(f"/v1/milk-transactions/{tx['id']}/{step}", headers=headers)
        ).status_code == 200
    slip = (await client.get(f"/v1/milk-transactions/{tx['id']}/slip", headers=headers)).json()
    assert "Qty: 25 kg" in slip["text"] and "/kg" in slip["text"]
    assert " L" not in slip["text"]
    book = (
        await client.get(
            "/v1/reports/day-book", params={"center_id": center["id"]}, headers=headers
        )
    ).json()
    assert book["quantity_unit"] == "kg"
    csv = (
        await client.get(
            "/v1/reports/day-book.csv", params={"center_id": center["id"]}, headers=headers
        )
    ).text
    assert "collected_kg" in csv and "quantity_unit,kg" in csv


# --- a declared factor: both figures, and the factor, on the receipt ------------


@pytest.mark.asyncio
async def test_a_declared_factor_is_pinned_priced_and_printed(client):
    headers, _center, supplier, session = await _procurement_env(client)
    r = await _set_locale(
        client,
        headers,
        trade_unit="kg",
        conversion_factor="1.0300",
        conversion_effective_from=str(days_ago(1)),
    )
    assert r.status_code == 200, r.text
    assert r.json()["trade_unit"] == "kg" and r.json()["trade_unit_label"] == "kg"

    tx = await _run_collection(client, headers, session["id"], supplier, gross=45.0, tare=5.0)
    assert tx["weight_unit"] == "litre" and tx["net_weight"] == 40.0
    assert tx["trade_unit"] == "kg"
    assert tx["trade_quantity"] == 41.2
    assert Decimal(str(tx["conversion_factor"])) == Decimal("1.0300")
    # Priced on the PAID quantity: 41.2 kg at 45.00/kg, not 40 L.
    assert Decimal(str(tx["gross_amount"])) == Decimal("1854.00")

    # The owner changes the factor tomorrow; this row does not move.
    r = await _set_locale(client, headers, conversion_factor="1.0400")
    assert r.status_code == 200, r.text
    again = (await client.get(f"/v1/milk-transactions/{tx['id']}", headers=headers)).json()
    assert again["trade_quantity"] == 41.2
    assert Decimal(str(again["conversion_factor"])) == Decimal("1.0300")

    for step in ("accept", "complete"):
        assert (
            await client.post(f"/v1/milk-transactions/{tx['id']}/{step}", headers=headers)
        ).status_code == 200
    slip = (await client.get(f"/v1/milk-transactions/{tx['id']}/slip", headers=headers)).json()
    text = slip["text"]
    assert "Qty: 40 L" in text
    assert "Paid qty: 41.2 kg x 1.0300 kg/L" in text
    assert "/kg" in text, "the rate is per the unit the farmer is paid in"

    # And withdrawing the conversion is an explicit act, not a null.
    r = await _set_locale(client, headers, clear_conversion=True)
    assert r.status_code == 200 and r.json()["trade_unit"] is None


# --- the migration backfill ------------------------------------------------------


def _alembic(db: pathlib.Path, *args: str) -> None:
    env = {**os.environ, "LACTEVA_DATABASE_URL": f"sqlite+aiosqlite:///{db}"}
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
    )


def _insert_minimal(conn: sqlite3.Connection, table: str, values: dict) -> None:
    """Insert a row supplying every NOT NULL column the caller did not, with a
    type-appropriate dummy — the point is the backfill, not the row."""
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    row = dict(values)
    for _cid, name, ctype, notnull, default, _pk in cols:
        if name in row or not notnull or default is not None:
            continue
        t = (ctype or "").upper()
        if "INT" in t:
            row[name] = 0
        elif "CHAR" in t or "TEXT" in t or "JSON" in t or t == "":
            row[name] = "x"
        elif "DATE" in t or "TIME" in t:
            row[name] = datetime.now(UTC).isoformat()
        elif "NUM" in t or "DEC" in t or "FLOAT" in t or "REAL" in t:
            row[name] = 0
        elif "BLOB" in t:
            row[name] = b"\x00" * 16
        else:
            row[name] = "x"
    keys = list(row)
    conn.execute(
        f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})",
        [row[k] for k in keys],
    )


def test_the_migration_backfills_every_existing_organisation_and_row_to_kg(tmp_path):
    """Indian organisations INCLUDED. Every row that existed was weighed —
    the service allowed nothing else — and a volume label on a weight is a
    3% error on a paid settlement."""
    db = tmp_path / "before.db"
    _alembic(db, "upgrade", "b7c41d29e5af")  # the head before WO-70
    conn = sqlite3.connect(db)
    org_id = uuid.uuid4().hex
    _insert_minimal(
        conn,
        "organization",
        {
            "id": org_id,
            "name": "Lacteva India Demo",
            "slug": "india-before-wo70",
            "country_code": "IN",
            "currency_code": "INR",
            "timezone": "Asia/Kolkata",
            "supported_languages": '["en-IN"]',
            "default_locale": "en-IN",
        },
    )
    tx_id = uuid.uuid4().hex
    _insert_minimal(
        conn,
        "milk_collection_transaction",
        {"id": tx_id, "tenant_id": org_id, "state": "COMPLETED", "net_weight": 12.5},
    )
    conn.commit()
    conn.close()

    _alembic(db, "upgrade", "head")
    conn = sqlite3.connect(db)
    unit, trade, factor = conn.execute(
        "SELECT quantity_unit, trade_unit, conversion_factor FROM organization WHERE id = ?",
        (org_id,),
    ).fetchone()
    assert (unit, trade, factor) == ("kg", None, None), "an Indian org that existed WEIGHED"
    weight_unit, trade_unit, trade_qty = conn.execute(
        "SELECT weight_unit, trade_unit, trade_quantity FROM milk_collection_transaction "
        "WHERE id = ?",
        (tx_id,),
    ).fetchone()
    assert (weight_unit, trade_unit, trade_qty) == ("kg", None, None)
    conn.close()

    # And the way back exists.
    _alembic(db, "downgrade", "b7c41d29e5af")
    conn = sqlite3.connect(db)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(organization)")}
    assert "quantity_unit" not in columns
    conn.close()
