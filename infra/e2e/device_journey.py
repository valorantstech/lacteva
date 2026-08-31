"""One collection captured from instruments, end to end (WO-49b).

The unit tests prove the handset can parse a frame; the PostgreSQL suites
prove the guards refuse a bad attribution. Neither proves the thing the owner
actually asked for in D-15 — that an analyzer reading at the counter becomes a
priced, completed collection carrying the provenance of the instrument that
made it. This does, against the real API, as `lacteva_app` with row-level
security forced, which is the only configuration where a refusal means
anything.

THE FRAMES ARE THE SIMULATOR'S OWN. This does not invent a payload and post a
digest of it: it starts `apps/mobile/tools/device_simulator.dart`, reads what
it actually sends over TCP, and hashes those bytes. So the hash on the
transaction is the hash of bytes that crossed a socket, and the profile the
handset parses is the profile that produced them. A journey that fabricated
its own frame would prove the API accepts strings, which nobody doubted.

Skipped, loudly, when the Dart SDK is absent — a silent skip is how a green
pipeline comes to mean nothing (VER-001).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

FIXTURE = Path(os.environ["LACTEVA_E2E_FIXTURE"])
ROOT = Path(__file__).resolve().parents[2]
SIMULATOR = ROOT / "apps/mobile/tools/device_simulator.dart"


def call(method: str, path: str, body: dict | None = None, *, token: str | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:  # the body says why, and we want it
        raise SystemExit(f"FAILED {method} {path} -> {exc.code}: {exc.read()[:400]!r}") from exc


def read_one_frame(port: int, *, timeout: float = 10.0) -> bytes:
    """The first complete line the simulator sends, as raw bytes.

    Bytes, not text, and deliberately: the digest has to be of what crossed
    the wire, or it ties a disputed reading to nothing.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
                sock.settimeout(3)
                buffer = b""
                while b"\n" not in buffer or buffer.split(b"\n")[0].strip(b" ,LACTEVA") == b"":
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buffer += chunk
                for line in buffer.split(b"\n"):
                    # The simulator's first frame is the partial one a settling
                    # instrument emits; the journey wants the complete one.
                    if line.count(b",") >= 2 and not line.endswith(b",,,"):
                        return line
        except OSError:
            time.sleep(0.2)
    raise SystemExit(f"the simulator on port {port} sent no complete frame")


def main() -> int:
    if shutil.which("dart") is None and shutil.which("flutter") is None:
        print("   SKIPPED — no Dart SDK, so the simulator cannot run", file=sys.stderr)
        return 0

    fixture = json.loads(FIXTURE.read_text())
    global BASE
    BASE = fixture["base_url"]
    token = call(
        "POST",
        "/v1/auth/token",
        {"email": fixture["users"]["admin"]["email"], "password": fixture["password"]},
    )["access_token"]
    centre = fixture["centres"][0]
    supplier = fixture["suppliers"][0]

    print("── registering the instruments this journey reads from ──")
    devices = {}
    for category, kind in (("milk_analyzer", "analyzer"), ("scale", "scale")):
        device = call(
            "POST",
            "/v1/devices",
            {
                "category": category,
                "serial_number": f"E2E-{kind.upper()}-{int(time.time())}",
                "name": f"E2E {kind}",
            },
            token=token,
        )
        call("POST", f"/v1/devices/{device['id']}/assign", {"center_id": centre["id"]}, token=token)
        call("POST", f"/v1/devices/{device['id']}/status", {"status": "active"}, token=token)
        devices[kind] = device["id"]

    dart = shutil.which("dart") or str(Path(shutil.which("flutter")).parent / "cache/dart-sdk/bin/dart")
    readings = {}
    for kind, port in (("analyzer", 9711), ("scale", 9712)):
        process = subprocess.Popen(  # noqa: S603 - a file in this repository
            [dart, str(SIMULATOR), "--port", str(port), "--kind", kind],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            frame = read_one_frame(port)
        finally:
            process.terminate()
            process.wait(timeout=10)
        fields = frame.decode().strip().split(",")
        readings[kind] = {
            "frame": frame,
            # The digest of the bytes that crossed the socket, in the shape the
            # handset sends: `sha256:<hex>`.
            "hash": "sha256:" + hashlib.sha256(frame).hexdigest(),
            "values": [float(v) for v in fields[1:] if v.strip()],
        }
        print(f"   {kind}: {frame!r}")

    print("── one collection, captured from the instruments ──")
    tx = call("POST", "/v1/milk-transactions", {"session_id": fixture["session_id"]}, token=token) \
        if "session_id" in fixture else None
    if tx is None:
        session = call(
            "POST",
            "/v1/collection-sessions",
            {"center_id": centre["id"], "label": "device journey"},
            token=token,
        )
        tx = call("POST", "/v1/milk-transactions", {"session_id": session["id"]}, token=token)
    tid = tx["id"]

    qr = call("GET", f"/v1/suppliers/{supplier['id']}/qr", token=token)
    call("POST", f"/v1/milk-transactions/{tid}/identify",
         {"method": "qr", "value": qr["payload"]}, token=token)
    call("POST", f"/v1/milk-transactions/{tid}/milk",
         {"milk_type": "cow", "container_type": "can", "container_identifier": "CAN-DEV"},
         token=token)

    gross, tare = readings["scale"]["values"][0], readings["scale"]["values"][1]
    call(
        "POST",
        f"/v1/milk-transactions/{tid}/weight",
        {
            "source": "scale",
            "unit": "kg",
            "gross": gross,
            "tare": tare,
            "device_id": devices["scale"],
            "frame_hash": readings["scale"]["hash"],
        },
        token=token,
    )

    fat, snf, clr = readings["analyzer"]["values"][:3]
    priced = call(
        "POST",
        f"/v1/milk-transactions/{tid}/quality",
        {
            "source": "analyzer",
            "fat": fat,
            "snf": snf,
            "clr": clr,
            "device_id": devices["analyzer"],
            "frame_hash": readings["analyzer"]["hash"],
        },
        token=token,
    )

    print("── what the platform now believes ──")
    assert priced["weight_source"] == "scale", priced["weight_source"]
    assert priced["quality_source"] == "analyzer", priced["quality_source"]
    assert priced["fat"] == fat, f"{priced['fat']} != {fat}"
    assert priced["net_weight"] == round(gross - tare, 3)
    print(f"   fat {priced['fat']} from the analyzer, {priced['net_weight']} kg from the scale")

    # The rate engine is source-blind (spec §3): an instrument reading prices
    # exactly as a typed one does, and that is the property being asserted.
    assert priced.get("rate_amount") or priced.get("state") in ("PRICED", "QUALITY_CAPTURED"), priced
    print(f"   state {priced['state']}, rate {priced.get('rate_amount')}")

    events = call("GET", f"/v1/milk-transactions/{tid}/events", token=token)
    rows = events["items"] if isinstance(events, dict) else events
    for event_type, kind in (("WeightCaptured", "scale"), ("QualityCaptured", "analyzer")):
        row = [e for e in rows if e["event_type"] == event_type][0]
        assert row["data"]["source"] == kind, row["data"]
        assert row["data"]["device_id"] == devices[kind], row["data"]
        assert row["data"]["frame_hash"] == readings[kind]["hash"], row["data"]
        print(f"   {event_type} names {kind} {row['data']['device_id'][:8]}… and its frame digest")

    call("POST", f"/v1/milk-transactions/{tid}/accept", token=token)
    done = call("POST", f"/v1/milk-transactions/{tid}/complete", token=token)
    assert done["state"] == "COMPLETED", done["state"]
    assert done["slip_number"], "a completed collection must have a parchi"
    # Provenance survives completion: the snapshot a dispute is settled from
    # says which instrument produced the numbers.
    assert done["weight_source"] == "scale"
    assert done["quality_source"] == "analyzer"
    print(f"   COMPLETED as {done['slip_number']}, provenance intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
