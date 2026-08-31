"""The farmer hears what happened at the counter (WO-52; LACTEVA-NOTIFY-003).

BR-0016: a business module never sends a message. The notification originates
from `collection.transaction-completed.v1` in the durable log, which is why a
farmer's copy can be reproduced and why nothing in milk_collection knows
notifications exist.
"""

import pytest

from platform_core.consumers.notification_dispatch import MAPPINGS
from platform_core.infrastructure.events import EventEnvelope

COLLECTION_COMPLETED = "collection.transaction-completed.v1"
pytestmark = pytest.mark.asyncio


def _envelope(**data):
    import uuid

    base = {
        "supplier_id": str(uuid.uuid4()),
        "slip_number": "SLP-2026-000007",
        "net_weight": 25.0,
        "quantity_unit": "kg",
        "fat": 4.2,
        "snf": 8.45,
        "unit_price": "45.0000",
        "gross_amount": "1125.00",
        "currency": "INR",
        "rejected": False,
    }
    base.update(data)
    return EventEnvelope(
        id=uuid.uuid4(),
        type=COLLECTION_COMPLETED,
        source="milk_collection",
        time="2026-08-31T07:30:00Z",
        aggregate_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        data=base,
    )


async def test_a_completed_collection_becomes_a_message_about_that_collection():
    built = MAPPINGS[COLLECTION_COMPLETED].build(_envelope())
    assert built is not None
    v = built["variables"]
    assert v["slip_number"] == "SLP-2026-000007"
    assert v["quantity"] == 25.0
    assert v["fat"] == 4.2
    assert v["snf"] == 8.45
    assert v["unit_price"] == "45.0000"
    assert v["gross_amount"] == "1125.00"
    # Which collection this is about, so "what was this farmer told?" is one
    # query rather than a walk through the outbox.
    assert built["source_type"] == "milk_transaction"


async def test_an_overridden_rate_is_named_in_the_farmer_s_copy():
    """BR-0029 / D-3. A rate a person changed is never silent — not on the
    parchi, and not in the message."""
    built = MAPPINGS[COLLECTION_COMPLETED].build(
        _envelope(unit_price="52.5000", base_unit_price="45.0000")
    )
    assert built["variables"]["base_unit_price"] == "45.0000"
    assert built["variables"]["unit_price"] == "52.5000"


async def test_an_ordinary_collection_carries_no_override_text():
    built = MAPPINGS[COLLECTION_COMPLETED].build(_envelope())
    # Optional in the template: empty means the "rate changed" sentence does
    # not render at all, rather than rendering with a blank in it.
    assert built["variables"]["base_unit_price"] == ""


async def test_a_rejected_collection_gets_no_amount_message():
    """A rejection has its own message; this one would tell a farmer what
    they earned for milk that was refused."""
    assert MAPPINGS[COLLECTION_COMPLETED].build(_envelope(rejected=True)) is None


async def test_a_collection_still_waiting_for_a_rate_says_nothing_yet():
    """Telling a farmer their milk is worth nothing while a rate card is being
    published is worse than telling them later."""
    assert MAPPINGS[COLLECTION_COMPLETED].build(_envelope(gross_amount=None)) is None
    assert MAPPINGS[COLLECTION_COMPLETED].build(_envelope(gross_amount="")) is None


async def test_the_template_is_registered_as_a_business_message():
    from platform_core.modules.notification.templates import BUSINESS_PURPOSE_KEYS, PURPOSES

    assert "collection_completed" in PURPOSES
    # The line a regulator draws between transactional and everything else.
    assert "collection_completed" in BUSINESS_PURPOSE_KEYS


async def test_sms_and_whatsapp_remain_unclaimed_for_this_message():
    """WO-52 keeps them in the Coming-Soon register. The mapping ships on the
    channel the platform can actually send on, and is `selectable` so a tenant
    can move it the day a provider is contracted — no code change, a row."""
    mapping = MAPPINGS[COLLECTION_COMPLETED]
    assert mapping.channel == "email"
    assert mapping.selectable is True
