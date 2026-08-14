"""Deterministic demo dataset for customer demonstrations (DEMO-001).

    python infra/demo/seed_demo.py seed      # build the demo dataset
    python infra/demo/seed_demo.py verify    # assert it is complete and correct
    python infra/demo/seed_demo.py purge     # remove it, leaving nothing else touched
    python infra/demo/seed_demo.py reset     # purge, then seed

Every business fact here is produced by driving the platform's OWN API in
process — the same endpoints an operator uses, through the same authorization,
the same pricing engine and the same settlement rules. Nothing is inserted
directly into a business table and no amount is computed by this script. If a
rate card says 45.0000 and the scale says 40 kg, the 1,800.00 on the demo
dashboard came from `pricing/calculator.py`, not from here. That is the point:
a demo that fakes its numbers is a demo that lies about the product.

THE ONE DELIBERATE EXCEPTION is `created_at` on a collection transaction. A
collection's business date IS its creation date (`tx_date =
as_utc(tx.created_at).date()`), and the platform has no back-dating API — quite
rightly, because an operator must not be able to move milk through time. But a
demo with only today's data looks dead, and settlements need history to settle.
So the seeder stamps the transaction row's `created_at` immediately after
creation and BEFORE pricing, so the domain then prices, settles and pays it as
a genuine collection on that day. The timestamp is the only value this script
writes directly, and it writes it before any money exists.

DETERMINISM. No randomness anywhere: quantities, quality readings, names and
dates are all derived from fixed tables and the index of the row being built.
Two runs a week apart produce the same dairy (relative to the day it is run),
so a screenshot taken today still matches the demo tomorrow.

SAFETY. Everything lives inside two organizations named below. `purge` deletes
those organizations' rows and nothing else — it is keyed on tenant id, so
development or pilot data in other organizations cannot be caught by it.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

# Run from the repository, where the package lives under `src/`, OR from inside
# the deployed image, where it is already installed. Neither should require the
# other's directory layout to exist.
_here = pathlib.Path(__file__).resolve()
if len(_here.parents) > 2:
    _src = _here.parents[2] / "services/platform-core/src"
    if _src.is_dir():
        sys.path.insert(0, str(_src))

# The seeder drives the app in process; it must not also try to create tables.
os.environ.setdefault("LACTEVA_ENV", "staging")

PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo-Lacteva-2026!")

DEMO_ORG = "Lacteva Demo Cooperative"
DEMO_ORG_SLUG = "lacteva-demo"
ISOLATION_ORG = "Lacteva Isolation Demo"
ISOLATION_ORG_SLUG = "lacteva-isolation-demo"


# --- DEMO-009: the customer (sales) side -------------------------------------
#
# The mirror of the supplier round: households and businesses this dairy
# DELIVERS to. Deliberately a different cast of names from the suppliers, so a
# demonstration cannot confuse who is buying with who is selling.
#
# The mix is chosen to show the states a dairy actually has on its books:
# somebody fully paid up, somebody carrying a balance, and somebody whose milk
# is delivered but not yet billed.
# Sixteen customers, because DEMO-010 shows this to real dairy owners and six
# households is not a dairy — it is a fixture. The mix is what a peri-urban
# Kenyan dairy's book actually looks like: a majority of small households, a
# handful of shops and hotels, a school, and one distributor who takes more
# milk than everyone else combined and pays the lowest rate for doing so.
#
# The settlement state is written on each row rather than derived from an
# index, so the demo ledger can be read here and matched against the screen:
#
#   paid      bill issued and paid in full; a receipt exists
#   partial   bill issued, part paid; carries a balance
#   unpaid    bill issued, nothing paid; the oldest debt on the round
#   unbilled  delivered, no bill raised yet — work waiting to become money
#   showcase  TWO bills over two halves of the window: the first paid in full
#             with a receipt, the second left outstanding (DEMO-015 §18). It is
#             the one customer a demonstration can be walked through end to end
#             — bill, payment, receipt, and a STATEMENT that opens with a
#             brought-forward balance rather than at zero, which is the only
#             way to show that the opening balance is real.
#
# `evening` marks the customers who take a second delivery each day. It exists
# so the daily delivery report has two slots to group, which is what a real
# hotel or distributor does and what the slot column is for.
CUSTOMERS = [
    # (name, type, phone, address, litres/day, rate, state, evening)
    ("Mama Njeri Household", "household", "+254701000101", "12 Kilima Road", "2.000", "62.00", "partial", False),
    ("Kilima Tea House", "shop", "+254701000102", "Market Street", "8.000", "58.00", "showcase", False),
    ("Ngong View Hotel", "hotel", "+254701000103", "Ngong Road", "20.000", "55.00", "partial", True),
    ("St. Mary's School", "institution", "+254701000104", "Limuru Road", "35.000", "54.00", "paid", False),
    ("Wanjala Distributors", "distributor", "+254701000105", "Industrial Area", "60.000", "52.00", "unpaid", True),
    ("Achieng Household", "household", "+254701000106", "8 Naivasha Lane", "1.500", "62.00", "paid", False),
    ("Wairimu Household", "household", "+254701000107", "24 Kiambu Road", "3.000", "62.00", "unpaid", False),
    ("Otieno Household", "household", "+254701000108", "5 Lakeside Close", "2.000", "62.00", "paid", False),
    ("Chebet Household", "household", "+254701000109", "17 Highland Drive", "2.500", "62.00", "partial", False),
    ("Green Cup Cafe", "shop", "+254701000110", "Station Road", "12.000", "58.00", "paid", False),
    ("Limuru Ridge Bakery", "shop", "+254701000111", "3 Ridge Lane", "15.000", "57.00", "unpaid", False),
    ("Riverside Guest House", "hotel", "+254701000112", "Riverside Drive", "18.000", "55.00", "paid", True),
    ("Kiambu Mission Hospital", "institution", "+254701000113", "Hospital Road", "40.000", "54.00", "partial", False),
    ("Naivasha Grocers", "distributor", "+254701000114", "Market Square", "45.000", "53.00", "paid", False),
    ("Kamau Household", "household", "+254701000115", "9 Valley View", "2.000", "62.00", "unbilled", False),
    ("Mutindi Household", "household", "+254701000116", "31 Church Street", "1.500", "62.00", "unbilled", False),
]


#: Days of delivery history. Enough for a monthly bill to be a real month.
DELIVERY_DAYS = 30


# --- the dairy ---------------------------------------------------------------
# Kenyan cooperative names, because the platform's currency is KES and its
# demo receipts already read "Amina Njoroge". A believable dairy beats a
# clever one: nobody is persuaded by "Test Supplier 1".

# --- markets (DEMO-013) -------------------------------------------------------
#
# A demo tenant used to BE Kenya: the centres, the farmers, the households, the
# rates and the country code were module constants, and `make_org` posted
# `country_code: "ke"` outright. Demonstrating the platform to an Indian dairy
# would have meant either showing them shillings or forking the seeder.
#
# So a market is now DATA. Kenya is one value of it and India is another, and
# the builders below take one as a parameter — there is no branch anywhere that
# asks which country it is building. Adding a third market is a third profile.
#
# The names are real-looking on purpose. Nobody is persuaded by "Test Supplier
# 1", and a dairy manager reading a demo bill should recognise the world it
# describes.


@dataclass(frozen=True)
class Market:
    """One demonstrable dairy, in one country."""

    key: str
    org_name: str
    org_slug: str
    #: ISO 3166-1 alpha-2. The platform resolves currency, timezone and
    #: languages from it — the seeder never states them, which is the point.
    country_code: str
    email_domain: str
    centers: list
    supplier_names: list
    customers: list
    #: (fat_min, fat_max, rate) — the money is per-market because a litre is
    #: not worth the same number in two currencies.
    fat_bands: list
    staff: dict
    currency_hint: str  # for the seed SUMMARY only; the platform is the truth


CENTERS = [
    ("Kilima Hill Collection Centre", "KH-C1"),
    ("Ngong Valley Collection Centre", "NV-C1"),
    ("Limuru Ridge Collection Centre", "LR-C1"),
    ("Naivasha Lakeside Centre", "NL-C1"),
    ("Kiambu Highlands Centre", "KB-C1"),
]

SUPPLIER_NAMES = [
    "Amina Njoroge",
    "Joseph Kamau",
    "Grace Wanjiru",
    "Peter Otieno",
    "Mary Achieng",
    "Daniel Kiprono",
    "Esther Mwangi",
    "Samuel Barasa",
    "Ruth Chebet",
    "John Muriithi",
    "Lydia Nekesa",
    "Francis Ochieng",
    "Beatrice Wairimu",
    "Patrick Kimani",
    "Agnes Cherono",
    "Michael Wekesa",
    "Sarah Atieno",
    "Stephen Njuguna",
    "Faith Mutindi",
    "Charles Rotich",
    "Priscilla Adhiambo",
    "Anthony Gitau",
    "Jane Kerubo",
    "Elijah Maina",
]

# Fat percentage per supplier, fixed so a supplier always prices the same way.
# Values straddle the band boundaries below, so the demo shows three rates.
FAT_BY_SUPPLIER = [
    3.4,
    4.2,
    5.1,
    3.8,
    4.5,
    4.9,
    3.6,
    5.3,
    4.1,
    3.9,
    4.7,
    5.0,
    3.5,
    4.3,
    4.8,
    3.7,
    4.4,
    5.2,
    4.0,
    3.3,
    4.6,
    5.4,
    3.2,
    4.05,
]

# (from, to, price) — FAT bands in KES per kg. Contiguous and half-open, which
# is how `pricing/resolution.py` reads them.
FAT_BANDS = [(3.0, 4.0, 42.0), (4.0, 5.0, 45.5), (5.0, 6.0, 49.0)]


KENYA = Market(
    key="kenya",
    org_name=DEMO_ORG,
    org_slug=DEMO_ORG_SLUG,
    country_code="KE",
    email_domain="lacteva-demo.example.com",
    centers=CENTERS,
    supplier_names=SUPPLIER_NAMES,
    customers=CUSTOMERS,
    fat_bands=FAT_BANDS,
    staff={
        "manager": "Wanjiku Mbugua",
        "viewer": "Otieno Odhiambo",
        "operations": "Kipchoge Rutto",
        "operator": "Naliaka Simiyu",
        "sales": "Zawadi Mwakio",
        "household": "Njeri Mwangi",
    },
    currency_hint="KES",
)

#: DEMO-013 §10 — a SEPARATE Indian tenant, not a converted Kenyan one.
#:
#: Converting the existing records would have destroyed the evidence that the
#: platform runs two countries at once, which is the whole claim. Rates are
#: rupees per litre at plausible Indian levels; the households and the dairies
#: are the kind a Bengaluru co-operative actually serves.
INDIA_CENTERS = [
    ("Yelahanka Collection Centre", "YL-C1"),
    ("Hoskote Collection Centre", "HK-C1"),
    ("Devanahalli Collection Centre", "DV-C1"),
]

INDIA_SUPPLIERS = [
    "Ramesh Gowda",
    "Lakshmi Devi",
    "Suresh Patil",
    "Anjali Reddy",
    "Venkatesh Rao",
    "Meena Kumari",
    "Prakash Shetty",
    "Savitha Nayak",
    "Manjunath Hegde",
    "Kavitha Iyer",
    "Basavaraj Kulkarni",
    "Shobha Rani",
]

#: (name, type, phone, address, litres/day, rate, state, evening)
INDIA_CUSTOMERS = [
    ("Sharma Household", "household", "+919845000101", "12 Jayanagar 4th Block", "1.000", "56.00", "partial", False),
    ("Iyengar Bakery", "shop", "+919845000102", "MG Road", "6.000", "52.00", "showcase", False),
    ("Hotel Sagar Deluxe", "hotel", "+919845000103", "Residency Road", "18.000", "50.00", "partial", True),
    ("St. Joseph's School", "institution", "+919845000104", "Museum Road", "30.000", "48.00", "paid", False),
    ("Nandini Distributors", "distributor", "+919845000105", "Peenya Industrial Area", "50.000", "46.00", "unpaid", True),
    ("Reddy Household", "household", "+919845000106", "8 Indiranagar 100ft Road", "1.500", "56.00", "paid", False),
    ("Krishnan Household", "household", "+919845000107", "24 Malleswaram", "2.000", "56.00", "unpaid", False),
    ("Desai Household", "household", "+919845000108", "5 Basavanagudi", "1.000", "56.00", "paid", False),
    ("Kamath Household", "household", "+919845000109", "17 Rajajinagar", "2.500", "56.00", "partial", False),
    ("Adiga Tiffin Room", "shop", "+919845000110", "Gandhi Bazaar", "10.000", "52.00", "paid", False),
    ("Sri Ganesh Sweets", "shop", "+919845000111", "Chickpet", "14.000", "51.00", "unpaid", False),
    ("Taj Residency Annexe", "hotel", "+919845000112", "Ulsoor Road", "16.000", "50.00", "paid", True),
    ("Manipal Clinic", "institution", "+919845000113", "Old Airport Road", "22.000", "48.00", "partial", False),
    ("Bengaluru Grocers", "distributor", "+919845000114", "KR Market", "40.000", "47.00", "paid", False),
    ("Pillai Household", "household", "+919845000115", "9 Koramangala 5th Block", "1.000", "56.00", "unbilled", False),
    ("Nair Household", "household", "+919845000116", "31 Whitefield", "1.500", "56.00", "unbilled", False),
    ("Bhat Household", "household", "+919845000117", "42 Vijayanagar", "2.000", "56.00", "paid", False),
    ("Rao Household", "household", "+919845000118", "7 HSR Layout", "1.000", "56.00", "partial", False),
    ("Udupi Krishna Bhavan", "shop", "+919845000119", "Seshadripuram", "12.000", "51.00", "paid", False),
    ("Cafe Coorg", "shop", "+919845000120", "Church Street", "8.000", "52.00", "unpaid", False),
    ("Hotel Mayura Residency", "hotel", "+919845000121", "Race Course Road", "20.000", "50.00", "partial", True),
    ("Vidyaniketan School", "institution", "+919845000122", "Yeshwanthpur", "26.000", "48.00", "paid", False),
    ("Bharath Milk Agencies", "distributor", "+919845000123", "Yeshwanthpur APMC", "45.000", "46.50", "unpaid", True),
    ("Joshi Household", "household", "+919845000124", "3 Sadashivanagar", "2.500", "56.00", "paid", False),
]

#: Rupees per litre by fat band. Indian co-operatives pay on fat and SNF; this
#: keeps the platform's existing single-dimension band and prices it plausibly.
INDIA_FAT_BANDS = [(3.0, 4.0, 34.0), (4.0, 5.0, 38.5), (5.0, 6.0, 43.0)]

INDIA = Market(
    key="india",
    org_name="Lacteva India Demo",
    org_slug="lacteva-india-demo",
    country_code="IN",
    email_domain="lacteva-india.example.com",
    centers=INDIA_CENTERS,
    supplier_names=INDIA_SUPPLIERS,
    customers=INDIA_CUSTOMERS,
    fat_bands=INDIA_FAT_BANDS,
    staff={
        "manager": "Priya Raghavan",
        "viewer": "Arun Menon",
        "operations": "Deepak Shenoy",
        "operator": "Sunita Bhat",
        "sales": "Rahul Verma",
        "household": "Anita Sharma",
    },
    currency_hint="INR",
)

MARKETS = {market.key: market for market in (KENYA, INDIA)}

#: Every organization this seeder owns. DEMO-013: derived from the markets
#: rather than listed, so adding a market cannot leave a tenant that `purge`
#: does not remove and `verify` does not check — which would be a demo dairy
#: nobody was maintaining, quietly rotting in the database.
DEMO_SLUGS = [m.org_slug for m in MARKETS.values()] + [ISOLATION_ORG_SLUG]


PRODUCT = "RAW-COW-MILK"

# Gross/tare pairs, cycled by index. Net weights land between 8 and 42 kg,
# which is the range a smallholder actually delivers.
WEIGHTS = [
    (14.0, 2.0),
    (22.5, 2.5),
    (31.0, 3.0),
    (18.5, 2.5),
    (27.0, 2.0),
    (35.5, 3.5),
    (12.0, 2.0),
    (24.0, 2.0),
    (29.5, 2.5),
    (44.0, 4.0),
]


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


class SeedError(SystemExit):
    pass


async def expect(response, *codes: int, what: str):
    if response.status_code not in codes:
        raise SeedError(
            f"demo seed failed at {what}: {response.status_code} {response.text[:400]}"
        )
    return response.json() if response.content else {}


async def retrying(send, *codes: int, what: str):
    """Do the thing, and WAIT if the platform says to (DEMO-013).

    Seeding a second market pushed the invitation-accept rule past its ten in
    fifteen minutes and the run died at the eleventh — correctly. The limit is
    protecting a real endpoint from a real abuse, and a seeder is not special
    enough to be exempt from it; a bypass here would be a bypass that outlives
    this script.

    So it does what any well-behaved client does: reads `retry_after_seconds`
    and comes back. That makes the seeder correct at any number of markets
    rather than lucky at one.
    """
    for attempt in range(4):
        response = await send()
        if response.status_code != 429:
            return await expect(response, *codes, what=what)
        try:
            wait = int(response.json()["extra"]["retry_after_seconds"]) + 2
        except Exception:
            wait = 60
        print(
            f"  rate limited on {what}; waiting {wait}s "
            f"(attempt {attempt + 1}/4)",
            flush=True,
        )
        await asyncio.sleep(wait)
    raise SeedError(f"demo seed failed at {what}: still rate limited after four waits")


# --- a client with no dependencies -------------------------------------------


class Response:
    """Just enough of a response for `expect()` to read."""

    def __init__(self, status_code: int, body: bytes):
        self.status_code = status_code
        self.content = body

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")

    def json(self):
        import json as _json

        return _json.loads(self.content) if self.content else {}


class AsgiClient:
    """Call the FastAPI app in process, over ASGI, with nothing installed.

    `httpx` is a DEV dependency and the production image installs `--no-dev`,
    quite rightly — a test client has no business in a runtime image. But the
    seeder has to run where the database is, which is inside that image, so
    depending on httpx would have meant either bloating production or building
    a second image to hold one library.

    The surface actually used here is four verbs and a JSON body, so the ASGI
    call is written out instead. This is not a re-implementation of an HTTP
    client: there is no connection, no pooling and no wire format — the app is
    a coroutine and this hands it a scope.
    """

    def __init__(self, app, base_url: str = "http://demo-seed"):
        self._app = app
        self._base = base_url

    async def request(
        self, method: str, path: str, *, json=None, headers=None
    ) -> Response:
        import json as _json
        from urllib.parse import urlsplit

        split = urlsplit(path)
        body = b"" if json is None else _json.dumps(json).encode()
        raw_headers = [(b"host", b"demo-seed")]
        if json is not None:
            raw_headers.append((b"content-type", b"application/json"))
        raw_headers.append((b"content-length", str(len(body)).encode()))
        for key, value in (headers or {}).items():
            raw_headers.append((key.lower().encode(), str(value).encode()))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": split.path,
            "raw_path": split.path.encode(),
            "query_string": split.query.encode(),
            "root_path": "",
            "headers": raw_headers,
            "client": ("127.0.0.1", 50000),
            "server": ("demo-seed", 80),
        }

        sent = {"status": 500, "body": bytearray()}
        request_done = False

        async def receive():
            nonlocal request_done
            if request_done:
                return {"type": "http.disconnect"}
            request_done = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                sent["status"] = message["status"]
            elif message["type"] == "http.response.body":
                sent["body"].extend(message.get("body", b""))

        await self._app(scope, receive, send)
        return Response(sent["status"], bytes(sent["body"]))

    async def get(self, path, *, headers=None):
        return await self.request("GET", path, headers=headers)

    async def post(self, path, *, json=None, headers=None):
        return await self.request("POST", path, json=json, headers=headers)

    async def put(self, path, *, json=None, headers=None):
        return await self.request("PUT", path, json=json, headers=headers)

    async def delete(self, path, *, headers=None):
        return await self.request("DELETE", path, headers=headers)


# --- platform plumbing -------------------------------------------------------


async def bootstrap() -> None:
    """What the app lifespan does, minus the background loops."""
    from platform_core.core.rls import platform_factory
    from platform_core.modules.authz.service import AuthzService
    from platform_core.modules.event_relay.consumers import discover_consumers
    from platform_core.modules.event_relay.projections import discover_projections

    discover_consumers()
    discover_projections()
    async with platform_factory("demo seed: system-role catalog")() as session:
        await AuthzService(session).ensure_system_roles()
        await session.commit()


async def backdate_transaction(tx_id: str, when: datetime) -> None:
    """Stamp a collection's creation instant — the one direct write.

    See the module docstring. This runs BEFORE the quality step, so the pricing
    engine reads the back-dated day and the whole downstream chain (calculation
    date, settlement eligibility, receipt) is genuinely that day's business.
    """
    import uuid as _uuid

    from platform_core.core.rls import platform_factory
    from platform_core.modules.milk_collection.models import MilkCollectionTransaction
    from sqlalchemy import update

    async with platform_factory("demo seed: back-date a collection")() as session:
        await session.execute(
            update(MilkCollectionTransaction)
            .where(MilkCollectionTransaction.id == _uuid.UUID(tx_id))
            .values(created_at=when)
        )
        await session.commit()


async def run_consumers() -> dict:
    """Let receipts and notifications be generated the way production does.

    Drains rather than pulses: `run_once` takes a bounded batch per consumer,
    and a seeded history produces far more events than one batch. Looping until
    a pass processes nothing is what the deployed worker loop does over time —
    doing it once here would leave the demo with settlements but no receipts,
    which is precisely the "healthy but empty" state this platform keeps
    learning to distrust.
    """
    from platform_core.core import db
    from platform_core.core.rls import platform_factory
    from platform_core.infrastructure.events import get_event_bus
    from platform_core.modules.event_relay.consumers import (
        ConsumerRunner,
        discover_consumers,
    )
    from platform_core.modules.event_relay.projections import discover_projections
    from platform_core.modules.event_relay.service import RelayService

    # Both halves, in order. Publishing writes an outbox row inside the
    # business transaction; the RELAY moves it onto the bus; only then can a
    # consumer see it. Running the consumer alone yields "processed: 0" and a
    # demo with no receipts, which looks like a broken product.
    discover_consumers()
    discover_projections()
    runner = ConsumerRunner(db.get_session_factory())
    totals = {"relayed": 0, "processed": 0, "failed": 0}
    for _ in range(200):  # a bound, so a stuck consumer cannot spin forever
        async with platform_factory("demo seed: relay the outbox")() as session:
            relayed = await RelayService(session, get_event_bus()).dispatch_pending(
                limit=200
            )
            await session.commit()
        result = await runner.run_once(limit=200)
        totals["relayed"] += relayed
        totals["processed"] += result["processed"]
        totals["failed"] += result["failed"]
        if not relayed and not result["processed"]:
            break
    return totals


# --- account setup -----------------------------------------------------------


async def grant_platform_admin(email: str) -> None:
    """Registration cannot grant platform-admin to itself, by design (SEC-002).

    The grant is cross-tenant by definition — it attaches a PLATFORM role and
    the lookup spans tenants — so it needs the platform session factory. Under
    an ordinary session RLS would find neither row.
    """
    from platform_core.core.rls import platform_factory
    from platform_core.modules.authz.models import Role, UserRole
    from platform_core.modules.identity.models import User
    from sqlalchemy import select

    async with platform_factory("demo seed: grant platform-admin")() as session:
        user = await session.scalar(select(User).where(User.email == email))
        role = await session.scalar(select(Role).where(Role.name == "platform-admin"))
        if user is None or role is None:
            raise SeedError("could not grant platform-admin: user or role missing")
        existing = await session.scalar(
            select(UserRole).where(
                UserRole.user_id == user.id, UserRole.role_id == role.id
            )
        )
        if existing is None:
            session.add(UserRole(user_id=user.id, role_id=role.id, tenant_id=None))
            await session.commit()


ADMIN_EMAIL = "demo-admin@lacteva.example.com"


async def refresh_member(client, headers: dict, email: str, org_id: str) -> dict:
    """The same re-authentication for a tenant member. See `refresh_admin`."""
    fresh = await retrying(
        lambda: client.post(
            "/v1/auth/token",
            json={"email": email, "password": PASSWORD, "tenant_id": org_id},
        ),
        200,
        what=f"re-login {email}",
    )
    headers["Authorization"] = f"Bearer {fresh['access_token']}"
    return headers


async def refresh_admin(client, admin: dict) -> dict:
    """Sign the platform admin in again, IN PLACE.

    DEMO-010 found this the only way it can be found: the dataset grew to
    sixteen customers and ~570 deliveries, the seed passed fifteen minutes, and
    the admin's access token expired part-way through — so building the second
    organization failed with a bare 401 after twenty minutes of correct work.
    Nothing was wrong except that a long job was holding a short-lived
    credential, which is exactly what a token lifetime is for.

    Mutating the dict rather than returning a new one keeps every caller
    holding the same object, so there is no way to keep using the stale one.
    """
    fresh = await retrying(
        lambda: client.post(
            "/v1/auth/token", json={"email": ADMIN_EMAIL, "password": PASSWORD}
        ),
        200,
        what="admin re-login",
    )
    admin["Authorization"] = f"Bearer {fresh['access_token']}"
    return admin


async def platform_admin(client) -> dict:
    """A platform administrator, reused across runs if it already exists."""
    email = ADMIN_EMAIL
    r = await client.post(
        "/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Demo Platform Admin"},
    )
    if r.status_code not in (201, 409):
        raise SeedError(
            f"demo seed failed at register admin: {r.status_code} {r.text[:300]}"
        )
    await grant_platform_admin(email)
    tokens = await retrying(
        lambda: client.post(
            "/v1/auth/token", json={"email": email, "password": PASSWORD}
        ),
        200,
        what="admin login",
    )
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def make_org(client, admin: dict, name: str, slug: str, country_code: str) -> dict:
    """DEMO-013: the country is supplied, never assumed.

    Nothing else is: the platform resolves currency, timezone and languages
    from it (`core/locales.py`), so this seeder states no money and no clock
    anywhere. If it did, it would be a second source of truth that could
    disagree with the tenant it just created.
    """
    org = await expect(
        await client.post(
            "/v1/organizations",
            json={"name": name, "slug": slug, "country_code": country_code},
            headers=admin,
        ),
        201,
        what=f"create organization {slug}",
    )
    return org


async def invite_and_capture_token(
    client, *, headers: dict, email: str, role_name: str
) -> str:
    """Issue an invitation and read the token out of the delivered message.

    The seeder runs the app in process, so it can install a provider that
    records what was sent — which is the only place the raw token ever appears.
    This is not a shortcut around the invitation boundary; it IS the boundary,
    exercised.
    """
    import re

    from platform_core.modules.notification import providers

    captured: dict[str, str] = {}

    class _CapturingEmailProvider:
        name = "demo-capture-email"

        async def send(self, message):
            captured["body"] = message.body
            return providers.DeliveryResult(
                provider_message_id=f"demo:{message.notification_id}",
                status=providers.ACCEPTED,
            )

    previous = providers.get_provider("email")
    providers.register_provider("email", _CapturingEmailProvider())
    try:
        await expect(
            await client.post(
                "/v1/invitations",
                json={"email": email, "role_name": role_name},
                headers=headers,
            ),
            201,
            what=f"invite {email}",
        )
    finally:
        providers.register_provider("email", previous)

    match = re.search(r"registration:\s*(\S+?)\.\s", captured.get("body", ""))
    if not match:
        raise SeedError(f"no invitation token in the message sent to {email}")
    return match.group(1)


async def make_member(
    client, admin: dict, org_id: str, *, email: str, full_name: str, role_name: str
) -> dict:
    """A real member of an organization, created through the invitation flow.

    Demo accounts a customer can actually sign in with — and, for the manager,
    the identity the whole dairy is then built under, so the audit trail reads
    like a person did the work rather than a script.
    """
    token = await invite_and_capture_token(
        client, headers=acting(admin, org_id), email=email, role_name=role_name
    )
    user = await retrying(
        lambda: client.post(
            "/v1/invitations/accept",
            json={"token": token, "password": PASSWORD, "full_name": full_name},
        ),
        201,
        what=f"accept invitation {email}",
    )
    tokens = await retrying(
        lambda: client.post(
            "/v1/auth/token",
            json={"email": email, "password": PASSWORD, "tenant_id": org_id},
        ),
        200,
        what=f"login {email}",
    )
    return {
        "id": user["id"],
        "email": email,
        "full_name": full_name,
        "role": role_name,
        "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
    }


def acting(admin: dict, org_id: str) -> dict:
    """A platform admin acting inside one organization.

    The platform treats a tenant-scoped TOKEN as authoritative and only honours
    this header for a platform session — which is exactly what the seeder is.
    """
    return {**admin, "X-Tenant-ID": org_id}


# --- the dairy ---------------------------------------------------------------


async def make_center(
    client, h: dict, branch_id: str, name: str, code: str, operator_id: str
) -> dict:
    """A centre that is actually READY — hours, active, an operator, a live scale.

    Readiness is not decoration: `collection-sessions` refuses to open at a
    centre that is not ready, so a demo whose centres are merely "created"
    cannot collect a single litre.
    """
    center = await expect(
        await client.post(
            "/v1/collection-centers",
            json={"branch_id": branch_id, "name": name, "code": code},
            headers=h,
        ),
        201,
        what=f"create centre {code}",
    )
    cid = center["id"]
    await expect(
        await client.put(
            f"/v1/collection-centers/{cid}/operating-hours",
            json={
                "windows": [
                    {"day_of_week": d, "opens": "06:00", "closes": "19:00"}
                    for d in range(7)
                ]
            },
            headers=h,
        ),
        200,
        what=f"hours {code}",
    )
    await expect(
        await client.post(
            f"/v1/collection-centers/{cid}/status", json={"status": "active"}, headers=h
        ),
        200,
        what=f"activate {code}",
    )
    await expect(
        await client.post(
            f"/v1/collection-centers/{cid}/operators",
            json={"user_id": operator_id},
            headers=h,
        ),
        201,
        200,
        what=f"operator {code}",
    )
    # DEMO-006: a scale is BLOCKING; an analyzer and a printer are WARNINGS.
    # Fitting all three is what a real centre does, and it is the difference
    # between a demo centre reporting READY and one reporting WARNING with two
    # checks failing — which is what DEMO-005 had to report honestly.
    for category, label in (
        ("scale", "scale"),
        ("milk_analyzer", "analyzer"),
        ("printer", "printer"),
    ):
        device = await expect(
            await client.post(
                "/v1/devices",
                json={
                    "category": category,
                    "serial_number": f"{category.upper()}-{code}",
                    "name": f"{name} {label}",
                },
                headers=h,
            ),
            201,
            what=f"{label} {code}",
        )
        await expect(
            await client.post(
                f"/v1/devices/{device['id']}/assign", json={"center_id": cid}, headers=h
            ),
            200,
            201,
            what=f"assign {label} {code}",
        )
        await expect(
            await client.post(
                f"/v1/devices/{device['id']}/status", json={"status": "active"}, headers=h
            ),
            200,
            what=f"activate {label} {code}",
        )
    return center


async def make_rate_card(
    client,
    h: dict,
    *,
    code: str,
    name: str,
    effective_from: str,
    effective_until: str | None,
    center_ids: list[str],
    bands,
    publish: bool,
) -> dict:
    card = await expect(
        await client.post(
            "/v1/rate-cards",
            json={
                "code": code,
                "name": name,
                "effective_from": effective_from,
                "effective_until": effective_until,
                "description": "Quality-banded rate for raw cow milk",
            },
            headers=h,
        ),
        201,
        what=f"rate card {code}",
    )
    for cid in center_ids:
        await expect(
            await client.post(
                f"/v1/rate-cards/{card['id']}/centers",
                json={"center_id": cid},
                headers=h,
            ),
            201,
            what=f"scope {code}",
        )
    await expect(
        await client.post(
            f"/v1/rate-cards/{card['id']}/products",
            json={"product_code": PRODUCT},
            headers=h,
        ),
        201,
        what=f"product {code}",
    )
    matrix = await expect(
        await client.post(
            "/v1/pricing-matrices",
            json={
                "rate_card_id": card["id"],
                "name": f"{name} — FAT bands",
                "product_code": PRODUCT,
                "dimension_code": "FAT",
            },
            headers=h,
        ),
        201,
        what=f"matrix {code}",
    )
    for from_value, to_value, price in bands:
        await expect(
            await client.post(
                f"/v1/pricing-matrices/{matrix['id']}/rows",
                json={
                    "from_value": from_value,
                    "to_value": to_value,
                    "unit_price": price,
                },
                headers=h,
            ),
            201,
            what=f"band {code} {from_value}",
        )
    if publish:
        # A rate card is not published by fiat: it is submitted, approved and
        # then published. Skipping the ceremony in a seeder would hide the very
        # governance a customer is being shown.
        for step in ("submit", "approve", "publish"):
            await expect(
                await client.post(f"/v1/rate-cards/{card['id']}/{step}", headers=h),
                200,
                what=f"{step} {code}",
            )
    return card


async def make_supplier(client, h: dict, name: str, index: int, center_id: str) -> dict:
    supplier = await expect(
        await client.post(
            "/v1/suppliers",
            json={"full_name": name, "phone": f"+2547{20000000 + index:08d}"},
            headers=h,
        ),
        201,
        what=f"supplier {name}",
    )
    await expect(
        await client.post(
            f"/v1/suppliers/{supplier['id']}/centers",
            json={"center_id": center_id},
            headers=h,
        ),
        201,
        what=f"assign {name}",
    )
    # A centre assignment must exist BEFORE activation: the platform refuses to
    # activate a supplier with nowhere to deliver.
    await expect(
        await client.post(
            f"/v1/suppliers/{supplier['id']}/status",
            json={"status": "active"},
            headers=h,
        ),
        200,
        what=f"activate {name}",
    )
    return supplier


async def collect_one(
    client,
    h: dict,
    *,
    session_id: str,
    supplier: dict,
    index: int,
    when: date,
    container: str,
) -> dict:
    """One collection, walked through the real state machine on a real date.

    Measurements are `manual` — the demo must never present mock hardware as a
    reading. `accept` and `complete` are separate steps because they are
    separate business decisions.
    """
    tx = await expect(
        await client.post(
            "/v1/milk-transactions", json={"session_id": session_id}, headers=h
        ),
        201,
        what="create transaction",
    )
    tid = tx["id"]

    # Before pricing: give the collection its real day (see module docstring).
    # 07:30 UTC is a plausible morning round and keeps every collection inside
    # the centre's operating window.
    await backdate_transaction(
        tid, datetime.combine(when, time(7, 30), tzinfo=timezone.utc)
    )

    gross, tare = WEIGHTS[index % len(WEIGHTS)]
    fat = FAT_BY_SUPPLIER[index % len(FAT_BY_SUPPLIER)]
    steps = [
        ("identify", {"method": "manual", "supplier_id": supplier["id"]}),
        (
            "milk",
            {
                "milk_type": "cow",
                "container_type": "can",
                "container_identifier": container,
                "temperature_c": 4.0,
            },
        ),
        ("weight", {"source": "manual", "unit": "kg", "gross": gross, "tare": tare}),
        (
            "quality",
            {
                "source": "manual",
                "fat": fat,
                "snf": round(8.0 + (index % 7) * 0.1, 2),
                "clr": round(26.0 + (index % 5) * 0.5, 2),
                "temperature_c": 4.0,
            },
        ),
    ]
    for name, body in steps:
        await expect(
            await client.post(
                f"/v1/milk-transactions/{tid}/{name}", json=body, headers=h
            ),
            200,
            what=f"transaction {name}",
        )
    return tid


async def accept_and_complete(client, h: dict, tid: str) -> dict:
    await expect(
        await client.post(f"/v1/milk-transactions/{tid}/accept", headers=h),
        200,
        what="accept",
    )
    return await expect(
        await client.post(f"/v1/milk-transactions/{tid}/complete", headers=h),
        200,
        what="complete",
    )


async def reject(client, h: dict, tid: str, reason: str) -> dict:
    """A rejected collection. Real dairies reject milk; a demo without a single
    rejection quietly implies the platform cannot express one."""
    return await expect(
        await client.post(
            f"/v1/milk-transactions/{tid}/reject", json={"reason": reason}, headers=h
        ),
        200,
        what="reject",
    )


async def settle(
    client,
    h: dict,
    *,
    supplier_id: str,
    center_id: str,
    period_from: date,
    period_to: date,
    finalize: bool,
) -> dict | None:
    """Create a settlement and sweep the period into it.

    Returns None when the sweep found nothing — an empty settlement cannot be
    finalized (the platform refuses), and a demo should not display one.
    """
    settlement = await expect(
        await client.post(
            "/v1/settlements",
            json={
                "supplier_id": supplier_id,
                "center_id": center_id,
                "period_from": period_from.isoformat(),
                "period_to": period_to.isoformat(),
            },
            headers=h,
        ),
        201,
        what="create settlement",
    )
    swept = await expect(
        await client.post(f"/v1/settlements/{settlement['id']}/collect", headers=h),
        200,
        what="collect period",
    )
    if not swept.get("added"):
        return None
    settlement = await expect(
        await client.post(f"/v1/settlements/{settlement['id']}/calculate", headers=h),
        200,
        what="calculate settlement",
    )
    if finalize:
        settlement = await expect(
            await client.post(
                f"/v1/settlements/{settlement['id']}/finalize", headers=h
            ),
            200,
            what="finalize settlement",
        )
    return settlement


async def pay(
    client,
    h: dict,
    *,
    supplier_id: str,
    settlement_id: str,
    method: str,
    reference: str,
    outcome: str,
) -> dict:
    """Take a finalized settlement through the payment lifecycle.

    `outcome` is one of completed | processing | failed, so the demo can show
    a payments screen that is not uniformly green.
    """
    payment = await expect(
        await client.post(
            "/v1/payments",
            json={
                "supplier_id": supplier_id,
                "method": method,
                "allocations": [{"settlement_id": settlement_id}],
                "idempotency_key": f"demo-{settlement_id}",
            },
            headers=h,
        ),
        201,
        what="create payment",
    )
    pid = payment["id"]
    for step in ("submit", "execute"):
        await expect(
            await client.post(f"/v1/payments/{pid}/{step}", json={}, headers=h),
            200,
            what=f"payment {step}",
        )
    if outcome == "completed":
        return await expect(
            await client.post(
                f"/v1/payments/{pid}/complete", json={"reference": reference}, headers=h
            ),
            200,
            what="payment complete",
        )
    if outcome == "failed":
        return await expect(
            await client.post(
                f"/v1/payments/{pid}/fail",
                json={"reason": "mobile money wallet not reachable"},
                headers=h,
            ),
            200,
            what="payment fail",
        )
    return payment  # left in `processing`


# --- orchestration -----------------------------------------------------------

# The timeline, relative to today (UTC). Chosen so the demo always shows a
# settled past, money waiting to move, and activity from this morning.
#
#   D-21 .. D-15   period A — finalized and PAID, with receipts
#   D-14 .. D-8    period B — finalized, awaiting payment / part paid
#   D-7  .. D-1    period C — a FEW suppliers settled but NOT finalized; the
#                  rest of the window left unswept
#   today          this morning's round, still in an open session
#
# DEMO-006 added period C. A demo where every settlement is already finalized
# can only ever show the end of the lifecycle: no Calculate, no Finalize, no
# irreversibility warning, because the platform correctly refuses all three on
# a frozen settlement. Period C leaves a handful of settlements CALCULATED so
# the last step can be taken live, and deliberately leaves the rest of the
# window unswept so `Collect period` has real collections to find.
HISTORY_DAYS = 21

# How many suppliers get an open (calculated, not finalized) settlement for
# period C. Three is enough to demonstrate finalization without turning the
# settlement list into a wall of drafts.
OPEN_SETTLEMENTS = 3


async def build_demo_org(client, admin: dict, org: dict, market: Market) -> dict:
    """The full dairy: users, centres, suppliers, rates, collections, money."""
    today = utc_today()
    summary: dict = {"organization": org["name"], "organization_id": org["id"]}

    manager = await make_member(
        client,
        admin,
        org["id"],
        email=f"manager@{market.email_domain}",
        full_name=market.staff["manager"],
        role_name="tenant-admin",
    )
    viewer = await make_member(
        client,
        admin,
        org["id"],
        email=f"viewer@{market.email_domain}",
        full_name=market.staff["viewer"],
        role_name="tenant-viewer",
    )
    # DEMO-010 §6: "how do different users see different things" is one of the
    # fourteen questions this demo has to answer, and it cannot be answered
    # with two accounts that are effectively all-or-nothing. These three are
    # the named roles from DEMO-008's registry, seeded as real members with
    # real grants, so the difference can be SHOWN by signing in — not
    # described. Nothing about them is special-cased anywhere: they are rows.
    operations = await make_member(
        client,
        admin,
        org["id"],
        email=f"operations@{market.email_domain}",
        full_name=market.staff["operations"],
        role_name="ORGANIZATION_MANAGER",
    )
    operator = await make_member(
        client,
        admin,
        org["id"],
        email=f"operator@{market.email_domain}",
        full_name=market.staff["operator"],
        role_name="COLLECTION_OPERATOR",
    )
    sales = await make_member(
        client,
        admin,
        org["id"],
        email=f"sales@{market.email_domain}",
        full_name=market.staff["sales"],
        role_name="SALES_OFFICER",
    )
    summary["users"] = [
        {"email": u["email"], "name": u["full_name"], "role": u["role"]}
        for u in (manager, viewer, operations, operator, sales)
    ]
    # Everything below is done AS the manager, so the audit trail names a
    # person with the permissions to have done it.
    h = manager["headers"]
    admin_user_id = manager["id"]

    ws = await expect(
        await client.post(
            "/v1/workspaces",
            json={"name": "Central Region", "slug": "central"},
            headers=h,
        ),
        201,
        what="workspace",
    )
    branch = await expect(
        await client.post(
            "/v1/branches",
            json={"workspace_id": ws["id"], "name": "Central Dairy Hub", "code": "CDH"},
            headers=h,
        ),
        201,
        what="branch",
    )

    centers = [
        await make_center(client, h, branch["id"], name, code, admin_user_id)
        for name, code in market.centers
    ]
    summary["centers"] = [c["code"] for c in centers]

    # Two rate cards: the one in force, and a superseded one that shows the
    # customer their price history is kept, not overwritten.
    await make_rate_card(
        client,
        h,
        code="RC-2025-LEGACY",
        name="2025 Season Rates",
        effective_from=(today - timedelta(days=365)).isoformat(),
        effective_until=(today - timedelta(days=HISTORY_DAYS + 1)).isoformat(),
        center_ids=[c["id"] for c in centers],
        # Last season, derived from this market's own rates rather than
        # stated: a demo with a Kenyan legacy card and Indian current rates
        # would show a co-operative a pay rise nobody gave.
        bands=[(lo, hi, round(rate - 3.0, 2)) for lo, hi, rate in market.fat_bands],
        publish=True,
    )
    current = await make_rate_card(
        client,
        h,
        code="RC-2026-MAIN",
        name="2026 Main Season Rates",
        effective_from=(today - timedelta(days=HISTORY_DAYS)).isoformat(),
        effective_until=None,
        center_ids=[c["id"] for c in centers],
        bands=market.fat_bands,
        publish=True,
    )
    # A draft card as well: rate cards under review are a real state, and a
    # demo that only ever shows `published` hides the approval workflow.
    await make_rate_card(
        client,
        h,
        code="RC-2027-DRAFT",
        name="2027 Proposed Rates (draft)",
        effective_from=(today + timedelta(days=90)).isoformat(),
        effective_until=None,
        center_ids=[c["id"] for c in centers],
        bands=[(lo, hi, round(rate + 2.0, 2)) for lo, hi, rate in market.fat_bands],
        publish=False,
    )
    summary["rate_cards"] = ["RC-2025-LEGACY", "RC-2026-MAIN", "RC-2027-DRAFT"]

    suppliers = []
    for i, name in enumerate(market.supplier_names):
        center = centers[i % len(centers)]
        suppliers.append(
            {**await make_supplier(client, h, name, i, center["id"]), "_center": center}
        )
    summary["suppliers"] = len(suppliers)

    # --- collections ---------------------------------------------------------
    # One session per centre per day, closed before the next opens, because a
    # centre may hold only one open session.
    completed: dict[str, list[str]] = {}
    rejected = 0
    for day_offset in range(HISTORY_DAYS, -1, -1):
        day = today - timedelta(days=day_offset)
        for center in centers:
            todays = [
                s for i, s in enumerate(suppliers) if s["_center"]["id"] == center["id"]
            ]
            # Not every supplier delivers every day — a dairy where all 24
            # arrive daily reads as generated data.
            delivering = [s for i, s in enumerate(todays) if (i + day_offset) % 3 != 0]
            if not delivering:
                continue
            session = await expect(
                await client.post(
                    "/v1/collection-sessions",
                    json={
                        "center_id": center["id"],
                        "label": f"{day.isoformat()} morning",
                    },
                    headers=h,
                ),
                201,
                what="open session",
            )
            for n, supplier in enumerate(delivering):
                idx = suppliers.index(supplier)
                tid = await collect_one(
                    client,
                    h,
                    session_id=session["id"],
                    supplier=supplier,
                    index=idx,
                    when=day,
                    container=f"CAN-{center['code']}-{n + 1:02d}",
                )
                # One rejection in the whole history, on a single day, so the
                # rejection path is demonstrable without implying a quality crisis.
                if day_offset == 5 and n == 0 and center is centers[0]:
                    await reject(client, h, tid, "failed organoleptic check at intake")
                    # A rejected collection is still COMPLETED as a transaction:
                    # the milk was refused, the paperwork was not abandoned. The
                    # session cannot close while anything is in flight.
                    await expect(
                        await client.post(
                            f"/v1/milk-transactions/{tid}/complete", headers=h
                        ),
                        200,
                        what="complete rejected transaction",
                    )
                    rejected += 1
                    continue
                await accept_and_complete(client, h, tid)
                completed.setdefault(supplier["id"], []).append(tid)
            # Today's session stays OPEN — the demo should show work in progress.
            if day_offset != 0:
                await expect(
                    await client.post(
                        f"/v1/collection-sessions/{session['id']}/close", headers=h
                    ),
                    200,
                    what="close session",
                )
    summary["transactions_completed"] = sum(len(v) for v in completed.values())
    summary["transactions_rejected"] = rejected
    return {
        "summary": summary,
        "headers": h,
        "centers": centers,
        "suppliers": suppliers,
        "today": today,
        "current_card": current,
        # DEMO-012: `make_customer_login` invites a member, which needs the
        # platform admin and the organization the invitation belongs to.
        "admin": admin,
        "org": org,
        # DEMO-013: which market this tenant is, so the later phases build the
        # right households without asking what country they are in.
        "market": market,
    }


async def build_money(client, built: dict) -> dict:
    """Settlements, payments and receipts over the collected history.

    Period A is settled and paid; period B is settled and awaiting money. Both
    are driven per supplier, because BR-0009 keys the no-overlap rule on the
    supplier alone.
    """
    h, today = built["headers"], built["today"]
    suppliers = built["suppliers"]
    a_from, a_to = today - timedelta(days=21), today - timedelta(days=15)
    b_from, b_to = today - timedelta(days=14), today - timedelta(days=8)
    c_from, c_to = today - timedelta(days=7), today - timedelta(days=1)

    counts = {
        "finalized": 0,
        "paid": 0,
        "awaiting_payment": 0,
        "failed": 0,
        "processing": 0,
        "open_calculated": 0,
    }
    paid_settlements = []
    for i, supplier in enumerate(suppliers):
        center = supplier["_center"]
        a = await settle(
            client,
            h,
            supplier_id=supplier["id"],
            center_id=center["id"],
            period_from=a_from,
            period_to=a_to,
            finalize=True,
        )
        if a:
            counts["finalized"] += 1
            # Most payments succeed; a few show the states an operator must
            # actually handle. Deterministic by index, not random.
            outcome = "completed"
            if i % 11 == 7:
                outcome = "failed"
            elif i % 11 == 4:
                outcome = "processing"
            await pay(
                client,
                h,
                supplier_id=supplier["id"],
                settlement_id=a["id"],
                method="MOBILE_MONEY" if i % 3 else "BANK_TRANSFER",
                reference=f"MPESA-{a['settlement_number']}",
                outcome=outcome,
            )
            counts[
                {"completed": "paid", "failed": "failed", "processing": "processing"}[
                    outcome
                ]
            ] += 1
            if outcome == "completed":
                paid_settlements.append(a["settlement_number"])

        b = await settle(
            client,
            h,
            supplier_id=supplier["id"],
            center_id=center["id"],
            period_from=b_from,
            period_to=b_to,
            finalize=True,
        )
        if b:
            counts["finalized"] += 1
            counts["awaiting_payment"] += 1

        # Period C for the first three suppliers only — calculated, deliberately
        # not finalized. Everyone else's last week stays unsettled, which is
        # what makes a live `Collect period` find anything.
        if i < OPEN_SETTLEMENTS:
            c = await settle(
                client,
                h,
                supplier_id=supplier["id"],
                center_id=center["id"],
                period_from=c_from,
                period_to=c_to,
                finalize=False,
            )
            if c:
                counts["open_calculated"] += 1

    built["summary"]["settlements"] = counts
    built["summary"]["paid_settlement_numbers"] = paid_settlements[:5]
    return built


async def build_sales(client, built: dict) -> dict:
    """Customers, a month of deliveries, bills, payments and receipts.

    DEMO-009. Every figure comes from the platform: the delivery amount is
    computed by the domain from the customer's agreed rate, the bill is built
    from those deliveries, and the receipt is generated by the consumer from
    the payment event. The seeder chooses WHO and HOW MUCH; it never computes
    a total.
    """
    h, today = built["headers"], built["today"]
    market: Market = built["market"]
    summary = {
        "customers": 0,
        "deliveries": 0,
        "bills_issued": 0,
        "paid": 0,
        "part_paid": 0,
        "unpaid": 0,
        "unbilled": 0,
    }
    records = []

    for index, (name, kind, phone, address, litres, rate, pattern, evening) in enumerate(
        market.customers
    ):
        customer = await expect(
            await client.post(
                "/v1/customers",
                json={
                    "name": name,
                    "customer_type": kind,
                    "phone": phone,
                    "address": address,
                    "billing_mode": "credit",
                    "billing_day": 1,
                    "plan": {
                        "product": "RAW-COW-MILK",
                        "default_quantity": litres,
                        "quantity_unit": "L",
                        "unit_price": rate,
                    },
                },
                headers=h,
            ),
            201,
            what=f"customer {name}",
        )
        summary["customers"] += 1

        # A month of deliveries. A few days are skipped, deterministically, so
        # the report has something other than a straight line to show — and so
        # that "milk delivered" and "days in the month" are visibly not the
        # same number, which is the thing a dairy owner checks first.
        slots = ["morning", "evening"] if evening else ["morning"]
        for day_offset in range(DELIVERY_DAYS, 0, -1):
            day = today - timedelta(days=day_offset)
            skipped = (day_offset + index) % 11 == 0
            for slot in slots:
                body = {
                    "customer_id": customer["id"],
                    "delivery_date": day.isoformat(),
                    "slot": slot,
                    "status": "skipped" if skipped else "delivered",
                }
                # Households vary a little day to day; institutions do not.
                if not skipped and kind == "household" and day_offset % 5 == 0:
                    body["quantity"] = str(Decimal(litres) + Decimal("0.500"))
                # An evening round is smaller than a morning one.
                elif not skipped and slot == "evening":
                    body["quantity"] = str(
                        (Decimal(litres) / 2).quantize(Decimal("0.001"))
                    )
                # Strict. This used to be `if r.status_code == 201`, which
                # meant a run where every delivery was refused still reported
                # success with a smaller number — the seeder's job is to prove
                # the dataset, so a refusal has to stop it.
                await expect(
                    await client.post("/v1/deliveries", json=body, headers=h),
                    201,
                    what=f"delivery {name} {day} {slot}",
                )
                summary["deliveries"] += 1

        if pattern == "unbilled":
            summary["unbilled"] += 1
            records.append({"customer": name, "state": "delivered, not yet billed"})
            continue

        if pattern == "showcase":
            # DEMO-015 §18: the one customer a demonstration is walked
            # through. Two bills over two halves of the window rather than one
            # over all of it, because a statement that opens at zero cannot
            # show what an opening balance IS — and "what does this customer
            # owe me, and how did they come to owe it?" is the question the
            # statement exists to answer.
            records.append(
                await seed_showcase_ledger(client, h, customer=customer, name=name, today=today)
            )
            summary["bills_issued"] += 2
            summary["paid"] += 1
            summary["unpaid"] += 1
            summary["showcase"] = name
            if index == 0:
                first_customer = customer
            continue

        # Bill the completed month: everything up to yesterday.
        invoice = await expect(
            await client.post(
                "/v1/invoices",
                json={
                    "customer_id": customer["id"],
                    "period_from": (today - timedelta(days=DELIVERY_DAYS)).isoformat(),
                    "period_to": (today - timedelta(days=1)).isoformat(),
                },
                headers=h,
            ),
            201,
            what=f"invoice for {name}",
        )
        invoice = await expect(
            await client.post(f"/v1/invoices/{invoice['id']}/issue", json={}, headers=h),
            200,
            what=f"issue invoice for {name}",
        )
        summary["bills_issued"] += 1

        due = Decimal(str(invoice["amount_due"]))
        if pattern == "paid":
            paid = due
            summary["paid"] += 1
        elif pattern == "partial":
            paid = (due / 2).quantize(Decimal("0.01"))
            summary["part_paid"] += 1
        else:
            paid = Decimal("0.00")
            summary["unpaid"] += 1

        if paid > 0:
            await expect(
                await client.post(
                    "/v1/customer-payments",
                    json={
                        "customer_id": customer["id"],
                        "amount": str(paid),
                        "method": "MOBILE_MONEY" if index % 2 else "CASH",
                        "reference": f"MPESA-{invoice['invoice_number']}",
                    },
                    headers=h,
                ),
                201,
                what=f"payment for {name}",
            )

        records.append(
            {
                "customer": name,
                "invoice": invoice["invoice_number"],
                "amount_due": str(due),
                "paid": str(paid),
                "state": pattern,
            }
        )
        if index == 0:
            first_customer = customer

    summary["ledger"] = records
    # DEMO-012 §4: a login that IS a customer, so the mobile customer
    # experience can be shown rather than described. Bound to the first
    # household, which is `partial` — it has a bill, a part payment and a
    # receipt, so the app has a balance, a bill and a receipt to render
    # instead of four empty cards.
    summary["customer_login"] = await make_customer_login(
        client, built, customer=first_customer
    )
    built["summary"]["sales"] = summary
    return built


async def seed_showcase_ledger(client, h: dict, *, customer: dict, name: str, today) -> dict:
    """Two bills, one paid, one not — the deterministic demo scenario.

    The window is split in half. The FIRST half is billed, issued and paid in
    full, which produces a receipt through the consumer exactly as any payment
    does. The SECOND half is billed and issued and left alone.

    What that arrangement buys, and why it is worth the extra requests:

      * the customer's statement OPENS with a brought-forward balance instead
        of at zero, so the opening-balance line is demonstrably doing work;
      * the running balance moves twice, down and then up, so a reader can see
        it is arithmetic rather than a repeated total;
      * there is one paid bill with a receipt to open, and one outstanding
        bill to collect — which is the whole receivables story on one screen.

    Every figure is still the platform's. This chooses dates and who pays; it
    computes nothing.
    """
    first_from = today - timedelta(days=DELIVERY_DAYS)
    first_to = today - timedelta(days=(DELIVERY_DAYS // 2) + 1)
    second_from = today - timedelta(days=DELIVERY_DAYS // 2)
    second_to = today - timedelta(days=1)

    async def bill(period_from, period_to, what):
        draft = await expect(
            await client.post(
                "/v1/invoices",
                json={
                    "customer_id": customer["id"],
                    "period_from": period_from.isoformat(),
                    "period_to": period_to.isoformat(),
                },
                headers=h,
            ),
            201,
            what=f"{what} for {name}",
        )
        return await expect(
            await client.post(f"/v1/invoices/{draft['id']}/issue", json={}, headers=h),
            200,
            what=f"issue {what} for {name}",
        )

    settled = await bill(first_from, first_to, "showcase bill 1")
    # `total`, not `amount_due`: the first bill has no brought-forward balance,
    # and paying the total is what closes it. Paying `amount_due` on a later
    # bill would be paying the previous month twice.
    await expect(
        await client.post(
            "/v1/customer-payments",
            json={
                "customer_id": customer["id"],
                "amount": str(Decimal(str(settled["total"]))),
                "method": "BANK_TRANSFER",
                "reference": f"NEFT-{settled['invoice_number']}",
                "invoice_ids": [settled["id"]],
            },
            headers=h,
        ),
        201,
        what=f"showcase payment for {name}",
    )
    outstanding = await bill(second_from, second_to, "showcase bill 2")

    return {
        "customer": name,
        "state": "showcase",
        "settled_invoice": settled["invoice_number"],
        "settled_amount": str(settled["total"]),
        "outstanding_invoice": outstanding["invoice_number"],
        "outstanding_amount": str(outstanding["amount_due"]),
    }


async def make_customer_login(client, built: dict, *, customer: dict) -> dict:
    """A household that can sign in to the mobile app and see its own account.

    Two steps, and the second is the interesting one.

    The member is invited and accepts exactly like any other member, with the
    `CUSTOMER_PORTAL` role — five read permissions, and nothing that could
    change anything. That part is ordinary.

    The BINDING is a direct write, because there is deliberately no API that
    sets `customer_id` from a request body. A scope that an administrator
    could set by hand is a scope an administrator could set WRONG, and the
    failure mode is one household reading another's bills — so DEMO-012 left
    it out of the API surface entirely and this seeder does what a migration
    or an operator with database access would do. The limitation is recorded
    in DEMO-012-FINAL.md rather than worked around with a hidden endpoint.
    """
    market: Market = built["market"]
    email = f"household@{market.email_domain}"
    # This runs at the very end of the sales phase, twenty minutes after the
    # admin signed in. DEMO-010 already found what that costs: a long job
    # holding a short-lived credential fails with a bare 401 after twenty
    # minutes of correct work.
    await refresh_admin(client, built["admin"])
    member = await make_member(
        client,
        built["admin"],
        built["org"]["id"],
        email=email,
        full_name=market.staff["household"],
        role_name="CUSTOMER_PORTAL",
    )

    from sqlalchemy import select

    from platform_core.core.rls import platform_factory
    from platform_core.modules.identity.models import User

    async with platform_factory("demo seed: bind a customer login")() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            raise SeedError("customer login was not created")
        user.customer_id = uuid.UUID(customer["id"])
        await session.commit()

    return {
        "email": email,
        "name": member["full_name"],
        "role": "CUSTOMER_PORTAL",
        "customer": customer["name"],
        "customer_id": customer["id"],
    }


async def demonstrate_br_0027(client, built: dict) -> dict:
    """A late collection, carried forward — BR-0027, shown rather than described.

    A collection is recorded INTO period A after period A was finalized. Its own
    period is closed forever, so it is stranded exactly as PILOT-001 found; the
    fix carries it into a later open settlement, which is what a customer needs
    to see actually working.
    """
    h, today = built["headers"], built["today"]
    # DEMO-010: NOT supplier 0. The first `OPEN_SETTLEMENTS` suppliers are left
    # with an open, calculated period C covering `today-7 .. today-1`, and the
    # carry-forward settlement below is dated `today-7` — so on supplier 0 it
    # collided with that open period and the platform correctly refused it
    # ("period overlaps settlement ... for this supplier"), aborting the entire
    # seed. Found by running the seeder, not by reading it. Picking the first
    # supplier PAST that window keeps the demonstration identical — periods A
    # and B are finalized either way — and removes the collision.
    supplier = built["suppliers"][OPEN_SETTLEMENTS]
    center = supplier["_center"]
    late_day = today - timedelta(days=18)  # inside the finalized period A

    session = await expect(
        await client.post(
            "/v1/collection-sessions",
            json={"center_id": center["id"], "label": "late slip entry"},
            headers=h,
        ),
        201,
        409,
        what="late session",
    )
    if "id" not in session:  # a session is already open at this centre — reuse it
        page = await expect(
            await client.get(
                f"/v1/collection-sessions?center_id={center['id']}&status=open",
                headers=h,
            ),
            200,
            what="find open session",
        )
        session = page["items"][0]

    tid = await collect_one(
        client,
        h,
        session_id=session["id"],
        supplier=supplier,
        index=0,
        when=late_day,
        container="CAN-LATE-01",
    )
    await accept_and_complete(client, h, tid)

    # Its own period is closed, so it lands in a settlement dated after it.
    carry_from = today - timedelta(days=7)
    carried = await settle(
        client,
        h,
        supplier_id=supplier["id"],
        center_id=center["id"],
        period_from=carry_from,
        period_to=carry_from,
        finalize=True,
    )
    if carried:
        await pay(
            client,
            h,
            supplier_id=supplier["id"],
            settlement_id=carried["id"],
            method="MOBILE_MONEY",
            reference=f"MPESA-LATE-{carried['settlement_number']}",
            outcome="completed",
        )
        built["summary"]["br_0027_carry_forward"] = {
            "late_collection_date": late_day.isoformat(),
            "carried_into": carried["settlement_number"],
            "settlement_period": carry_from.isoformat(),
            "net_amount": str(carried["net_amount"]),
        }
    return built


async def build_isolation_org(client, admin: dict, org: dict, market: Market = KENYA) -> dict:
    """A second, deliberately small organization.

    Its whole job is to make tenant isolation demonstrable: sign in here and the
    24 suppliers next door are not merely hidden from the list, they answer 404.
    """
    today = utc_today()
    manager = await make_member(
        client,
        admin,
        org["id"],
        email="manager@lacteva-isolation.example.com",
        full_name="Chelimo Kiplagat",
        role_name="tenant-admin",
    )
    h = manager["headers"]
    admin_user_id = manager["id"]
    ws = await expect(
        await client.post(
            "/v1/workspaces", json={"name": "Rift Region", "slug": "rift"}, headers=h
        ),
        201,
        what="isolation workspace",
    )
    branch = await expect(
        await client.post(
            "/v1/branches",
            json={"workspace_id": ws["id"], "name": "Rift Valley Hub", "code": "RVH"},
            headers=h,
        ),
        201,
        what="isolation branch",
    )
    center = await make_center(
        client, h, branch["id"], "Eldoret Ridge Centre", "ER-C1", admin_user_id
    )
    await make_rate_card(
        client,
        h,
        code="RC-RIFT-2026",
        name="Rift Valley Rates",
        effective_from=(today - timedelta(days=30)).isoformat(),
        effective_until=None,
        center_ids=[center["id"]],
        bands=market.fat_bands,
        publish=True,
    )
    suppliers = [
        await make_supplier(client, h, name, 100 + i, center["id"])
        for i, name in enumerate(["Kiptoo Langat", "Nancy Jepkosgei", "Wilson Kibet"])
    ]
    session = await expect(
        await client.post(
            "/v1/collection-sessions",
            json={"center_id": center["id"], "label": "morning"},
            headers=h,
        ),
        201,
        what="isolation session",
    )
    for i, supplier in enumerate(suppliers):
        tid = await collect_one(
            client,
            h,
            session_id=session["id"],
            supplier=supplier,
            index=i,
            when=today,
            container=f"CAN-ER-{i + 1:02d}",
        )
        await accept_and_complete(client, h, tid)
    return {
        "organization": org["name"],
        "organization_id": org["id"],
        "users": [
            {
                "email": manager["email"],
                "name": manager["full_name"],
                "role": manager["role"],
            }
        ],
        "centers": ["ER-C1"],
        "suppliers": len(suppliers),
        "transactions_completed": len(suppliers),
    }


# --- verify / purge ----------------------------------------------------------


async def demo_org_ids() -> list[str]:
    from platform_core.core.rls import platform_factory
    from platform_core.modules.organization.models import Organization
    from sqlalchemy import select

    async with platform_factory("demo seed: locate demo organizations")() as session:
        rows = await session.scalars(
            select(Organization.id).where(
                Organization.slug.in_(DEMO_SLUGS)
            )
        )
        return [str(x) for x in rows.all()]


async def purge() -> dict:
    """Delete every row belonging to the demo organizations — and nothing else.

    The table list comes from `core/rls.py`'s own declaration of what is
    tenant-owned, so a table added later is covered without editing this script.
    Deletion is ordered children-first via SQLAlchemy's sorted metadata.
    """
    from platform_core.core.db import Base
    from platform_core.core.model_registry import import_all_models
    from platform_core.core.rls import platform_factory, tenant_tables
    from platform_core.modules.organization.models import Organization
    from sqlalchemy import delete, text

    import_all_models()
    ids = await demo_org_ids()
    if not ids:
        return {"organizations_removed": 0, "rows_deleted": 0}

    owned = set(tenant_tables())
    removed = 0
    async with platform_factory("demo seed: purge the demo organizations")() as session:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name not in owned or "tenant_id" not in table.c:
                continue
            result = await session.execute(
                delete(table).where(
                    table.c.tenant_id.in_([__import__("uuid").UUID(i) for i in ids])
                )
            )
            removed += result.rowcount or 0
        # The organization row itself is platform-global, not tenant-owned.
        result = await session.execute(
            delete(Organization).where(
                Organization.slug.in_(DEMO_SLUGS)
            )
        )
        await session.commit()
    _ = text  # imported for callers that want ad-hoc checks
    return {"organizations_removed": len(ids), "rows_deleted": removed}


async def verify() -> dict:
    """Assert the demo dataset is present, complete and internally consistent."""
    from platform_core.core.rls import platform_factory
    from platform_core.modules.milk_collection.models import MilkCollectionTransaction
    from platform_core.modules.organization.models import Organization
    from platform_core.modules.payment.models import Payment, PaymentLine
    from platform_core.modules.receipt.models import Receipt
    from platform_core.modules.settlement.models import Settlement, SettlementLine
    from platform_core.modules.supplier.models import Supplier
    from sqlalchemy import func, select

    ids = [__import__("uuid").UUID(i) for i in await demo_org_ids()]
    if not ids:
        raise SeedError("demo data is NOT present: no demo organizations found")

    checks: dict = {}
    problems: list[str] = []
    async with platform_factory("demo seed: verify")() as session:
        checks["organizations"] = len(
            (
                await session.scalars(
                    select(Organization.id).where(Organization.id.in_(ids))
                )
            ).all()
        )
        for label, model in (
            ("suppliers", Supplier),
            ("transactions", MilkCollectionTransaction),
            ("settlements", Settlement),
            ("payments", Payment),
            ("receipts", Receipt),
        ):
            checks[label] = await session.scalar(
                select(func.count()).select_from(model).where(model.tenant_id.in_(ids))
            )
        checks["completed_transactions"] = await session.scalar(
            select(func.count())
            .select_from(MilkCollectionTransaction)
            .where(
                MilkCollectionTransaction.tenant_id.in_(ids),
                MilkCollectionTransaction.state == "COMPLETED",
            )
        )
        checks["finalized_settlements"] = await session.scalar(
            select(func.count())
            .select_from(Settlement)
            .where(Settlement.tenant_id.in_(ids), Settlement.status == "finalized")
        )
        # BR-0011: every settlement's stored net must equal gross + adjustments.
        rows = (
            await session.scalars(
                select(Settlement).where(Settlement.tenant_id.in_(ids))
            )
        ).all()
        for s in rows:
            if Decimal(s.net_amount) != Decimal(s.gross_amount) + Decimal(
                s.adjustments_amount
            ):
                problems.append(f"{s.settlement_number}: net != gross + adjustments")
        # No settlement may be finalized with nothing in it.
        empty = [
            s.settlement_number
            for s in rows
            if s.status == "finalized" and not s.gross_amount
        ]
        problems.extend(f"{n}: finalized with zero gross" for n in empty)

        # DEMO-009: the sales side must reconcile too — an invoice against the
        # deliveries it billed, and a receipt against the payment that produced
        # it. Same rule as the procurement half: reading a total is not
        # verifying it.
        from platform_core.modules.billing.models import (
            CustomerInvoice,
            CustomerInvoiceLine,
            CustomerPayment,
            CustomerReceipt,
        )
        from platform_core.modules.customer.models import Customer
        from platform_core.modules.delivery.models import MilkDelivery

        for label, model in (
            ("customers", Customer),
            ("deliveries", MilkDelivery),
            ("customer_invoices", CustomerInvoice),
            ("customer_payments", CustomerPayment),
            ("customer_receipts", CustomerReceipt),
        ):
            checks[label] = await session.scalar(
                select(func.count()).select_from(model).where(model.tenant_id.in_(ids))
            )

        invoice_lines = dict(
            (
                await session.execute(
                    select(
                        CustomerInvoiceLine.invoice_id,
                        func.sum(CustomerInvoiceLine.amount),
                    )
                    .where(CustomerInvoiceLine.tenant_id.in_(ids))
                    .group_by(CustomerInvoiceLine.invoice_id)
                )
            ).all()
        )
        for invoice in (
            await session.scalars(
                select(CustomerInvoice).where(CustomerInvoice.tenant_id.in_(ids))
            )
        ).all():
            expected = Decimal(invoice_lines.get(invoice.id) or 0)
            if Decimal(invoice.subtotal) != expected:
                problems.append(
                    f"{invoice.invoice_number}: subtotal {invoice.subtotal} != lines {expected}"
                )
            if Decimal(invoice.amount_due) != Decimal(invoice.total) + Decimal(
                invoice.previous_balance
            ):
                problems.append(
                    f"{invoice.invoice_number}: amount due != total + brought forward"
                )

        customer_payments = {
            p.id: p
            for p in (
                await session.scalars(
                    select(CustomerPayment).where(CustomerPayment.tenant_id.in_(ids))
                )
            ).all()
        }
        for receipt in (
            await session.scalars(select(CustomerReceipt).where(CustomerReceipt.tenant_id.in_(ids)))
        ).all():
            payment = customer_payments.get(receipt.payment_id)
            if payment is None:
                problems.append(f"{receipt.receipt_number}: receipt for an unknown payment")
            elif Decimal(receipt.amount) != Decimal(payment.amount):
                problems.append(
                    f"{receipt.receipt_number}: {receipt.amount} != payment {payment.amount}"
                )

        # DEMO-006 reconciliation. Reading a total is not verifying it: each
        # of these re-derives a stored figure from the rows underneath it, and
        # a mismatch means the platform is displaying money it did not compute.
        checks["open_settlements"] = sum(
            1 for s in rows if s.status in ("draft", "calculated")
        )
        line_sums = dict(
            (
                await session.execute(
                    select(
                        SettlementLine.settlement_id,
                        func.sum(SettlementLine.gross_amount),
                    )
                    .where(SettlementLine.tenant_id.in_(ids))
                    .group_by(SettlementLine.settlement_id)
                )
            ).all()
        )
        for s in rows:
            if s.status not in ("calculated", "finalized"):
                continue
            expected = Decimal(line_sums.get(s.id) or 0)
            if Decimal(s.gross_amount) != expected:
                problems.append(
                    f"{s.settlement_number}: gross {s.gross_amount} != lines {expected}"
                )

        allocations = dict(
            (
                await session.execute(
                    select(PaymentLine.payment_id, func.sum(PaymentLine.amount))
                    .where(PaymentLine.tenant_id.in_(ids))
                    .group_by(PaymentLine.payment_id)
                )
            ).all()
        )
        payments = (
            await session.scalars(select(Payment).where(Payment.tenant_id.in_(ids)))
        ).all()
        by_payment = {p.id: p for p in payments}
        for pay_row in payments:
            expected = Decimal(allocations.get(pay_row.id) or 0)
            if Decimal(pay_row.amount) != expected:
                problems.append(
                    f"{pay_row.payment_number}: amount {pay_row.amount} "
                    f"!= allocations {expected}"
                )

        receipts = (
            await session.scalars(select(Receipt).where(Receipt.tenant_id.in_(ids)))
        ).all()
        for r in receipts:
            source = by_payment.get(r.payment_id)
            if source is None:
                problems.append(f"{r.receipt_number}: receipt for an unknown payment")
                continue
            if source.status != "completed":
                problems.append(
                    f"{r.receipt_number}: receipt for a {source.status} payment"
                )
            if Decimal(r.net_amount) != Decimal(source.amount):
                problems.append(
                    f"{r.receipt_number}: net {r.net_amount} != payment {source.amount}"
                )

    for label, minimum in (
        ("organizations", 2),
        ("suppliers", 20),
        ("completed_transactions", 50),
        ("finalized_settlements", 5),
        ("payments", 5),
        ("receipts", 5),
        # DEMO-006: a demo with nothing left to finalize cannot show the
        # lifecycle at all.
        ("open_settlements", 1),
        # DEMO-009: the customer workflow needs customers to demonstrate.
        ("customers", 5),
        ("deliveries", 50),
        ("customer_invoices", 3),
        ("customer_payments", 2),
    ):
        if (checks.get(label) or 0) < minimum:
            problems.append(
                f"{label}: {checks.get(label)} < expected minimum {minimum}"
            )

    checks["problems"] = problems
    checks["ok"] = not problems
    return checks


# --- entry point -------------------------------------------------------------


async def seed(markets: tuple[Market, ...] = (KENYA, INDIA)) -> dict:
    """Build the demo tenants.

    DEMO-013: which markets is a parameter, because a deployment that already
    carries one of them must be able to add another without recreating it —
    slugs are unique, so `seed` on a host that already has the Kenyan demo
    would fail at the first organization and leave nothing.
    """
    from platform_core.main import create_app

    await bootstrap()
    client = AsgiClient(create_app())

    admin = await platform_admin(client)
    # Only where it does not exist yet, for the same reason.
    isolation = None
    if KENYA in markets:
        isolation = await make_org(
            client, admin, ISOLATION_ORG, ISOLATION_ORG_SLUG, KENYA.country_code
        )

    # DEMO-013: one loop, two countries, and no branch inside it. Each market
    # is built by the same code from a different profile — which is the claim
    # the Indian demo exists to make. Kenya first, so a partial run still
    # leaves the older demo whole.
    summaries: dict = {}
    for market in markets:
        org = await make_org(
            client, admin, market.org_name, market.org_slug, market.country_code
        )
        built = await build_demo_org(client, admin, org, market)
        built = await build_money(client, built)
        built = await demonstrate_br_0027(client, built)
        # The sales phase is the last and longest thing the manager does, and
        # it starts a long way from their login.
        await refresh_member(
            client,
            built["headers"],
            f"manager@{market.email_domain}",
            built["summary"]["organization_id"],
        )
        built = await build_sales(client, built)
        # Receipts and notifications are consumer work, exactly as in production.
        await run_consumers()
        summaries[market.key] = built["summary"]
        # Each market takes the better part of twenty minutes. The admin token
        # that created the organizations is older than that by the end of it.
        await refresh_admin(client, admin)

    isolation_summary = None
    if isolation is not None:
        isolation_summary = await build_isolation_org(client, admin, isolation)
        await run_consumers()

    return {
        # `demo` stays the Kenyan tenant under its old key: DEMO-010 and
        # DEMO-011 evidence refers to it, and renaming it in the summary would
        # break every script that reads this output.
        **({"demo": summaries["kenya"]} if "kenya" in summaries else {}),
        **({"india": summaries["india"]} if "india" in summaries else {}),
        **({"isolation": isolation_summary} if isolation_summary else {}),
    }


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "seed"
    import json

    if command == "seed":
        # `seed` builds every market; `seed india` builds one. The second form
        # is how a deployment that already carries the Kenyan demo gains the
        # Indian one without touching it.
        names = sys.argv[2:] or list(MARKETS)
        unknown = [n for n in names if n not in MARKETS]
        if unknown:
            print(f"unknown market(s) {unknown} — known: {sorted(MARKETS)}", file=sys.stderr)
            return 2
        chosen = tuple(MARKETS[n] for n in names)
        print(json.dumps(asyncio.run(seed(chosen)), indent=2))
        return 0
    if command == "purge":
        print(json.dumps(asyncio.run(purge()), indent=2))
        return 0
    if command == "reset":
        print(json.dumps(asyncio.run(purge()), indent=2))
        print(json.dumps(asyncio.run(seed()), indent=2))
        return 0
    if command == "consumers":
        # Useful on its own: after a restore, or when a demo was seeded while
        # the deployed worker loop was not running.
        print(json.dumps(asyncio.run(run_consumers()), indent=2))
        return 0
    if command == "verify":
        result = asyncio.run(verify())
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
