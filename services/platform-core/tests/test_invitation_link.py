"""WO-100 — the invitation email gives a code and no way to use it.

The first real customer's owner could not get in: the delivered email was a
code in a sentence, with no link, followed by a full stop that a phone's
long-press copy grabbed — and the platform hashed the token exactly. Now:

  * every one-time email carries a tappable link to the right portal page
    with the code in the URL FRAGMENT (never a query string: a fragment is
    not sent to the server, so it reaches no access log), the code alone on
    its own line, and one sentence saying where it is used;
  * the link is a SECRET like the code: redacted in the stored body;
  * a code pasted with a trailing full stop, quotes, "code:" or a newline is
    accepted on every path that spends one — invitation, password reset,
    email change — because the server keeps only the token alphabet;
  * the portal's address is a RUNTIME setting, required and https in prod.
"""

import re

import pytest

from platform_core.core.security import normalise_token
from tests.conftest import invite
from tests.test_email_change import _capturing, _member
from tests.test_org_structure import _tenant_admin


def test_normalise_keeps_the_token_and_nothing_else():
    token = "abcXYZ_-09" * 4  # 40 chars, the shape of token_urlsafe(32)
    for pasted in [
        f"{token}.",
        f'"{token}"',
        f"code: {token}\n",
        f" {token} \r\n",
        f"{token}\u2019",
        f"https://app.lacteva.com/accept-invitation#code={token}",
    ]:
        assert normalise_token(pasted) == token, pasted
    assert normalise_token("") == ""
    assert normalise_token(None) == ""  # type: ignore[arg-type]


async def test_the_invitation_email_carries_a_link_and_the_code_alone(client):
    _org, admin = await _tenant_admin(client)
    capture, restore = _capturing()
    try:
        r = await client.post(
            "/v1/invitations",
            json={"email": "new@kilima.example", "role_name": "DRIVER"},
            headers=admin,
        )
        assert r.status_code == 201, r.text
    finally:
        restore()
    text = capture.to("new@kilima.example")[-1].body
    # A tappable link to the right page, the code in the FRAGMENT.
    link = re.search(r"(https?://\S+)/accept-invitation#code=([A-Za-z0-9_-]+)", text)
    assert link, text
    token = link.group(2)
    assert "?code=" not in text and "?token=" not in text
    # The code stands alone on its own line with nothing touching it.
    assert re.search(rf"^{re.escape(token)}$", text, re.M), text
    # And one sentence says where it is used.
    assert "/accept-invitation and paste this code" in text
    # The link works exactly as delivered.
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "linked-password-11", "full_name": "Linked"},
    )
    assert r.status_code == 201, r.text
    # The stored body redacts the link as it redacts the code (SEC-003 / F-04).
    r = await client.get("/v1/notifications?limit=50", headers=admin)
    assert token not in r.text


@pytest.mark.parametrize("wrap", ["{}.", '"{}"', "{}\n", "code: {}", " {} \r\n"])
async def test_a_copied_invitation_code_is_accepted_however_it_was_pasted(client, wrap):
    _org, admin = await _tenant_admin(client)
    _body, token = await invite(client, admin, email="paste@kilima.example", role_name="DRIVER")
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": wrap.format(token), "password": "paste-password-11", "full_name": "Pasted"},
    )
    assert r.status_code == 201, (wrap, r.text)


async def test_a_copied_reset_code_and_email_change_code_are_accepted(client):
    _org, admin = await _tenant_admin(client)
    _user_id, headers = await _member(client, admin)
    capture, restore = _capturing()
    try:
        await client.post(
            "/v1/auth/password-reset/request", json={"email": "raghvan@kilima.example"}
        )
        reset = re.search(
            r"/reset-password#code=([A-Za-z0-9_-]+)", capture.to("raghvan@kilima.example")[-1].body
        ).group(1)
        r = await client.post(
            "/v1/auth/password-reset/confirm",
            json={"token": f"{reset}.", "new_password": "pasted-password-11"},
        )
        assert r.status_code == 204, r.text
        headers = {
            "Authorization": "Bearer "
            + (
                await client.post(
                    "/v1/auth/token",
                    json={"email": "raghvan@kilima.example", "password": "pasted-password-11"},
                )
            ).json()["access_token"]
        }
        await client.post(
            "/v1/auth/me/email-change",
            json={"new_email": "raghavan@kilima.example"},
            headers=headers,
        )
        change = capture.code_for("raghavan@kilima.example")
        r = await client.post("/v1/auth/email-change/confirm", json={"token": f'"{change}"\n'})
        assert r.status_code == 204, r.text
    finally:
        restore()


def test_the_portal_address_is_required_and_https_in_prod():
    """The link in every invitation is only as good as this setting; prod
    refuses to start with a plain-http or missing portal address, the same
    way it refuses a development credential."""
    from platform_core.core.config import Settings

    with pytest.raises(ValueError, match="LACTEVA_PORTAL_PUBLIC_URL"):
        Settings(env="prod", portal_public_url="http://app.lacteva.com")
    with pytest.raises(ValueError, match="LACTEVA_PORTAL_PUBLIC_URL"):
        Settings(env="prod", portal_public_url="")
