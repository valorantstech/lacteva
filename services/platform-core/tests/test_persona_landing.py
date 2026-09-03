"""The personas the app routes on are the platform's own (WO-64).

`test/persona_landing_test.dart` asserts which screen each persona lands on,
and it has to state each persona's grants inline because Dart cannot read
`permissions.py`. Copied constants drift — that is not a hypothetical, it is
the defect class this repository has hit twice (a catalog whose callers were
never checked, and a client vocabulary that omitted an animal the platform
knew about).

So the copy is checked here, from the side that owns the truth: for the five
grants the mobile router consults, what the Dart file believes about each role
must be exactly what the registry says.
"""

import json
import pathlib
import re

import pytest

from platform_core.modules.authz.permissions import ALL_SYSTEM_ROLES, WILDCARD

REPO = pathlib.Path(__file__).resolve().parents[3]
DART = REPO / "apps/mobile/test/persona_landing_test.dart"

#: The only grants `experienceFor` reads. A role's other permissions are
#: irrelevant to WHERE IT LANDS, and asserting on them would make this fail
#: every time an unrelated capability is granted.
ROUTING_GRANTS = frozenset(
    {
        "collection.session.manage",
        "sales.delivery.record",
        "sales.delivery.read",
        "collection.transaction.read",
        "logistics.run.execute",
    }
)


def _dart_persona_grants() -> dict[str, set[str]]:
    """Parse `personaGrants` out of the Dart test.

    Deliberately a parse of the literal rather than a generated file: the Dart
    test has to be readable on its own — someone debugging a landing screen
    should see the grants in front of them — and generation would move the
    truth into a build step nobody runs on a laptop.
    """
    source = DART.read_text()
    block = re.search(r"const personaGrants = <String, Set<String>>\{(.*?)\n\};", source, re.S)
    assert block, "personaGrants is no longer a literal map — this parser needs updating"
    grants: dict[str, set[str]] = {}
    for role, body in re.findall(r"'([^']+)':\s*\{([^}]*)\}", block.group(1)):
        grants[role] = set(re.findall(r"'([^']+)'", body))
    return grants


def _platform_grants(role: str) -> set[str]:
    permissions = ALL_SYSTEM_ROLES[role]
    if WILDCARD in permissions:
        return set(ROUTING_GRANTS)
    return {p for p in ROUTING_GRANTS if p in permissions}


def test_the_app_knows_every_persona_the_platform_defines():
    """A role the registry gained and the router never heard of would land
    wherever the fall-through put it, and nobody would have decided that."""
    missing = sorted(set(ALL_SYSTEM_ROLES) - set(_dart_persona_grants()))
    assert missing == [], (
        "these roles exist in the platform and no mobile landing test covers them: "
        f"{missing} — add each to persona_landing_test.dart with the screen it opens"
    )


@pytest.mark.parametrize("role", sorted(_dart_persona_grants()))
def test_each_persona_carries_the_grants_the_platform_gives_it(role):
    assert role in ALL_SYSTEM_ROLES, f"{role} is not a role this platform defines"
    assert _dart_persona_grants()[role] == _platform_grants(role), (
        f"{role}'s routing grants have drifted from the registry: the app believes "
        f"{sorted(_dart_persona_grants()[role])}, the platform grants "
        f"{sorted(_platform_grants(role))}"
    )


def test_organisation_wide_roles_hold_both_halves_and_single_purpose_ones_do_not():
    """The rule the router encodes, asserted against the registry itself.

    `experienceFor` sends whoever holds BOTH `collection.session.manage` and
    `sales.delivery.record` to the manager home, on the grounds that a person
    trusted with procurement AND sales is running the dairy rather than doing
    one of its jobs. That is only a sound rule while the registry keeps those
    two grants apart for single-purpose roles — so this checks the premise,
    not the consequence.
    """
    both = {
        role
        for role in ALL_SYSTEM_ROLES
        if {"collection.session.manage", "sales.delivery.record"} <= _platform_grants(role)
    }
    assert both == {
        "tenant-admin",
        "ORGANIZATION_ADMIN",
        "ORGANIZATION_MANAGER",
        # The wildcard roles hold everything by definition, including both
        # halves. They also hold the driver grant, which is tested first, so
        # they never actually reach the manager-home branch — see the mobile
        # table, which records where they DO land rather than where this rule
        # would put them.
        "platform-admin",
        "PLATFORM_SUPER_ADMIN",
    }, (
        "a role now holds both halves of the business and would land on the manager "
        f"home: {sorted(both)}. If that is intended, say so here; if it is not, the "
        "role has been granted more than its job needs"
    )


def test_the_dart_table_states_a_screen_for_every_persona_it_grants():
    """Half a table is worse than none: a persona with grants and no expected
    screen is a row that asserts nothing."""
    source = DART.read_text()
    expected = set(re.findall(r"'([^']+)':\s*\(Experience\.", source.split("const expected")[1]))
    assert expected == set(_dart_persona_grants()), (
        f"grants and expectations disagree: {sorted(set(_dart_persona_grants()) ^ expected)}"
    )


def test_the_landing_screens_are_the_ones_the_review_found_correct():
    """The on-glass review endorsed four of the five landings and rejected one.

    Pinned so a later refactor cannot quietly "simplify" the personas that were
    already right — the operator's counter and the viewer's read-only round in
    particular, which the review called the permission model working
    beautifully.
    """
    source = DART.read_text().split("const expected")[1]
    landings = dict(re.findall(r"'([^']+)':\s*\(Experience\.(\w+)", source))
    assert landings["tenant-admin"] == "collection"
    assert landings["ORGANIZATION_MANAGER"] == "collection"
    assert landings["COLLECTION_OPERATOR"] == "collection"
    assert landings["SALES_OFFICER"] == "delivery"
    assert landings["tenant-viewer"] == "delivery"
    assert landings["DRIVER"] == "driver"


def test_the_json_of_this_is_not_committed_anywhere():
    """A generated copy would be a third source of truth. There are two: the
    registry, and a hand-written table a person can read."""
    assert not (REPO / "apps/mobile/test/personas.json").exists()
    json.dumps({})  # the module imports json only for this assertion's honesty
