"""The morning peak, over real HTTP, against real PostgreSQL (WO-41).

WHAT THIS MEASURES AND WHY IT IS NOT A BENCHMARK.

An Indian dairy's day has one shape: nearly every collection of the morning
round arrives inside about ninety minutes, at every centre at once, onto
handsets held by operators who are standing in front of a farmer with a can.
The question this answers is not "how fast is the platform" — it is "does the
platform stay usable during the only hour that matters, on the host we
actually bought". A number without that question attached is decoration.

So it captures collections the way the mobile client does: through the REAL
state machine, over REAL HTTP, at two centres CONCURRENTLY, and it reports
the latency of each step separately, because a p95 across a mixture of a
cheap POST and the pricing call is a number that describes nothing.

WHY IT DOES NOT RUN AGAINST THE LIVE HOST. Load against the deployed platform
would put synthetic collections in the demo dairy the owner shows people, and
a load test that has to be cleaned up afterwards eventually is not. The local
harness is the same code, the same PostgreSQL, and — since WO-43 — the same
non-superuser role with row-level security FORCED, which is the part that
actually costs something per query. Live is sampled read-only, for latency
that includes the network, and the two are reported side by side rather than
pretended to be one measurement.

Run it through the E2E harness, which stands up the whole world:

    LACTEVA_E2E_PROBE=infra/perf/morning-peak.py ./infra/e2e/run-e2e.sh probe

Options come from the environment so the harness's `probe` mode needs no
argument plumbing:

    LACTEVA_PEAK_COLLECTIONS   total collections to capture (default 40)
    LACTEVA_PEAK_HANDSETS      concurrent operators per centre (default 4)
    LACTEVA_PEAK_BUDGET_S      wall-clock cap in seconds (default 600)
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx

FIXTURE = Path(os.environ["LACTEVA_E2E_FIXTURE"])
TOTAL = int(os.environ.get("LACTEVA_PEAK_COLLECTIONS", "40"))
HANDSETS = int(os.environ.get("LACTEVA_PEAK_HANDSETS", "4"))
BUDGET_S = float(os.environ.get("LACTEVA_PEAK_BUDGET_S", "600"))

# The seven calls one collection really costs. They are listed here rather
# than discovered, so that a step appearing or disappearing from the flow is a
# visible change to this file and not a silent change to the measurement.
STEPS = ("create", "identify", "milk", "weight", "quality", "accept", "complete")

_lat: dict[str, list[float]] = defaultdict(list)
_errors: list[str] = []


class Timed:
    """One HTTP call, recorded under a label. Failures are data, not crashes.

    A load run that stops at the first refusal tells you when it broke and
    nothing about how it behaves while broken, which is the interesting half.
    """

    def __init__(self, client: httpx.AsyncClient, headers: dict[str, str]) -> None:
        self._client = client
        self._headers = headers

    async def post(self, label: str, url: str, body: dict | None = None) -> dict | None:
        started = time.perf_counter()
        try:
            r = await self._client.post(url, json=body, headers=self._headers, timeout=60.0)
        except Exception as exc:  # a timeout IS the result here, not a crash
            _lat[label].append((time.perf_counter() - started) * 1000)
            _errors.append(f"{label}: {type(exc).__name__}")
            return None
        _lat[label].append((time.perf_counter() - started) * 1000)
        if r.status_code not in (200, 201):
            _errors.append(f"{label}: HTTP {r.status_code} {r.text[:120]}")
            return None
        return r.json()

    async def get(self, label: str, url: str) -> dict | None:
        started = time.perf_counter()
        r = await self._client.get(url, headers=self._headers, timeout=60.0)
        _lat[label].append((time.perf_counter() - started) * 1000)
        if r.status_code != 200:
            _errors.append(f"{label}: HTTP {r.status_code}")
            return None
        return r.json()


async def _login(client: httpx.AsyncClient, email: str, password: str) -> dict[str, str]:
    r = await client.post(
        "/v1/auth/token", json={"email": email, "password": password}, timeout=60.0
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _whoami(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    r = await client.get("/v1/auth/me", headers=headers, timeout=60.0)
    r.raise_for_status()
    return r.json()["user"]["id"]


async def _make_ready(t: Timed, centre_id: str, operator_id: str) -> None:
    """A centre that can actually open a session.

    The E2E seed staffs only its first centre, because its journeys only
    collect at one. A morning peak is two centres at once by definition, so
    the second is staffed here — through the same endpoint, not around it.
    `collection-sessions` refuses at a centre with no operator, and that
    refusal is correct.
    """
    await t.post(
        "setup:operator",
        f"/v1/collection-centers/{centre_id}/operators",
        {"user_id": operator_id, "role_label": "operator"},
    )


async def _suppliers_for(t: Timed, admin_h: dict, centre_id: str, want: int, tag: str) -> list[str]:
    """Enough ACTIVE suppliers at this centre to keep the handsets busy.

    Created through the real onboarding path — draft, assign, activate —
    because a supplier who skipped it cannot deliver, which is the platform's
    rule and not an inconvenience to route around.
    """
    ids = []
    for n in range(want):
        sup = await t.post(
            "setup:supplier",
            "/v1/suppliers",
            {
                "full_name": f"Peak {tag} Farmer {n + 1} (LOAD)",
                "phone": f"+9198{abs(hash((tag, n))) % 100000000:08d}",
                "village": "Load Village",
            },
        )
        if sup is None:
            continue
        await t.post("setup:assign", f"/v1/suppliers/{sup['id']}/centers", {"center_id": centre_id})
        await t.post("setup:activate", f"/v1/suppliers/{sup['id']}/status", {"status": "active"})
        ids.append(sup["id"])
    return ids


async def _capture(t: Timed, session_id: str, supplier_id: str, index: int) -> bool:
    """One collection, every step of it, exactly as the handset walks it."""
    tx = await t.post("create", "/v1/milk-transactions", {"session_id": session_id})
    if tx is None:
        return False
    tid = tx["id"]
    body = {
        "identify": {"method": "manual", "supplier_id": supplier_id},
        "milk": {
            "milk_type": "cow",
            "container_type": "can",
            "container_identifier": f"CAN-{index:04d}",
            "temperature_c": 4.0,
        },
        "weight": {
            "source": "manual",
            "unit": "kg",
            "gross": 40.0 + (index % 9),
            "tare": 3.0,
        },
        "quality": {
            "source": "manual",
            "fat": round(3.4 + (index % 12) * 0.1, 1),
            "snf": round(8.0 + (index % 7) * 0.1, 2),
            "clr": round(26.0 + (index % 5) * 0.5, 2),
            "temperature_c": 4.0,
        },
    }
    for step, payload in body.items():
        if await t.post(step, f"/v1/milk-transactions/{tid}/{step}", payload) is None:
            return False
    for step in ("accept", "complete"):
        if await t.post(step, f"/v1/milk-transactions/{tid}/{step}", None) is None:
            return False
    return True


async def _handset(t: Timed, session_id: str, suppliers: list[str], queue: asyncio.Queue) -> int:
    """One operator, capturing until the round is done or the budget is spent."""
    done = 0
    while True:
        try:
            index = queue.get_nowait()
        except asyncio.QueueEmpty:
            return done
        if await _capture(t, session_id, suppliers[index % len(suppliers)], index):
            done += 1


def _pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(p / 100 * len(ordered) + 0.5) - 1))
    return ordered[k]


def _rss_mb() -> float:
    """Resident memory of the whole server process tree, in MB.

    Read from /proc rather than psutil: one fewer dependency, and the number
    that matters is the sum across the uvicorn workers, not any one of them.
    """
    total = 0
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cmdline = (proc / "cmdline").read_bytes()
            if b"uvicorn" not in cmdline and b"platform_core" not in cmdline:
                continue
            for line in (proc / "status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    total += int(line.split()[1])
        except (OSError, ValueError):
            continue
    return total / 1024


async def main() -> int:
    fx = json.loads(FIXTURE.read_text())
    base, password = fx["base_url"], fx["password"]
    centres = fx["centres"][:2]
    if len(centres) < 2:
        print("FATAL: the fixture has fewer than two centres", file=sys.stderr)
        return 1

    async with httpx.AsyncClient(base_url=base) as client:
        admin_h = await _login(client, fx["users"]["admin"]["email"], password)
        admin = Timed(client, admin_h)
        # The handsets are the OPERATOR's, not the administrator's: the
        # permission checks a collection really passes through are that
        # role's, and they are part of what a capture costs.
        operator_h = await _login(client, fx["users"]["operator"]["email"], password)
        operator_id = await _whoami(client, operator_h)

        per_centre = max(6, TOTAL // 2 // 2)
        print(f"── preparing {len(centres)} centres, {per_centre} suppliers each ──")
        sessions, rosters = [], []
        for centre in centres:
            await _make_ready(admin, centre["id"], operator_id)
            rosters.append(
                await _suppliers_for(admin, admin_h, centre["id"], per_centre, centre["code"])
            )
            s = await admin.post(
                "setup:session",
                "/v1/collection-sessions",
                {"center_id": centre["id"], "label": "morning peak (LOAD)"},
            )
            if s is None:
                print("FATAL: could not open a collection session", file=sys.stderr)
                for line in sorted(set(_errors)):
                    print(f"  {line}", file=sys.stderr)
                return 1
            sessions.append(s["id"])

        # Everything above is setup and must not colour the measurement.
        _lat.clear()
        _errors.clear()
        rss_before = _rss_mb()

        queues = []
        for half in range(2):
            q: asyncio.Queue = asyncio.Queue()
            for i in range(half, TOTAL, 2):
                q.put_nowait(i)
            queues.append(q)

        print(f"── {TOTAL} collections, {HANDSETS} handsets per centre, both centres at once ──")
        started = time.perf_counter()
        workers = [
            _handset(Timed(client, operator_h), sessions[half], rosters[half], queues[half])
            for half in range(2)
            for _ in range(HANDSETS)
        ]
        captured = sum(await asyncio.wait_for(asyncio.gather(*workers), timeout=BUDGET_S))
        elapsed = time.perf_counter() - started
        rss_after = _rss_mb()

        # One read of the day, as a supervisor would take it mid-round.
        await admin.get("read:daily", f"/v1/reports/collection/daily?center_id={centres[0]['id']}")

    print()
    print(
        f"  captured {captured}/{TOTAL} collections in {elapsed:.1f}s "
        f"({captured / elapsed * 60:.1f}/min)"
    )
    print(f"  server resident memory: {rss_before:.0f} MB → {rss_after:.0f} MB")
    print()
    print(f"  {'step':16} {'n':>5} {'p50 ms':>9} {'p95 ms':>9} {'max ms':>9}")
    for label in (*STEPS, "read:daily"):
        v = _lat.get(label, [])
        if not v:
            continue
        print(
            f"  {label:16} {len(v):>5} {statistics.median(v):>9.1f} "
            f"{_pct(v, 95):>9.1f} {max(v):>9.1f}"
        )
    whole = [sum(_lat[s][i] for s in STEPS if i < len(_lat[s])) for i in range(captured)]
    if whole:
        print(
            f"  {'ONE COLLECTION':16} {len(whole):>5} {statistics.median(whole):>9.1f} "
            f"{_pct(whole, 95):>9.1f} {max(whole):>9.1f}"
        )

    if _errors:
        print(f"\n  {len(_errors)} refusals:")
        for line in sorted(set(_errors))[:10]:
            print(f"    {line}")

    # The verdict, stated here rather than left to the reader: a collection is
    # a person standing at a counter, and the round has to clear.
    if captured < TOTAL:
        print(f"\nFAIL: only {captured} of {TOTAL} collections completed")
        return 1
    if elapsed > BUDGET_S:
        print(f"\nFAIL: the round took {elapsed:.0f}s, over the {BUDGET_S:.0f}s budget")
        return 1
    print(f"\nPASS: the round cleared in {elapsed:.0f}s, inside the {BUDGET_S:.0f}s budget")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
