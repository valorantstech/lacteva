/**
 * The portal's server boundary against the REAL platform
 * (P1-E2E-HARNESS-001).
 *
 * REAL: the portal's own route handlers — the ones that ship — talking over
 * real HTTP to a real FastAPI server backed by real PostgreSQL, with a real
 * synthetic dairy seeded through the platform's own API. The only thing
 * standing in is `next/headers`, because a cookie jar is the runtime's job and
 * not the boundary under test; every request that leaves this file is real.
 *
 * What it defends is the portal-specific half that no backend test can reach:
 * the browser never holds a bearer token — it holds an HttpOnly cookie, and
 * the proxy is what turns one into the other. If that seam breaks, every page
 * in the portal breaks at once, and until this suite existed nothing would
 * have noticed until someone clicked.
 *
 * Driven by `./infra/e2e/run-e2e.sh portal`. Without that harness there is no
 * server, and the suite says so rather than failing.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it, vi } from "vitest";

type Fixture = {
  base_url: string;
  password: string;
  org: { id: string; name: string };
  users: Record<string, { email: string }>;
  centres: { id: string; code: string; name: string }[];
  suppliers: { id: string; code: string }[];
  other_org: { id: string; centre_id: string; admin_email: string };
};

const fixturePath = process.env.LACTEVA_E2E_FIXTURE ?? "";
const harnessed = fixturePath.length > 0;
let fx: Fixture;

/** The cookie jar the Next runtime would own. */
const jar = new Map<string, string>();
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      jar.has(name) ? { name, value: jar.get(name) } : undefined,
    set: (name: string, value: string) => jar.set(name, value),
    delete: (name: string) => jar.delete(name),
  }),
}));

const { POST: login } = await import("@/app/api/auth/login/route");
const { GET: proxyGet } = await import("@/app/api/proxy/[...path]/route");
const { POST: acceptInvitation } = await import(
  "@/app/api/auth/invitation/route"
);
const { POST: resetRequest } = await import(
  "@/app/api/auth/password-reset/request/route"
);
const { POST: resetConfirm } = await import(
  "@/app/api/auth/password-reset/confirm/route"
);

const params = (path: string[]) => ({ params: Promise.resolve({ path }) });

async function signIn(email: string, tenantId?: string) {
  jar.clear();
  const res = await login(
    new Request("http://portal.test/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        password: fx.password,
        ...(tenantId ? { tenant_id: tenantId } : {}),
      }),
    }),
  );
  return res;
}

beforeAll(() => {
  if (!harnessed) return;
  fx = JSON.parse(readFileSync(fixturePath, "utf8")) as Fixture;
  // The portal's server code reads the platform's address from the same
  // variable the deployment sets.
  process.env.LACTEVA_API_URL = process.env.LACTEVA_E2E_API ?? fx.base_url;
});

/**
 * The money path, over the real boundary (LACTEVA-QA-001).
 *
 * Every figure below is the PLATFORM's own decimal string, compared as a
 * string. Nothing here multiplies, sums or rounds: a test that recomputes the
 * money is a second pricing engine, and the second engine is always the one
 * that is wrong. `Decimal` arithmetic in the platform and `Number` arithmetic
 * in a test cannot be made to agree by trying harder — so the test never
 * tries. It reads what the platform stored and demands the same characters
 * back from every later read.
 *
 * These journeys existed only as in-process proofs (R-6). Money is the one
 * place "works in-process" is not enough for a customer.
 */
const post = async (path: string[], body?: unknown) => {
  const { POST: proxyPost } = await import("@/app/api/proxy/[...path]/route");
  return proxyPost(
    new Request(`http://portal.test/api/proxy/${path.join("/")}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }),
    params(path),
  );
};

const get = async (path: string[], query = "") =>
  proxyGet(
    new Request(`http://portal.test/api/proxy/${path.join("/")}${query}`),
    params(path),
  );

/** Body of a response we expect to have succeeded, with the status in the message. */
async function ok<T>(res: Response, what: string, expected = [200, 201]): Promise<T> {
  const text = await res.text();
  expect(expected, `${what}: ${res.status} ${text.slice(0, 300)}`).toContain(res.status);
  return (text ? JSON.parse(text) : {}) as T;
}

/**
 * Poll until the platform has something to show.
 *
 * Receipts are written by a CONSUMER, not by the request that triggers them —
 * the relay delivers the event and the consumer renders the document. In
 * process that is a `run_once()` call; against a real server it is simply
 * asynchronous, so a test that reads immediately is testing its own timing.
 */
async function eventually<T>(
  read: () => Promise<T>,
  ready: (value: T) => boolean,
  what: string,
  timeoutMs = 15_000,
): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  let last: T = await read();
  while (Date.now() < deadline) {
    if (ready(last)) return last;
    await new Promise((r) => setTimeout(r, 400));
    last = await read();
  }
  expect.fail(`${what} never arrived within ${timeoutMs}ms`);
}

/** A published rate card covering `centre` for RAW-COW-MILK at `rate`. */
async function publishRateCard(centre: string, code: string, rate: string, from: string) {
  const card = await ok<{ id: string }>(
    await post(["v1", "rate-cards"], {
      name: `E2E ${code}`,
      code,
      currency: "INR",
      effective_from: from,
    }),
    "create rate card",
  );
  await ok(await post(["v1", "rate-cards", card.id, "centers"], { center_id: centre }), "scope centre");
  await ok(
    await post(["v1", "rate-cards", card.id, "products"], { product_code: "RAW-COW-MILK" }),
    "scope product",
  );
  const matrix = await ok<{ id: string }>(
    await post(["v1", "pricing-matrices"], {
      rate_card_id: card.id,
      name: `${code} FAT`,
      product_code: "RAW-COW-MILK",
      dimension_code: "FAT",
    }),
    "create matrix",
  );
  await ok(
    await post(["v1", "pricing-matrices", matrix.id, "rows"], {
      from_value: 3.0,
      to_value: 6.0,
      unit_price: rate,
    }),
    "add band",
  );
  // Publishing is a three-step authority, not a flag: submit, approve, publish.
  for (const step of ["submit", "approve", "publish"]) {
    await ok(await post(["v1", "rate-cards", card.id, step]), `${step} card`, [200, 201]);
  }
  return card.id;
}

/** Drive one collection to COMPLETED through the portal's own proxy. */
async function collect(sessionId: string, supplierId: string, fat = "4.2") {
  // `manual` identifies by id. `code` expects the supplier's CODE and `qr` a
  // minted payload; the id belongs to the manual method, which is the one a
  // back-office screen uses.
  const tx = await ok<{ id: string }>(
    await post(["v1", "milk-transactions"], { session_id: sessionId }),
    "create transaction",
  );
  await ok(
    await post(["v1", "milk-transactions", tx.id, "identify"], {
      method: "manual",
      supplier_id: supplierId,
    }),
    "identify",
  );
  await ok(
    await post(["v1", "milk-transactions", tx.id, "milk"], {
      milk_type: "cow",
      container_type: "can",
      container_identifier: "CAN-E2E",
    }),
    "milk",
  );
  await ok(
    await post(["v1", "milk-transactions", tx.id, "weight"], {
      source: "manual",
      gross: 32.5,
      tare: 2.5,
    }),
    "weight",
  );
  const priced = await ok<Record<string, unknown>>(
    await post(["v1", "milk-transactions", tx.id, "quality"], {
      source: "manual",
      fat: Number(fat),
      snf: 8.5,
      clr: 28.0,
    }),
    "quality",
  );
  await ok(await post(["v1", "milk-transactions", tx.id, "accept"]), "accept");
  const done = await ok<Record<string, unknown>>(
    await post(["v1", "milk-transactions", tx.id, "complete"]),
    "complete",
  );
  return { id: tx.id, priced, done };
}

describe("portal → platform, over the real boundary", () => {
  it("signs a real operator in and keeps the token off the page", async () => {
    if (!harnessed) return;
    const res = await signIn(fx.users.admin.email, fx.org.id);
    // 204: the session is established and there is deliberately nothing to
    // return — the portal's real contract, confirmed at the real boundary.
    expect(res.status).toBe(204);

    // The token lives in the cookie jar, never in the response body — the
    // whole reason the proxy exists.
    const body = await res.text();
    expect(body).not.toMatch(/access_token|eyJ/);
    expect(jar.size).toBeGreaterThan(0);
  });

  it("refuses a wrong password, and sets no session", async () => {
    if (!harnessed) return;
    jar.clear();
    const res = await login(
      new Request("http://portal.test/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: fx.users.admin.email,
          password: "not-the-password",
        }),
      }),
    );
    expect(res.status).toBeGreaterThanOrEqual(400);
    expect(jar.size).toBe(0);
  });

  it("proxies an authenticated read to the real platform", async () => {
    if (!harnessed) return;
    await signIn(fx.users.admin.email, fx.org.id);

    const res = await proxyGet(
      new Request("http://portal.test/api/proxy/v1/collection-centers?limit=50"),
      params(["v1", "collection-centers"]),
    );
    expect(res.status).toBe(200);
    const page = (await res.json()) as { items: { id: string; code: string }[] };
    // The synthetic dairy's own centres, as the platform returned them.
    expect(page.items.map((c) => c.code)).toContain(fx.centres[0].code);
  });

  it("refuses to proxy without a session", async () => {
    if (!harnessed) return;
    jar.clear();
    const res = await proxyGet(
      new Request("http://portal.test/api/proxy/v1/collection-centers"),
      params(["v1", "collection-centers"]),
    );
    expect(res.status).toBeGreaterThanOrEqual(400);
    expect(res.status).not.toBe(200);
  });

  it("cannot reach another tenant's centre through the proxy", async () => {
    if (!harnessed) return;
    await signIn(fx.users.admin.email, fx.org.id);

    const foreign = fx.other_org.centre_id;
    const res = await proxyGet(
      new Request(`http://portal.test/api/proxy/v1/collection-centers/${foreign}`),
      params(["v1", "collection-centers", foreign]),
    );
    // RLS decides this in the database; the portal simply carries the answer.
    expect(res.status).not.toBe(200);
    expect([403, 404]).toContain(res.status);
  });

  it("carries the platform's own refusal rather than inventing one", async () => {
    if (!harnessed) return;
    await signIn(fx.users.manager.email, fx.org.id);

    // The manager here is a viewer: reading is allowed, recording is not.
    const read = await proxyGet(
      new Request("http://portal.test/api/proxy/v1/suppliers?limit=5"),
      params(["v1", "suppliers"]),
    );
    expect(read.status).toBe(200);

    const { POST: proxyPost } = await import("@/app/api/proxy/[...path]/route");
    const write = await proxyPost(
      new Request("http://portal.test/api/proxy/v1/suppliers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: "Should Not Exist", phone: "+919900000999" }),
      }),
      params(["v1", "suppliers"]),
    );
    expect(write.status).toBe(403);
    // The body is the platform's RFC-9457 problem document, passed through.
    const problem = await write.json();
    expect(problem).toHaveProperty("title");
  });

  // E2E-001 (P1-E2E-404-001). The defect this harness found: a row created
  // moments earlier read back 404, because the platform answered BEFORE it
  // committed. It could not be caught in-process — an ASGI test client waits
  // for the application to finish and shows the ordering as correct however
  // wrong it is — so the regression test has to live out here, against a real
  // server and a real PostgreSQL, doing what a real client does: acting on its
  // own answer immediately.
  //
  // Repeated, because the window was sub-millisecond: one pass proved nothing.
  // Before the fix this failed within the first handful of iterations.
  it("reads back every row it just created, 25 times running", async () => {
    if (!harnessed) return;
    await signIn(fx.users.admin.email, fx.org.id);
    const { POST: proxyPost } = await import("@/app/api/proxy/[...path]/route");

    const stamp = Date.now().toString().slice(-6);
    const missing: string[] = [];
    const created: string[] = [];

    for (let i = 0; i < 25; i++) {
      const create = await proxyPost(
        new Request("http://portal.test/api/proxy/v1/suppliers", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            full_name: `E2E Read-After-Write ${stamp}-${i} (TEST DATA)`,
            phone: `+9198${stamp}${String(i).padStart(2, "0")}`,
          }),
        }),
        params(["v1", "suppliers"]),
      );
      expect(create.status).toBe(201);
      const { id } = (await create.json()) as { id: string };
      created.push(id);

      // The very next request, with nothing in between.
      const readBack = await proxyGet(
        new Request(`http://portal.test/api/proxy/v1/suppliers/${id}`),
        params(["v1", "suppliers", id]),
      );
      if (readBack.status !== 200) missing.push(`${id} → ${readBack.status}`);
    }

    expect(missing).toEqual([]);
    expect(created).toHaveLength(25);
  });

  // LACTEVA-ADMIN-002. Onboarding a dairy's staff needed raw API calls: the
  // invitation endpoints were implemented and SMTP-proven with no client
  // caller at all. This is the whole journey through the PORTAL's own server
  // code — invite as an administrator, read the code the platform actually
  // emailed, accept through the pre-auth route, then sign in as the person who
  // did not exist when the test started.
  //
  // It has to live out here because the token exists in exactly one place: the
  // delivered message. The API will not return it (SEC-003 / F-04 — whoever
  // issued an invitation could otherwise accept it themselves under the
  // invitee's address), so an in-process test could only assert against a
  // token it had invented.
  it("invites a colleague, who accepts and signs in", async () => {
    if (!harnessed) return;
    const maildir = process.env.LACTEVA_E2E_MAIL;
    if (!maildir) return; // the sink is the harness's, not this test's to build

    const count = () =>
      readdirSync(maildir).filter((f) => f.startsWith("msg-")).length;
    const before = count();

    await signIn(fx.users.admin.email, fx.org.id);
    const { POST: proxyPost } = await import("@/app/api/proxy/[...path]/route");

    const invitee = `invited+${Date.now().toString().slice(-8)}@e2e.example`;
    const invited = await proxyPost(
      new Request("http://portal.test/api/proxy/v1/invitations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: invitee, role_name: "tenant-viewer" }),
      }),
      params(["v1", "invitations"]),
    );
    expect(invited.status).toBe(201);
    const meta = (await invited.json()) as Record<string, unknown>;
    // The platform hands back metadata and no secret; the portal must have
    // nothing to leak.
    expect(meta.email).toBe(invitee);
    expect(meta.status).toBe("pending");
    expect(JSON.stringify(meta)).not.toMatch(/token/i);

    // Read the code out of the message that was really delivered — the same
    // expression `seed.py` uses, because that is the only place it exists.
    const token = await (async () => {
      const deadline = Date.now() + 20_000;
      while (Date.now() < deadline) {
        const files = readdirSync(maildir)
          .filter((f) => f.startsWith("msg-"))
          .sort()
          .slice(before)
          .reverse();
        for (const file of files) {
          const body = readFileSync(join(maildir, file), "utf8")
            .replace(/=\r?\n/g, "");
          const m = body.match(/registration:\s*(\S+?)\.(?:\s|$)/) ??
            body.match(/registration:\s*(\S+)/);
          if (m) return m[1].replace(/\.$/, "");
        }
        await new Promise((r) => setTimeout(r, 250));
      }
      throw new Error("the platform delivered no invitation message");
    })();

    // Accept through the PORTAL's pre-auth route — the one that exists because
    // /api/proxy would refuse a request carrying no session.
    jar.clear();
    const accepted = await acceptInvitation(
      new Request("http://portal.test/api/auth/invitation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          full_name: "E2E Invited Colleague",
          password: fx.password,
        }),
      }),
    );
    expect(accepted.status).toBe(201);
    // Joining is not signing in: no session was minted by accepting.
    expect(jar.size).toBe(0);

    // And now the person can sign in, which is the only proof that matters.
    const signedIn = await signIn(invitee, fx.org.id);
    expect(signedIn.status).toBe(204);
    expect(jar.size).toBeGreaterThan(0);
  });

  it("keeps those new rows inside their own tenant", async () => {
    if (!harnessed) return;
    // The fix moved where the commit happens; it must not have moved who can
    // see the row. A supplier created by this dairy stays invisible to the
    // other one — decided by RLS in the database, not by the portal.
    await signIn(fx.users.admin.email, fx.org.id);
    const { POST: proxyPost } = await import("@/app/api/proxy/[...path]/route");
    const create = await proxyPost(
      new Request("http://portal.test/api/proxy/v1/suppliers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: `E2E Isolation ${Date.now()} (TEST DATA)`,
          phone: `+9197${Date.now().toString().slice(-8)}`,
        }),
      }),
      params(["v1", "suppliers"]),
    );
    expect(create.status).toBe(201);
    const { id } = (await create.json()) as { id: string };

    await signIn(fx.other_org.admin_email, fx.other_org.id);
    const foreign = await proxyGet(
      new Request(`http://portal.test/api/proxy/v1/suppliers/${id}`),
      params(["v1", "suppliers", id]),
    );
    expect(foreign.status).not.toBe(200);
    expect([403, 404]).toContain(foreign.status);
  });
});

describe("the money path, end to end over real HTTP", () => {
  // (a) Procurement: milk in, money out.
  it("prices a collection, settles it, pays it, and receipts it — same figures throughout", async () => {
    if (!harnessed) return;
    await signIn(fx.users.admin.email, fx.org.id);

    const centre = fx.centres[0].id;
    const supplier = fx.suppliers[0].id;
    await publishRateCard(centre, `E2EPROC${Date.now().toString().slice(-6)}`, "46.5000", "2026-01-01");

    const session = await ok<{ id: string }>(
      await post(["v1", "collection-sessions"], { center_id: centre, label: "e2e-money" }),
      "open session",
    );
    const { id: txId, done } = await collect(session.id, supplier);

    // The platform priced it. These strings are the platform's, and they are
    // the ONLY source for every assertion that follows.
    const unitPrice = String(done.unit_price);
    const gross = String(done.gross_amount);
    expect(done.pricing_status).toBe("priced");
    expect(unitPrice).toBe("46.5000");
    // 32.5 - 2.5 = 30kg at 46.50. Asserted as the platform's own string; the
    // test does not do this multiplication, it reads the answer.
    expect(gross).toBe("1395.00");
    expect(done.state).toBe("COMPLETED");

    const settlement = await ok<{ id: string }>(
      await post(["v1", "settlements"], {
        supplier_id: supplier,
        center_id: centre,
        currency: "INR",
        period_from: "2026-01-01",
        period_to: "2026-12-31",
      }),
      "create settlement",
    );
    const swept = await ok<{ added: number; skipped: number }>(
      await post(["v1", "settlements", settlement.id, "collect"]),
      "collect period",
    );
    expect(swept.added).toBe(1);

    await ok(await post(["v1", "settlements", settlement.id, "calculate"]), "calculate totals");
    const totals = await ok<Record<string, unknown>>(
      await get(["v1", "settlements", settlement.id]),
      "read settlement",
    );
    const settlementBody = (totals.settlement ?? totals) as Record<string, unknown>;
    // The settlement's gross is the collection's gross, character for
    // character. A settlement that "nearly" agrees with its own lines is the
    // failure this journey exists to catch.
    expect(String(settlementBody.gross_amount)).toBe(gross);
    const net = String(settlementBody.net_amount);
    // BR-0011, surfaced by the platform for exactly this question: the header
    // totals and the lines underneath them are the same money.
    expect(totals.totals_match_lines).toBe(true);
    expect(settlementBody.line_count).toBe(1);

    const finalized = await ok<Record<string, unknown>>(
      await post(["v1", "settlements", settlement.id, "finalize"]),
      "finalize",
    );
    expect(finalized.status).toBe("finalized");
    // Finalizing must not move the money.
    expect(String(finalized.net_amount)).toBe(net);

    const payment = await ok<{ id: string; amount: string; payment_number: string }>(
      await post(["v1", "payments"], {
        supplier_id: supplier,
        currency: "INR",
        method: "BANK_TRANSFER",
        allocations: [{ settlement_id: settlement.id }],
      }),
      "create payment",
    );
    // Paying "the outstanding" must pay exactly the net, not a rounding of it.
    expect(payment.amount).toBe(net);
    expect(payment.payment_number).toMatch(/^PAY-/);

    // A payment is not money until it has actually moved. The platform makes
    // that a lifecycle rather than a flag — draft, pending, processing,
    // completed — and only a COMPLETED payment earns a receipt. Every step is
    // asserted to leave the amount exactly where it was.
    const lifecycle: [string, string, unknown][] = [
      ["submit", "pending", {}],
      ["execute", "processing", {}],
      // The bank's own reference for the transfer — the thing an operator
      // reconciles against a statement.
      ["complete", "completed", { reference: `E2E-BNK-${Date.now().toString().slice(-6)}` }],
    ];
    for (const [step, expected, body] of lifecycle) {
      const moved = await ok<Record<string, unknown>>(
        await post(["v1", "payments", payment.id, step], body),
        `payment ${step}`,
      );
      expect(moved.status).toBe(expected);
      expect(String(moved.amount)).toBe(net);
    }

    const receipts = await eventually(
      async () =>
        await ok<{ items: Record<string, unknown>[] }>(
          await get(["v1", "receipts"], `?payment_id=${payment.id}`),
          "read receipts",
        ),
      (r) => r.items.length > 0,
      "the payment receipt",
    );
    const receipt = receipts.items[0];
    // The receipt is the farmer's evidence, so it must carry BOTH figures and
    // both must still be the settlement's.
    expect(String(receipt.net_amount)).toBe(net);
    expect(String(receipt.gross_amount)).toBe(gross);
    expect(String(receipt.receipt_number)).toMatch(/^RCP-/);
    expect(String(receipt.payment_number)).toBe(payment.payment_number);

    // And the collection still says what it said at the start: money that has
    // travelled through four documents has not drifted in any of them.
    const reread = await ok<Record<string, unknown>>(
      await get(["v1", "milk-transactions", txId]),
      "re-read the collection",
    );
    expect(String(reread.gross_amount)).toBe(gross);
    expect(String(reread.unit_price)).toBe(unitPrice);
  });

  // (b) Sales: milk out, money in.
  it("invoices a customer's deliveries, takes payment, and receipts it", async () => {
    if (!harnessed) return;
    await signIn(fx.users.admin.email, fx.org.id);
    const stamp = Date.now().toString().slice(-8);

    const customer = await ok<{ id: string; code: string }>(
      await post(["v1", "customers"], {
        name: `E2E Tea House ${stamp} (TEST DATA)`,
        customer_type: "shop",
        phone: `+9196${stamp}`,
        plan: {
          product: "RAW-COW-MILK",
          default_quantity: "2.000",
          quantity_unit: "L",
          unit_price: "60.0000",
        },
      }),
      "create customer with a plan",
    );
    expect(customer.code).toMatch(/^CUS-/);

    // Three days of deliveries, recorded through the portal. The client sends
    // quantities and NEVER a price — the plan's rate is the platform's.
    const days = ["2026-03-02", "2026-03-03", "2026-03-04"];
    for (const day of days) {
      await ok(
        await post(["v1", "deliveries"], {
          customer_id: customer.id,
          delivery_date: day,
          slot: "morning",
          status: "delivered",
          quantity: "2.000",
        }),
        `deliver ${day}`,
      );
    }

    const invoice = await ok<Record<string, unknown>>(
      await post(["v1", "invoices"], {
        customer_id: customer.id,
        period_from: days[0],
        period_to: days[days.length - 1],
      }),
      "generate invoice",
    );
    expect(invoice.line_count).toBe(3);
    // 3 x 2L at 60.0000. Again: read, not computed.
    const subtotal = String(invoice.subtotal);
    expect(subtotal).toBe("360.00");
    const invoiceId = String(invoice.id);

    const issued = await ok<Record<string, unknown>>(
      await post(["v1", "invoices", invoiceId, "issue"]),
      "issue invoice",
    );
    expect(issued.status).toBe("issued");
    // Issuing makes it immutable; it must not make it a different number.
    expect(String(issued.subtotal)).toBe(subtotal);
    const total = String(issued.total ?? issued.subtotal);

    const before = await ok<Record<string, unknown>>(
      await get(["v1", "customers", customer.id, "balance"]),
      "balance before payment",
    );
    expect(String(before.outstanding)).toBe(total);

    const payment = await ok<Record<string, unknown>>(
      await post(["v1", "customer-payments"], {
        customer_id: customer.id,
        amount: total,
        method: "MOBILE_MONEY",
        reference: `E2E-${stamp}`,
      }),
      "record customer payment",
    );
    expect(String(payment.amount)).toBe(total);

    const after = await ok<Record<string, unknown>>(
      await get(["v1", "customers", customer.id, "balance"]),
      "balance after payment",
    );
    expect(String(after.paid)).toBe(total);
    expect(String(after.outstanding)).toBe("0.00");

    const detail = await ok<Record<string, unknown>>(
      await get(["v1", "invoices", invoiceId]),
      "invoice after payment",
    );
    const inv = (detail.invoice ?? detail) as Record<string, unknown>;
    expect(inv.status).toBe("paid");
    expect(String(detail.outstanding)).toBe("0.00");

    const receipts = await eventually(
      async () =>
        await ok<{ items: Record<string, unknown>[] }>(
          await get(["v1", "customer-receipts"], `?customer_id=${customer.id}`),
          "customer receipts",
        ),
      (r) => r.items.length > 0,
      "the customer receipt",
    );
    expect(String(receipts.items[0].amount)).toBe(total);
    expect(String(receipts.items[0].receipt_number)).toMatch(/^CRC-/);
  });

  // (c) The WO-5 loop, closed over the real boundary.
  it("reprices a rate-pending collection once a card covers it, and settles it", async () => {
    if (!harnessed) return;
    await signIn(fx.users.admin.email, fx.org.id);

    // A centre with no published card: capture is rate-pending, exactly as the
    // first physical handset run found on day one.
    const centre = fx.centres[1].id;
    const supplier = fx.suppliers[1].id;
    // The seed assigns an operator to centre 1 only, and a centre with nobody
    // at it is NOT_READY — the platform refuses to open a session there, which
    // is correct. Assigning someone is onboarding, done through the same
    // endpoint the runbook uses.
    const me = await ok<{ user: { id: string } }>(await get(["v1", "auth", "me"]), "who am I");
    await post(["v1", "collection-centers", centre, "operators"], {
      user_id: me.user.id,
      role_label: "operator",
    });
    // And a farmer may only deliver where they are assigned — the platform
    // refuses the rest, which is the rule this journey depends on rather than
    // works around.
    await post(["v1", "suppliers", supplier, "centers"], { center_id: centre });
    const session = await ok<{ id: string }>(
      await post(["v1", "collection-sessions"], { center_id: centre, label: "e2e-reprice" }),
      "open session",
    );
    const { id: txId, done } = await collect(session.id, supplier);
    expect(done.pricing_status).toBe("pricing_unavailable");
    expect(done.calculation_id).toBeNull();
    expect(done.gross_amount).toBeNull();

    const settlement = await ok<{ id: string }>(
      await post(["v1", "settlements"], {
        supplier_id: supplier,
        center_id: centre,
        currency: "INR",
        period_from: "2026-01-01",
        period_to: "2026-12-31",
      }),
      "create settlement",
    );
    // Stranded: settlement will not touch a collection with no calculation.
    const beforeSweep = await ok<{ added: number }>(
      await post(["v1", "settlements", settlement.id, "collect"]),
      "sweep before repricing",
    );
    expect(beforeSweep.added).toBe(0);

    await publishRateCard(centre, `E2ELATE${Date.now().toString().slice(-6)}`, "44.0000", "2026-01-01");

    const repriced = await ok<Record<string, unknown>>(
      await post(["v1", "milk-transactions", txId, "reprice"]),
      "reprice",
    );
    expect(repriced.pricing_status).toBe("priced");
    expect(String(repriced.unit_price)).toBe("44.0000");
    const gross = String(repriced.gross_amount);
    expect(gross).toBe("1320.00");

    // Repricing an already-priced collection is a conflict, never a quiet
    // recalculation — the immutability rule, over the real boundary.
    const again = await post(["v1", "milk-transactions", txId, "reprice"]);
    expect(again.status).toBe(409);

    const afterSweep = await ok<{ added: number }>(
      await post(["v1", "settlements", settlement.id, "collect"]),
      "sweep after repricing",
    );
    expect(afterSweep.added).toBe(1);

    await ok(await post(["v1", "settlements", settlement.id, "calculate"]), "calculate");
    const totals = await ok<Record<string, unknown>>(
      await get(["v1", "settlements", settlement.id]),
      "settlement totals",
    );
    const body = (totals.settlement ?? totals) as Record<string, unknown>;
    // The farmer is finally payable, for exactly what the reprice computed.
    expect(String(body.gross_amount)).toBe(gross);
  });
});

describe("a locked-out person gets back in", () => {
  /**
   * The journey WO-8 could not write, because the harness found the defect it
   * was meant to traverse: the reset email carried no code at all
   * (LACTEVA-BACKEND-004). The code now travels as a secret, sent directly, so
   * this can finally be driven the whole way — request, read the code out of
   * the message the platform really delivered, spend it, and sign in.
   *
   * It is the only test anywhere that proves the reset flow is usable by a
   * human being. Everything in WO-4 mocked the platform, which is exactly why
   * a flow nobody could finish shipped on both clients.
   */
  it("resets a password with the code from the real email, and retires the old one", async () => {
    if (!harnessed) return;
    const maildir = process.env.LACTEVA_E2E_MAIL;
    if (!maildir) return; // the sink is the harness's, not this test's to build

    const count = () =>
      readdirSync(maildir).filter((f) => f.startsWith("msg-")).length;
    const before = count();

    // The manager, because this journey ends by signing them in and the
    // operator is used by the tests above.
    const email = fx.users.manager.email;
    const oldPassword = fx.password;
    const newPassword = "a-new-password-from-e2e-1";

    // Through the portal's OWN pre-auth route — /api/proxy would refuse this,
    // which is the whole reason that route exists.
    //
    // `tenant_id` is supplied deliberately: without it the platform's lookup
    // does not find a tenant user, `request_password_reset` returns early, and
    // the 202-always contract hides the fact that nothing happened. The
    // portal's `lib/api.ts` helper omits it today — reported as a DISCOVERED
    // item, not fixed here.
    const asked = await resetRequest(
      new Request("http://portal.test/api/auth/password-reset/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, tenant_id: fx.org.id }),
      }),
    );
    expect(asked.status).toBe(202);
    // 202 says nothing about whether the account exists, and must not.
    expect(await asked.text()).not.toMatch(/token|code/i);

    // Read the code the way its reader does: out of the delivered message.
    const code = await (async () => {
      const deadline = Date.now() + 20_000;
      while (Date.now() < deadline) {
        const files = readdirSync(maildir)
          .filter((f) => f.startsWith("msg-"))
          .sort()
          .slice(before)
          .reverse();
        for (const file of files) {
          const body = readFileSync(join(maildir, file), "utf8").replace(
            /=\r?\n/g,
            "",
          );
          const m = body.match(/complete your reset:\s*(\S+?)\.(?:\s|$)/);
          if (m) return m[1];
        }
        await new Promise((r) => setTimeout(r, 250));
      }
      throw new Error("the platform delivered no reset code");
    })();
    expect(code.length).toBeGreaterThan(20);

    const confirmed = await resetConfirm(
      new Request("http://portal.test/api/auth/password-reset/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: code, new_password: newPassword }),
      }),
    );
    expect(confirmed.status).toBe(204);

    // The new password works...
    jar.clear();
    const withNew = await login(
      new Request("http://portal.test/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          password: newPassword,
          tenant_id: fx.org.id,
        }),
      }),
    );
    expect(withNew.status).toBe(204);
    expect(jar.size).toBeGreaterThan(0);

    // ...and the old one does not. A reset that leaves the previous password
    // working has not reset anything.
    jar.clear();
    const withOld = await login(
      new Request("http://portal.test/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          password: oldPassword,
          tenant_id: fx.org.id,
        }),
      }),
    );
    expect(withOld.status).toBeGreaterThanOrEqual(400);
    expect(jar.size).toBe(0);

    // And the code is spent: a one-time code that can be replayed is not one.
    const replay = await resetConfirm(
      new Request("http://portal.test/api/auth/password-reset/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: code, new_password: "yet-another-one-1" }),
      }),
    );
    expect(replay.status).toBeGreaterThanOrEqual(400);
  });

  it("refuses a code that was never issued", async () => {
    if (!harnessed) return;
    const bogus = await resetConfirm(
      new Request("http://portal.test/api/auth/password-reset/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: "not-a-real-code-at-all",
          new_password: "should-never-apply-1",
        }),
      }),
    );
    expect(bogus.status).toBeGreaterThanOrEqual(400);
    expect(bogus.status).not.toBe(204);
  });
});
