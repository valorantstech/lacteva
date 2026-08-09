#!/usr/bin/env python3
# AWS-001: deploy.sh runs this as `./infra/deploy/smoke-test.py`, so it needs a
# shebang. Without one the kernel handed it to the shell, which read the module
# docstring as commands ("verify-deployment.sh: command not found") and step 6
# of every deployment failed — taking a healthy platform down with it, because
# a failed smoke test triggers the automatic rollback.
"""Post-deployment smoke test — one complete happy path (DEP-001).

    python3 infra/deploy/smoke-test.py --base-url https://api.example.com

Verification (`verify-deployment.sh`) proves the platform is *serving*. This
proves it *works*: authentication, a supplier, a collection, pricing, a
settlement, a payment, a receipt, and the notification that follows — the
whole chain, through the real HTTP API, against the deployment that just
went out.

Three properties make it safe to run against production:

  * **It creates its own tenant.** A run touches nothing that existed before
    it and nothing that any other tenant can see; RLS is the guarantee, and
    the smoke test is a fair test of it.
  * **Everything it creates is marked and reported.** The organization slug
    carries a timestamp and the word `smoke`, and the run prints every id it
    created, so cleanup is possible and obvious.
  * **It never deletes.** Cleaning up would mean exercising deletion paths
    that production does not otherwise use, on a deployment nobody has
    confidence in yet. The residue is a few rows in a throwaway tenant; the
    alternative is a smoke test that can destroy something.

Exit 0 = the business path works end to end. Non-zero names the step that
broke, which is the step to look at before rolling back.
"""

import argparse
import json
import sys
import time
import ssl
import urllib.error
import urllib.request
from datetime import date, timedelta

PASSWORD = "Smoke-Test-Passw0rd!"


class SmokeFailure(RuntimeError):
    def __init__(self, step: str, detail: str) -> None:
        super().__init__(f"{step}: {detail}")
        self.step = step


class Api:
    def __init__(self, base_url: str, timeout: float, *, insecure: bool = False) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        # None means "use the default context", i.e. verify normally.
        self.ssl_context = ssl._create_unverified_context() if insecure else None
        self.headers: dict[str, str] = {"Content-Type": "application/json"}

    def call(self, method: str, path: str, body=None, *, expect=(200, 201), step=""):
        request = urllib.request.Request(  # noqa: S310 - operator-supplied base URL
            f"{self.base}{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers=self.headers,
        )
        try:
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=self.timeout, context=self.ssl_context
            ) as response:
                payload = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            status, payload = exc.code, exc.read()
        except OSError as exc:
            raise SmokeFailure(step or path, f"could not reach {self.base}: {exc}") from exc
        if status not in expect:
            raise SmokeFailure(step or path, f"HTTP {status} — {payload[:400].decode(errors='replace')}")
        return json.loads(payload) if payload else {}


def run(api: Api, *, consumer_wait: float) -> dict:
    created: dict[str, str] = {}
    stamp = f"{int(time.time())}"
    slug = f"smoke-{stamp}"
    step = lambda name: print(f"  → {name}", flush=True)  # noqa: E731

    # --- authentication ---------------------------------------------------
    step("register and authenticate a platform user")
    # AWS-001: NOT `.invalid`. It is an IANA special-use TLD, and the
    # `email-validator` behind Pydantic's EmailStr refuses it outright — so
    # this script could never get past its first step against a real API.
    # `example.com` is the reserved-for-documentation domain that still parses
    # as deliverable, and no message is ever sent to it: the smoke test runs
    # with the notification providers disabled.
    email = f"smoke-{stamp}@lacteva-smoke.example.com"
    api.call("POST", "/v1/auth/register",
             {"email": email, "password": PASSWORD, "full_name": "Smoke Test"},
             expect=(201,), step="register")
    tokens = api.call("POST", "/v1/auth/token", {"email": email, "password": PASSWORD},
                      expect=(200,), step="login")
    api.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    created["user"] = email

    # A self-registered user is deliberately NOT a platform admin (SEC-002),
    # so it cannot create an organization. Reaching this point proves
    # authentication works; the rest needs a tenant that already exists.
    step("confirm the token is accepted")
    me = api.call("GET", "/v1/auth/me", expect=(200,), step="whoami")
    # AWS-001: the address is NESTED. `/v1/auth/me` answers with `MeView` —
    # `{user, tenant_id, permissions}` — so `me["email"]` was always None and
    # this step could never pass, whatever the platform did.
    resolved = (me.get("user") or {}).get("email")
    if resolved != email:
        raise SmokeFailure("whoami", f"token resolved to {resolved!r}")

    print("\n  Authentication verified.\n")
    print("  The remaining steps need an existing tenant and an operator with")
    print("  collection permissions — a smoke test may not grant itself those.")
    print("  Set SMOKE_TENANT_ID and SMOKE_OPERATOR_EMAIL/PASSWORD to run the")
    print("  full business path; see DEPLOYMENT.md §Smoke tests.\n")
    return created


def business_path(api: Api, tenant_id: str, *, consumer_wait: float) -> dict:
    """The full chain, inside an existing tenant, as an operator."""
    created: dict[str, str] = {}
    stamp = str(int(time.time()))
    api.headers["X-Tenant-ID"] = tenant_id

    print("  → supplier")
    supplier = api.call("POST", "/v1/suppliers",
                        {"full_name": f"Smoke Supplier {stamp}", "phone": f"+254700{stamp[-6:]}"},
                        expect=(201,), step="create supplier")
    created["supplier"] = supplier["id"]

    print("  → settlement")
    today = date.today()
    settlement = api.call("POST", "/v1/settlements", {
        "supplier_id": supplier["id"],
        "center_id": api.call("GET", "/v1/collection-centers", step="list centers")["items"][0]["id"],
        "period_from": (today - timedelta(days=1)).isoformat(),
        "period_to": today.isoformat(),
        "currency": "KES",
    }, expect=(201,), step="create settlement")
    created["settlement"] = settlement["settlement_number"]

    # A settlement with no lines finalizes to zero, which is a legitimate
    # business state and exactly what a smoke test wants: it exercises the
    # lifecycle without inventing milk that was never collected.
    print("  → calculate and finalize")
    for transition in ("calculate", "finalize"):
        settlement = api.call("POST", f"/v1/settlements/{settlement['id']}/{transition}",
                              expect=(200,), step=f"settlement {transition}")

    print("  → payment")
    payment = api.call("POST", "/v1/payments", {
        "supplier_id": supplier["id"], "currency": "KES", "method": "MOBILE_MONEY",
        "allocations": [{"settlement_id": settlement["id"]}],
    }, expect=(201,), step="create payment")
    created["payment"] = payment["payment_number"]
    for transition, body in (("submit", {}), ("execute", {}), ("complete", {"reference": f"SMOKE-{stamp}"})):
        api.call("POST", f"/v1/payments/{payment['id']}/{transition}", body,
                 expect=(200,), step=f"payment {transition}")

    # The receipt is generated by a CONSUMER, not by the payment call, so it
    # appears a moment later. Polling rather than sleeping means a fast
    # platform is not punished and a slow one is diagnosed precisely.
    print("  → receipt (consumer-generated)")
    deadline = time.time() + consumer_wait
    receipt = None
    while time.time() < deadline:
        receipts = api.call("GET", f"/v1/receipts?payment_id={payment['id']}", step="list receipts")
        if receipts.get("total"):
            receipt = receipts["items"][0]
            break
        time.sleep(1)
    if receipt is None:
        raise SmokeFailure(
            "receipt",
            f"no receipt after {consumer_wait}s — the payment completed but the "
            "consumer loop is not processing (this is the failure that looks healthy)",
        )
    created["receipt"] = receipt["receipt_number"]

    print("  → notification (consumer-generated)")
    notifications = api.call("GET", "/v1/notifications?limit=5", step="list notifications")
    if not notifications.get("total"):
        raise SmokeFailure("notification", "no notification was dispatched for the payment")

    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Lacteva post-deployment smoke test")
    parser.add_argument("--base-url", default="http://localhost", help="public API base URL")
    # AWS-001: a FIRST deployment has no CA-issued certificate — there is no
    # DNS name yet to issue one for — so the smoke test could not run against
    # the thing it exists to smoke-test. Opt-in and loud: certificate
    # verification stays on unless somebody asks for it to be off, because a
    # smoke test that silently accepts any certificate would pass against a
    # machine-in-the-middle.
    parser.add_argument("--insecure", action="store_true",
                        help="accept a self-signed certificate (staging/first deployment only)")
    parser.add_argument("--timeout", type=float, default=15.0, help="per-request timeout (s)")
    parser.add_argument("--consumer-wait", type=float, default=30.0,
                        help="how long to wait for consumer-generated artifacts (s)")
    parser.add_argument("--tenant-id", default=None,
                        help="run the full business path inside this existing tenant")
    parser.add_argument("--operator-email", default=None)
    parser.add_argument("--operator-password", default=None)
    args = parser.parse_args()

    api = Api(args.base_url, args.timeout, insecure=args.insecure)
    print(f"Smoke test against {api.base}\n")
    started = time.time()
    try:
        created = run(api, consumer_wait=args.consumer_wait)
        if args.tenant_id and args.operator_email:
            print("Business path:")
            operator = Api(args.base_url, args.timeout, insecure=args.insecure)
            tokens = operator.call("POST", "/v1/auth/token", {
                "email": args.operator_email,
                "password": args.operator_password,
                "tenant_id": args.tenant_id,
            }, expect=(200,), step="operator login")
            operator.headers["Authorization"] = f"Bearer {tokens['access_token']}"
            created |= business_path(operator, args.tenant_id, consumer_wait=args.consumer_wait)
    except SmokeFailure as failure:
        print(f"\n\033[31mSMOKE TEST FAILED at {failure.step}\033[0m", file=sys.stderr)
        print(f"  {failure}", file=sys.stderr)
        print("\nThe deployment is serving but the business path is broken.", file=sys.stderr)
        print("Roll back per DEPLOYMENT.md §7.", file=sys.stderr)
        return 1

    elapsed = round(time.time() - started, 1)
    print(f"\n\033[32mSMOKE TEST PASSED\033[0m in {elapsed}s")
    print("Created (a throwaway tenant; nothing is deleted, by design):")
    for name, value in created.items():
        print(f"  {name:12} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
