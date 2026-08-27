"""A reset works without knowing your organization's UUID
(LACTEVA-BACKEND-005).

WO-10 made the reset email carry a code. This is the other half of the same
door: nobody could get a code in the first place.

Both clients omit `tenant_id`, and they are right to — a locked-out person does
not know their organization's UUID, which is precisely the problem DEMO-010
solved for the login form ("the tenant is resolved from the credentials"). But
`request_password_reset` looked the user up with `get_by_email(email, None)`,
which matches `tenant_id IS NULL`. So for every real tenant user the lookup
found nothing, the service returned early, and the 202-always contract — which
exists so that asking reveals nothing — hid the fact that nothing had happened.

The flow was reachable only by someone who could supply a UUID they had no way
to obtain. It is now login's own bounded candidate lookup, and these tests hold
it to three things: it works without a tenant, one address with accounts in two
organizations gets a code for EACH (the inbox is the identity, and each message
says whose account it opens), and each code opens only its own account.
"""

import uuid

import pytest
from sqlalchemy import select

from platform_core.core import db
from tests.conftest import register_and_login


@pytest.fixture
def provider_guard():
    from platform_core.modules.notification import providers

    yield providers
    providers.reset_providers()


class _Capturing:
    """Keeps what was actually sent — the only place the raw code exists."""

    name = "capturing"

    def __init__(self):
        self.sent: list = []

    async def send(self, message):
        from platform_core.modules.notification.providers import ACCEPTED, DeliveryResult

        self.sent.append(message)
        return DeliveryResult(
            provider_message_id=f"capture:{message.notification_id}", status=ACCEPTED
        )


def _code_in(body: str) -> str:
    return body.split("complete your reset:", 1)[1].split(".", 1)[0].strip()


async def _reset_token_count() -> int:
    from platform_core.modules.auth.models import PasswordResetToken

    async with db.get_session_factory()() as session:
        return len(list((await session.scalars(select(PasswordResetToken))).all()))


async def test_a_tenant_user_resets_without_naming_their_organization(client, provider_guard):
    """The WO-10 regression scenario, which is what both clients actually send."""
    from tests.test_localization import _tenant_admin_for

    recorder = _Capturing()
    provider_guard.register_provider("email", recorder)
    email = "locked-out@kilima.example"
    org, _headers = await _tenant_admin_for(
        client, country="IN", slug="reset-resolve-a", email=email
    )

    # No tenant_id. This is the client-shaped request.
    r = await client.post("/v1/auth/password-reset/request", json={"email": email})
    assert r.status_code == 202, r.text

    delivered = [m for m in recorder.sent if m.recipient == email]
    assert len(delivered) == 1, "a real tenant user must get a code without a UUID"
    body = delivered[0].body
    # It says which account it opens.
    assert "reset-resolve-a" in body or "Dairy reset-resolve-a" in body, body

    code = _code_in(body)
    done = await client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": code, "new_password": "recovered-without-uuid-1"},
    )
    assert done.status_code == 204, done.text

    signed_in = await client.post(
        "/v1/auth/token",
        json={
            "email": email,
            "password": "recovered-without-uuid-1",
            "tenant_id": org["id"] if isinstance(org, dict) else org,
        },
    )
    assert signed_in.status_code == 200, signed_in.text


async def test_one_address_two_organizations_gets_a_code_for_each(client, provider_guard):
    """The inbox is the identity.

    Somebody who works for two dairies with one email address is entitled to
    recover both accounts. Sending one code and silently picking an
    organization would leave the other account unrecoverable and the reader
    unable to tell which one they had just changed — so each account gets its
    own code, and each message says whose it is.
    """
    from tests.test_localization import _tenant_admin_for

    recorder = _Capturing()
    provider_guard.register_provider("email", recorder)
    email = "works-for-both@example.com"
    org_a, _a = await _tenant_admin_for(client, country="IN", slug="reset-both-a", email=email)
    org_b, _b = await _tenant_admin_for(client, country="IN", slug="reset-both-b", email=email)
    a_id = org_a["id"] if isinstance(org_a, dict) else org_a
    b_id = org_b["id"] if isinstance(org_b, dict) else org_b
    assert a_id != b_id

    recorder.sent.clear()
    r = await client.post("/v1/auth/password-reset/request", json={"email": email})
    assert r.status_code == 202

    delivered = [m for m in recorder.sent if m.recipient == email]
    assert len(delivered) == 2, "two accounts, two codes"

    # Each message names a DIFFERENT organization, so the reader can tell them
    # apart. Two identical emails would be a puzzle, not a recovery.
    named = {m.body.split("your account in ", 1)[1].split(".", 1)[0] for m in delivered}
    assert len(named) == 2, f"both messages named the same organization: {named}"
    assert any("reset-both-a" in n for n in named)
    assert any("reset-both-b" in n for n in named)

    codes = {_code_in(m.body): m for m in delivered}
    assert len(codes) == 2, "each account gets its own code"

    # And a code opens ONLY its own account. Spending the first must leave the
    # second account's password exactly as it was.
    first_body = delivered[0].body
    first_code = _code_in(first_body)
    first_org = first_body.split("your account in ", 1)[1].split(".", 1)[0]
    assert (
        await client.post(
            "/v1/auth/password-reset/confirm",
            json={"token": first_code, "new_password": "only-this-account-1"},
        )
    ).status_code == 204

    changed_id = a_id if "reset-both-a" in first_org else b_id
    other_id = b_id if changed_id == a_id else a_id

    # The account the code named now takes the new password...
    assert (
        await client.post(
            "/v1/auth/token",
            json={"email": email, "password": "only-this-account-1", "tenant_id": changed_id},
        )
    ).status_code == 200

    # ...and the OTHER account does not: its password is untouched.
    assert (
        await client.post(
            "/v1/auth/token",
            json={"email": email, "password": "only-this-account-1", "tenant_id": other_id},
        )
    ).status_code == 401
    assert (
        await client.post(
            "/v1/auth/token",
            json={"email": email, "password": "admin-password-1", "tenant_id": other_id},
        )
    ).status_code == 200


async def test_an_unknown_address_still_says_nothing_and_sends_nothing(client, provider_guard):
    """Enumeration safety survives the wider lookup.

    A cross-organization search is exactly the change that could turn a silent
    202 into an oracle, so this is asserted rather than assumed: still 202,
    still nothing sent, still no token minted.
    """
    recorder = _Capturing()
    provider_guard.register_provider("email", recorder)
    before = await _reset_token_count()

    missing = f"nobody-{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post("/v1/auth/password-reset/request", json={"email": missing})
    assert r.status_code == 202
    assert [m for m in recorder.sent if m.recipient == missing] == []
    assert await _reset_token_count() == before


async def test_the_candidate_bound_is_respected(client, provider_guard):
    """A bound, not a business rule.

    An address with an unbounded number of accounts would otherwise make one
    unauthenticated request arbitrarily expensive — a hash, a token row and an
    email each. The reset borrows login's limit for the same reason login has
    it.
    """
    from platform_core.modules.identity.service import IdentityService

    recorder = _Capturing()
    provider_guard.register_provider("email", recorder)
    limit = IdentityService.LOGIN_CANDIDATE_LIMIT
    assert limit == 5, "the bound moved; this test is the reason to notice"

    email = "many-accounts@example.com"
    # One more account than the lookup will ever return.
    from platform_core.core import rate_limit
    from tests.test_localization import _tenant_admin_for

    for i in range(limit + 1):
        # Onboarding an organization signs in twice, and six of them exceed the
        # LOGIN limit — a real protection doing its job on a test that is not
        # about it. Cleared between organizations so the limiter under test
        # stays the reset one.
        rate_limit.set_rate_limiter(rate_limit.MemoryRateLimiter())
        await _tenant_admin_for(client, country="IN", slug=f"reset-bound-{i}", email=email)
    rate_limit.set_rate_limiter(rate_limit.MemoryRateLimiter())

    recorder.sent.clear()
    r = await client.post("/v1/auth/password-reset/request", json={"email": email})
    assert r.status_code == 202
    delivered = [m for m in recorder.sent if m.recipient == email]
    assert len(delivered) <= limit, f"the bound was ignored: {len(delivered)} messages"


async def test_an_explicit_tenant_still_takes_the_exact_match_path(client, provider_guard):
    """The old contract, unchanged for callers that name an organization."""
    recorder = _Capturing()
    provider_guard.register_provider("email", recorder)
    email = "explicit-tenant@example.com"
    await register_and_login(client, email)

    # A platform account has no tenant; naming a random one must find nobody
    # and must still say nothing about it.
    r = await client.post(
        "/v1/auth/password-reset/request",
        json={"email": email, "tenant_id": str(uuid.uuid4())},
    )
    assert r.status_code == 202
    assert [m for m in recorder.sent if m.recipient == email] == []
