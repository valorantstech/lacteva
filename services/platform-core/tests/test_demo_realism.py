"""The demo dairy has to look like the dairy it is demonstrating to (WO-64).

The India demo carries excellent Indian names — Vasanthi Prabhu, Shivakumar
Angadi, Adiga Tiffin Room, Hotel Mayura Residency — and every one of those
farmers had a KENYAN phone number, because the supplier's number was built
from a `+2547` literal in a function neither market could influence. In a
sales demonstration to an Indian dairy that is the detail that breaks the
spell: everything else is right, so the one wrong thing is the thing the room
notices.

This is a data guard, not a code one. It asserts that each market's people
carry that market's country dialling code — the sort of thing nobody thinks to
check twice, which is exactly why it is worth a test.
"""

import importlib.util
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
SEED = REPO / "infra/demo/seed_demo.py"

#: E.164 country calling codes for the markets this seeder builds. Stated
#: here rather than derived: a dialling code is not the ISO country code and
#: no library in this tree maps one to the other.
DIALLING = {"KE": "+254", "IN": "+91"}


def _seed_module():
    """Import the seeder without running it.

    It is a script, not a package, and importing it must not need the app to
    be importable — so this loads it by path and lets a `SystemExit` from any
    module-level guard pass through harmlessly.
    """
    spec = importlib.util.spec_from_file_location("seed_demo", SEED)
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_demo"] = module
    try:
        spec.loader.exec_module(module)
    except SystemExit:  # pragma: no cover - the script's own CLI guard
        pass
    return module


@pytest.fixture(scope="module")
def seed():
    return _seed_module()


def test_every_market_dials_its_own_country(seed):
    for key, market in seed.MARKETS.items():
        code = DIALLING.get(market.country_code.upper())
        assert code, f"{key}: no dialling code known for {market.country_code}"
        number = f"{market.supplier_phone_prefix}{market.supplier_phone_base:08d}"
        assert number.startswith(code), (
            f"{key}'s farmers are on {number}, which is not a {market.country_code} "
            "number — the detail that breaks the spell in a demonstration"
        )


def test_customers_and_the_driver_dial_the_same_country(seed):
    for key, market in seed.MARKETS.items():
        code = DIALLING[market.country_code.upper()]
        for customer in market.customers:
            phone = customer[2]
            assert phone.startswith(code), f"{key}: {customer[0]} is on {phone}"
        _code, name, phone = market.driver
        assert phone.startswith(code), f"{key}: the driver {name} is on {phone}"


def test_a_farmer_and_a_household_are_never_the_same_number(seed):
    """Two people sharing a number is the kind of detail that gets noticed
    when somebody taps to call from the app."""
    for key, market in seed.MARKETS.items():
        farmers = {
            f"{market.supplier_phone_prefix}{market.supplier_phone_base + i:08d}"
            for i in range(len(market.supplier_names) + 200)
        }
        customers = {c[2] for c in market.customers}
        assert not (farmers & customers), (
            f"{key}: these numbers belong to both a farmer and a household: "
            f"{sorted(farmers & customers)}"
        )
        assert market.driver[2] not in farmers | customers


def test_the_kenyan_numbers_did_not_move(seed):
    """The change was meant to give INDIA Indian numbers, not to renumber a
    dairy that was already right. A demo whose data shifts under it is a demo
    whose screenshots and printed parchis stop matching."""
    kenya = seed.MARKETS["kenya"]
    assert kenya.supplier_phone_prefix == "+2547"
    assert kenya.supplier_phone_base == 20000000
    # The exact number the review saw, for the sixteenth farmer.
    assert f"{kenya.supplier_phone_prefix}{kenya.supplier_phone_base + 16:08d}" == "+254720000016"


def test_no_market_builds_a_phone_number_from_a_literal(seed):
    """The defect was a `+2547` written into `make_supplier`, where no market
    could reach it. Nothing outside the market table may name a country code."""
    source = SEED.read_text()
    body_start = source.index("async def make_supplier(")
    body = source[body_start : source.index("\nasync def ", body_start + 10)]
    # COMMENTS STRIPPED FIRST. The comment above the fix quotes the old
    # `+2547` to say what went wrong, and a guard that matched its own
    # explanation would fail on the sentence describing the defect it
    # prevents — the third time this repository has hit that (the nginx
    # location scan and the date-derivation guard were the other two).
    body = "\n".join(line.split("#", 1)[0] for line in body.splitlines() if line.strip() != "")
    for code in DIALLING.values():
        assert code not in body, (
            f"make_supplier writes {code} into a number again — the phone belongs "
            "to the market, which is the only thing that knows the country"
        )
