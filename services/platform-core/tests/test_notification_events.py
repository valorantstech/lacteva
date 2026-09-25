"""WO-77 Part C — which notifications are on, read from the registry.

`GET /v1/notifications/events` is the dispatch registry and the messaging
posture joined per event, so an operator asking "does a household get a push
when its bill is issued?" reads the answer rather than working it out. Pinned:

  * every mapping in `MAPPINGS` is listed, none invented, none hidden;
  * the bill goes on push with an in-app companion; the supplier events stay
    on SMS exactly as they are — not rerouted to make a row look green;
  * `can_send` is the posture's answer for the event's channel: false while
    push is `disabled`, true once FCM is configured.
"""

from platform_core.consumers.notification_dispatch import MAPPINGS
from tests.test_fcm_push import credentials_file, fake_key_pem, fcm_settings  # noqa: F401
from tests.test_org_structure import _tenant_admin


async def test_the_registry_is_listed_per_event_with_its_channel(client):
    _org, admin = await _tenant_admin(client)
    r = await client.get("/v1/notifications/events", headers=admin)
    assert r.status_code == 200, r.text
    rows = {row["event"]: row for row in r.json()}
    assert set(rows) == set(MAPPINGS)

    bill = rows["sales.invoice-issued.v1"]
    assert bill["template_key"] == "invoice_issued"
    assert bill["channel"] == "push"
    assert bill["default_channel"] == "push"
    assert bill["selectable"] is True
    assert bill["inapp"] is True
    # Push is `disabled` on this test deployment: the row says so.
    assert bill["can_send"] is False

    paid = rows["sales.customer-payment-recorded.v1"]
    assert paid["channel"] == "push" and paid["inapp"] is False

    # The supplier journeys stay on SMS, un-rerouted, and honestly unsendable.
    for event in (
        "supplier.supplier-registered.v1",
        "settlement.finalized.v1",
        "payment.completed.v1",
    ):
        assert rows[event]["channel"] == "sms", event
        assert rows[event]["can_send"] is False, event


async def test_can_send_follows_the_configured_gateway(client, fcm_settings):  # noqa: F811
    from platform_core.modules.notification import providers

    providers.reset_providers()
    try:
        _org, admin = await _tenant_admin(client)
        rows = {
            row["event"]: row
            for row in (await client.get("/v1/notifications/events", headers=admin)).json()
        }
        assert rows["sales.invoice-issued.v1"]["can_send"] is True
        assert rows["sales.customer-payment-recorded.v1"]["can_send"] is True
        # SMS is untouched by a push gateway appearing: its answer is the
        # posture's own for the sms channel, whatever that is on this deployment.
        posture = (await client.get("/v1/notifications/messaging-posture", headers=admin)).json()
        sms = next(c for c in posture["channels"] if c["channel"] == "sms")
        assert rows["supplier.supplier-registered.v1"]["can_send"] is sms["can_send"]
    finally:
        providers.reset_providers()


async def test_the_list_needs_the_notification_read_permission(client):
    from tests.test_customer_scope import _customer, _customer_login

    org, admin = await _tenant_admin(client)
    household = await _customer(client, admin, "Curious Household")
    me = await _customer_login(client, admin, org["id"], household["id"], "c@household.example")
    assert (await client.get("/v1/notifications/events", headers=me)).status_code == 403
    assert (await client.get("/v1/notifications/events")).status_code == 401
