"""A minimal SMTP sink for the E2E harness (P1-E2E-HARNESS-001).

The platform deliberately does NOT return an invitation's raw token from the
API (SEC-003 / F-04: whoever issued an invitation could otherwise accept it
themselves). The token reaches the invitee through the notification channel and
nowhere else — so a harness that needs to accept an invitation must read it the
way the invitee does: out of a delivered message.

This is a mail SERVER stand-in, not a Lacteva stand-in. The platform's own
`SmtpEmailProvider` speaks real SMTP to it, so the invitation path under test
is the production one end to end; only the mailbox is local. Messages are
written to a directory as plain files for the seeder to read.

Deliberately tiny and dependency-free: `aiosmtpd` is not vendored in this
repository, and adding a dependency to receive four test emails would be worse
than forty lines of asyncio.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


class _Session:
    """One SMTP conversation, only as much as the platform's client needs."""

    def __init__(self, outdir: Path) -> None:
        self.outdir = outdir
        self.data: list[str] = []

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        async def say(line: str) -> None:
            writer.write(f"{line}\r\n".encode())
            await writer.drain()

        await say("220 lacteva-e2e-mailsink ESMTP")
        in_data = False
        body: list[str] = []
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")

                if in_data:
                    if line == ".":
                        in_data = False
                        self._persist("\n".join(body))
                        body = []
                        await say("250 OK queued")
                    else:
                        body.append(line[1:] if line.startswith("..") else line)
                    continue

                verb = line.split(" ", 1)[0].upper()
                if verb in {"EHLO", "HELO"}:
                    await say("250-lacteva-e2e-mailsink")
                    await say("250 OK")
                elif verb in {"MAIL", "RCPT"}:
                    await say("250 OK")
                elif verb == "DATA":
                    in_data = True
                    await say("354 End data with <CR><LF>.<CR><LF>")
                elif verb == "RSET":
                    await say("250 OK")
                elif verb == "NOOP":
                    await say("250 OK")
                elif verb == "QUIT":
                    await say("221 Bye")
                    break
                else:
                    # STARTTLS/AUTH and anything else: refuse politely rather
                    # than pretend. The harness configures the platform for
                    # plain local delivery, so nothing legitimate lands here.
                    await say("502 Command not implemented")
        finally:
            writer.close()

    def _persist(self, message: str) -> None:
        self.outdir.mkdir(parents=True, exist_ok=True)
        n = len(list(self.outdir.glob("msg-*.txt")))
        (self.outdir / f"msg-{n:04d}.txt").write_text(message, encoding="utf-8")


async def serve(host: str, port: int, outdir: Path) -> None:
    async def on_connect(reader, writer):
        await _Session(outdir).handle(reader, writer)

    server = await asyncio.start_server(on_connect, host, port)
    print(f"mailsink listening on {host}:{port} → {outdir}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8025
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("mail")
    asyncio.run(serve("127.0.0.1", port, out))
