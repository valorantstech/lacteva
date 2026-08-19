"""Synthetic dairy for the real client↔server E2E harness (P1-E2E-HARNESS-001).

**Everything here is SYNTHETIC TEST DATA.** No real dairy, farmer, outlet,
rate or price appears in this file, and none may be added: the fixtures use
`.e2e.example` addresses and obviously-fictional names so that nothing here can
ever be mistaken for a real dairy's records.

The dataset is built by calling the PLATFORM'S OWN HTTP API — the same
endpoints the portal and the phone call — so the seed itself is a first proof
that onboarding works over a real boundary. The single exception is the
platform-admin grant, which every deployment performs out of band; it uses the
platform's own `AuthzService` exactly as `tests/conftest.grant_platform_admin`
documents, never raw SQL.

Writes `fixture.json` for the client suites to read: ids and credentials of the
synthetic world, so a Dart or TypeScript test never has to guess them.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

BASE = os.environ.get("LACTEVA_E2E_API", "http://127.0.0.1:8099")
MAILDIR = Path(os.environ.get("LACTEVA_E2E_MAIL", "mail"))
PASSWORD = "e2e-synthetic-password-1"  # noqa: S105 — synthetic fixture, test-only


def _mail_count() -> int:
    return len(list(MAILDIR.glob("msg-*.txt"))) if MAILDIR.exists() else 0


async def _await_invitation_token(*, after: int, timeout: float = 20.0) -> str:
    """Poll the sink for the message the platform just sent, and read its token.

    The pattern is the platform's own: `tests/conftest.invite` reads the token
    out of the delivered body with the same expression, because that is the
    only place it exists.
    """
    import re

    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        files = sorted(MAILDIR.glob("msg-*.txt"))
        # Read every NEW message, newest first, and take the first one that
        # actually carries a token. Taking the newest and demanding a token be
        # in it was wrong: an invitation is not the only mail the platform
        # sends, and a "Welcome to Lacteva" arriving in the same moment made
        # the harness fail on a platform that had done nothing wrong.
        for path in reversed(files[after:]):
            body = path.read_text(encoding="utf-8", errors="replace")
            # Quoted-printable soft line breaks split long tokens across lines.
            body = body.replace("=\n", "").replace("=\r\n", "")
            match = re.search(r"registration:\s*(\S+?)\.(?:\s|$)", body) or re.search(
                r"registration:\s*(\S+)", body
            )
            if match:
                return match.group(1).rstrip(".")
        await asyncio.sleep(0.25)
    raise RuntimeError("the platform delivered no invitation message to the sink")


class Seeder:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.c = client

    async def post(self, path: str, *, json_body: Any = None, headers: dict | None = None) -> Any:
        # There was a retry here, for E2E-001: a row created moments earlier
        # reported "not found" by the very next request. The cause is now known
        # and fixed in the platform — it answered before it committed — so the
        # retry is GONE rather than left in place. A retry that outlives its
        # defect stops being a workaround and becomes a blindfold: it would
        # turn the regression it was written for into a silent pass.
        r = await self.c.post(path, json=json_body, headers=headers or {})
        if r.status_code >= 400:
            raise RuntimeError(f"POST {path} → {r.status_code}: {r.text}")
        return r.json() if r.content else None

    async def put(self, path: str, *, json_body: Any = None, headers: dict | None = None) -> Any:
        r = await self.c.put(path, json=json_body, headers=headers or {})
        if r.status_code >= 400:
            raise RuntimeError(f"PUT {path} → {r.status_code}: {r.text}")
        return r.json() if r.content else None

    async def get(self, path: str, *, headers: dict | None = None) -> Any:
        r = await self.c.get(path, headers=headers or {})
        if r.status_code >= 400:
            raise RuntimeError(f"GET {path} → {r.status_code}: {r.text}")
        return r.json()

    async def register(self, email: str, name: str) -> str:
        body = {"email": email, "password": PASSWORD, "full_name": name}
        return (await self.post("/v1/auth/register", json_body=body))["id"]

    async def token(self, email: str, tenant_id: str | None = None) -> dict[str, str]:
        body: dict[str, Any] = {"email": email, "password": PASSWORD}
        if tenant_id:
            body["tenant_id"] = tenant_id
        pair = await self.post("/v1/auth/token", json_body=body)
        return {"Authorization": f"Bearer {pair['access_token']}"}

    async def invite_accept(
        self, admin: dict, org_id: str, *, email: str, role_name: str, name: str
    ) -> dict[str, str]:
        """The real invitation path, exactly as an invitee experiences it.

        The API deliberately does NOT return the raw token (SEC-003 / F-04), so
        the harness reads it out of the message the platform actually
        delivered — real render, real SMTP, real secret handling.
        """
        before = _mail_count()
        await self.post(
            "/v1/invitations",
            json_body={"email": email, "role_name": role_name},
            headers={**admin, "X-Tenant-ID": org_id},
        )
        token = await _await_invitation_token(after=before)
        accepted = await self.post(
            "/v1/invitations/accept",
            json_body={"token": token, "password": PASSWORD, "full_name": name},
        )
        headers = await self.token(email, org_id)
        if isinstance(accepted, dict) and accepted.get("id"):
            headers["_user_id"] = str(accepted["id"])
        return headers


async def build() -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as http:
        s = Seeder(http)
        suffix = uuid.uuid4().hex[:8]

        # 1 — bootstrap identity. The platform-admin grant is the one out-of-band
        # step (see the module docstring).
        root_email = f"root+{suffix}@e2e.example"
        root_id = await s.register(root_email, "E2E Root")
        await _grant_platform_admin(root_id)
        root = await s.token(root_email)

        # 2 — the synthetic dairy, created through the real API.
        org = await s.post(
            "/v1/organizations",
            json_body={
                "name": "E2E Synthetic Dairy (TEST DATA)",
                "slug": f"e2e-dairy-{suffix}",
                "country_code": "in",
            },
            headers=root,
        )
        org_id = org["id"]

        admin_email = f"admin+{suffix}@e2e.example"
        admin = await s.invite_accept(
            root, org_id, email=admin_email, role_name="tenant-admin", name="E2E Admin"
        )

        # 3 — hierarchy: workspace → branch → two centres.
        ws = await s.post(
            "/v1/workspaces",
            json_body={"name": "E2E Region", "slug": f"e2e-region-{suffix}"},
            headers=admin,
        )
        branch = await s.post(
            "/v1/branches",
            json_body={
                "workspace_id": ws["id"],
                "name": "E2E Branch",
                "code": f"E2EB{suffix[:4].upper()}",
            },
            headers=admin,
        )
        centres = []
        for n in (1, 2):
            c = await s.post(
                "/v1/collection-centers",
                json_body={
                    "branch_id": branch["id"],
                    "name": f"E2E Centre {n}",
                    "code": f"E2EC{n}{suffix[:3].upper()}",
                },
                headers=admin,
            )
            centres.append(c)

        # 3b — a centre cannot receive milk until the platform says it is
        # ready: operating hours, a working scale (a BLOCKING readiness check)
        # and an active status. Walking that path here means the seed itself
        # proves the onboarding runbook (P0-PILOT-008 §D), not just the schema.
        for centre in centres:
            await s.put(
                f"/v1/collection-centers/{centre['id']}/operating-hours",
                json_body={
                    "windows": [
                        {"day_of_week": d, "opens": "05:00:00", "closes": "21:00:00"}
                        for d in range(7)
                    ]
                },
                headers=admin,
            )
            # The readiness rules name three device categories; the scale is
            # the BLOCKING one. Health is a REPORTED fact in this platform (no
            # hardware integration exists), so onboarding reports it — exactly
            # as the runbook's "declare the equipment" step describes.
            for category, label in (
                ("scale", "Scale"),
                ("milk_analyzer", "Analyzer"),
                ("printer", "Printer"),
            ):
                device = await s.post(
                    "/v1/devices",
                    json_body={
                        "category": category,
                        "name": f"E2E {label} {centre['code']}",
                        "serial_number": f"E2E-{category.upper()}-{centre['code']}",
                    },
                    headers=admin,
                )
                await s.post(
                    f"/v1/devices/{device['id']}/assign",
                    json_body={"center_id": centre["id"]},
                    headers=admin,
                )
                # Readiness counts ACTIVE devices only (`_device_check`), so
                # the equipment is commissioned, not merely registered.
                await s.post(
                    f"/v1/devices/{device['id']}/status",
                    json_body={"status": "active"},
                    headers=admin,
                )
                await s.post(
                    f"/v1/devices/{device['id']}/health",
                    json_body={"state": "ok", "note": "E2E synthetic health report"},
                    headers=admin,
                )

        # 4 — people. One operator scoped to centre 1 (the security boundary the
        # RLS/scope tests need), one org-wide manager, and one multi-role user.
        operator_email = f"operator+{suffix}@e2e.example"
        operator = await s.invite_accept(
            admin,
            org_id,
            email=operator_email,
            role_name="COLLECTION_OPERATOR",
            name="E2E Operator",
        )

        # The operator works at centre 1 — an assignment, and a readiness input.
        if operator.get("_user_id"):
            await s.post(
                f"/v1/collection-centers/{centres[0]['id']}/operators",
                json_body={"user_id": operator["_user_id"], "role_label": "operator"},
                headers=admin,
            )

        # Now the platform will let them be activated.
        for centre in centres:
            await s.post(
                f"/v1/collection-centers/{centre['id']}/status",
                json_body={"status": "active"},
                headers=admin,
            )

        manager_email = f"manager+{suffix}@e2e.example"
        manager = await s.invite_accept(
            admin, org_id, email=manager_email, role_name="tenant-viewer", name="E2E Manager"
        )

        # 5 — a second synthetic dairy: the cross-tenant boundary needs a real
        # foreign organization, not a fabricated id.
        other_email = f"other+{suffix}@e2e.example"
        other_org = await s.post(
            "/v1/organizations",
            json_body={
                "name": "E2E Other Dairy (TEST DATA)",
                "slug": f"e2e-other-{suffix}",
                "country_code": "in",
            },
            headers=root,
        )
        other_admin = await s.invite_accept(
            root, other_org["id"], email=other_email, role_name="tenant-admin", name="E2E Other"
        )
        other_ws = await s.post(
            "/v1/workspaces",
            json_body={"name": "Other Region", "slug": f"other-region-{suffix}"},
            headers=other_admin,
        )
        other_branch = await s.post(
            "/v1/branches",
            json_body={
                "workspace_id": other_ws["id"],
                "name": "Other Branch",
                "code": f"OTHB{suffix[:4].upper()}",
            },
            headers=other_admin,
        )
        other_centre = await s.post(
            "/v1/collection-centers",
            json_body={
                "branch_id": other_branch["id"],
                "name": "Other Centre",
                "code": f"OTHC{suffix[:3].upper()}",
            },
            headers=other_admin,
        )

        # 6 — suppliers (farmers are RECORDS, never logins).
        suppliers = []
        for n in (1, 2, 3):
            sup = await s.post(
                "/v1/suppliers",
                json_body={
                    "full_name": f"E2E Farmer {n} (TEST)",
                    "phone": f"+9199000000{n:02d}",
                    "village": "E2E Village",
                },
                headers=admin,
            )
            # A supplier is created as a DRAFT and may not deliver until they
            # are assigned to a centre and activated — the platform's rule, and
            # the onboarding pack's step. The seed walks it rather than
            # reaching around it.
            await s.post(
                f"/v1/suppliers/{sup['id']}/centers",
                json_body={"center_id": centres[0]["id"]},
                headers=admin,
            )
            sup = await s.post(
                f"/v1/suppliers/{sup['id']}/status",
                json_body={"status": "active"},
                headers=admin,
            )
            suppliers.append(sup)

        return {
            "_note": "SYNTHETIC E2E TEST DATA — not a real dairy",
            "base_url": BASE,
            "password": PASSWORD,
            "org": {"id": org_id, "slug": org["slug"], "name": org["name"]},
            "users": {
                "root": {"email": root_email},
                "admin": {"email": admin_email},
                "operator": {"email": operator_email},
                "manager": {"email": manager_email},
                "other_admin": {"email": other_email},
            },
            "centres": [{"id": c["id"], "code": c["code"], "name": c["name"]} for c in centres],
            "branch_id": branch["id"],
            "suppliers": [
                {"id": x["id"], "code": x["code"], "name": x.get("full_name")} for x in suppliers
            ],
            "other_org": {
                "id": other_org["id"],
                "centre_id": other_centre["id"],
                "admin_email": other_email,
            },
        }


async def _grant_platform_admin(user_id: str) -> None:
    """The deployment's own out-of-band bootstrap, via the platform's service."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/platform-core/src"))
    from platform_core.core import db  # noqa: PLC0415
    from platform_core.modules.authz.service import AuthzService  # noqa: PLC0415

    async with db.get_session_factory()() as session:
        await AuthzService(session).assign_role(
            user_id=uuid.UUID(user_id), role_name="platform-admin", tenant_id=None
        )
        await session.commit()


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixture.json")
    data = asyncio.run(build())
    out.write_text(json.dumps(data, indent=2))
    print(f"seeded synthetic dairy → {out}")
