/**
 * A login's details can be corrected (WO-87).
 *
 *   * Admin → Users: a member's name is edited in the row; "change" on the
 *     email starts a change through the platform and SAYS who confirms and
 *     what happens to sessions; a pending change shows in the row with its
 *     expiry and a cancel;
 *   * the person's own account, on Settings: the same two flows;
 *   * the confirm page spends the code through the PRE-AUTH handler and then
 *     sends the person to sign in with the new address;
 *   * the help text says what is NOT on offer — a login is never moved
 *     between people.
 *
 * Nothing here sets an email: every request is a REQUEST, and the test pins
 * the exact body the platform received.
 */
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let searchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/admin/users",
  useSearchParams: () => searchParams,
}));

import UsersPage from "@/app/admin/users/page";
import OrganizationSettingsPage from "@/app/admin/settings/page";
import ConfirmEmailPage from "@/app/confirm-email/page";
import type { Session } from "@/lib/api";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const USER = {
  id: "u-2",
  email: "raghvan@kilima.example",
  full_name: "Raghvan",
  locale: "en",
  is_active: true,
  last_login_at: null,
  created_at: "2026-09-01T00:00:00Z",
};

const PENDING = {
  new_email: "raghavan@kilima.example",
  requested_by: "u-1",
  requested_at: "2026-09-25T06:00:00Z",
  expires_at: "2026-09-26T06:00:00Z",
};

function member(pending: typeof PENDING | null = null) {
  return {
    user_id: "u-2",
    status: "active",
    joined_at: "2026-09-01T00:00:00Z",
    roles: [{ name: "DRIVER", center_id: null }],
    pending_email_change: pending,
  };
}

type Call = { url: string; method: string; body: unknown };

function stubUsers(pending: typeof PENDING | null = null) {
  const calls: Call[] = [];
  let current = pending;
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    calls.push({ url, method, body });
    if (url.endsWith("/v1/members/u-2/profile") && method === "PUT")
      return json({ ...USER, full_name: body.full_name });
    if (url.endsWith("/v1/members/u-2/email-change") && method === "POST") {
      current = { ...PENDING, new_email: body.new_email };
      return json(current, 202);
    }
    if (url.endsWith("/v1/members/u-2/email-change") && method === "DELETE") {
      current = null;
      return new Response(null, { status: 204 });
    }
    if (url.endsWith("/v1/members")) return json([member(current)]);
    if (url.endsWith("/v1/identity/users/u-2")) return json(USER);
    if (url.includes("/v1/authz/roles")) return json([]);
    if (url.includes("/v1/collection-centers"))
      return json({ items: [], total: 0, limit: 100, offset: 0 });
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return calls;
}


/** The alert that says something in particular (LACTEVA-QA-005): a page can
 *  hold more than one, so the singular query is never asked. */
async function alertSaying(pattern: RegExp, container: HTMLElement = document.body) {
  return waitFor(() => {
    const found = within(container)
      .getAllByRole("alert")
      .find((el) => pattern.test(el.textContent ?? ""));
    if (!found) throw new Error(`no alert yet matching ${pattern}`);
    return found;
  });
}

beforeEach(() => {
  vi.unstubAllGlobals();
  searchParams = new URLSearchParams();
});
afterEach(() => vi.unstubAllGlobals());

describe("Admin → Users (WO-87 §2, §3, §4)", () => {
  it("corrects a member's name in the row through the platform", async () => {
    const calls = stubUsers();
    const user = userEvent.setup();
    render(<UsersPage />);
    await screen.findByText("Raghvan");
    await user.click(screen.getByRole("button", { name: "Edit name of Raghvan" }));
    const field = screen.getByLabelText("Name");
    await user.clear(field);
    await user.type(field, "Raghavan");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")).toMatchObject({
        url: "/api/proxy/v1/members/u-2/profile",
        body: { full_name: "Raghavan" },
      }),
    );
    expect(await screen.findByText("Name corrected to Raghavan.")).toBeInTheDocument();
  });

  it("starts an email change, says who confirms and what happens to sessions, then shows it pending with a cancel", async () => {
    const calls = stubUsers();
    const user = userEvent.setup();
    render(<UsersPage />);
    await screen.findByText("raghvan@kilima.example");
    await user.click(screen.getByRole("button", { name: "Change email of Raghvan" }));
    const form = screen.getByTestId("email-change-u-2");
    expect(form.textContent).toMatch(/must confirm from its inbox/);
    expect(form.textContent).toMatch(/current address is told now/);
    expect(form.textContent).toMatch(/every session is signed out/);
    await user.type(within(form).getByLabelText("New email"), "raghavan@kilima.example");
    await user.click(within(form).getByRole("button", { name: "Send code" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")).toMatchObject({
        url: "/api/proxy/v1/members/u-2/email-change",
        body: { new_email: "raghavan@kilima.example" },
      }),
    );
    // Nothing was written to the account: no PUT, and the row still shows the
    // current address with the change pending beside it.
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
    const pending = await screen.findByTestId("pending-email-u-2");
    expect(pending.textContent).toMatch(/changing to raghavan@kilima.example/);
    expect(pending.textContent).toMatch(/expires 2026-09-26 06:00/);
    expect(screen.getByText("raghvan@kilima.example")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change email of Raghvan" })).toBeNull();

    await user.click(within(pending).getByRole("button", { name: "cancel" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "DELETE")?.url).toBe(
        "/api/proxy/v1/members/u-2/email-change",
      ),
    );
    await waitFor(() => expect(screen.queryByTestId("pending-email-u-2")).toBeNull());
  });

  it("says that a login is never moved between people", async () => {
    stubUsers();
    render(<UsersPage />);
    const help = await screen.findByTestId("users-help");
    expect(help.textContent).toMatch(/cannot be moved to a different person/);
    // WO-88 turned the remedy into the departure checklist; the fact is the same.
    expect(help.textContent).toMatch(/Remove from organisation.*and invite the new person/);
    expect(help.textContent).toMatch(/reinstated, never invited again/);
  });
});

describe("my own account on Settings (WO-87 §1, §3)", () => {
  const ORGANIZATION = {
    id: "org-1",
    name: "Kilima",
    slug: "kilima",
    country_code: "KE",
    currency_code: "KES",
    currency_symbol: "KSh",
    timezone: "Africa/Nairobi",
    default_language: "en",
    supported_languages: ["en"],
    languages: [{ tag: "en", name: "English", endonym: "English", rtl: false }],
    quantity_unit: "litre",
    quantity_unit_label: "L",
    modules: ["collection", "sales"],
  };
  const LOCALE = {
    country_code: "KE",
    country_name: "Kenya",
    currency_code: "KES",
    currency_symbol: "KSh",
    timezone: "Africa/Nairobi",
    default_language: "en",
    supported_languages: ["en"],
    languages: [{ tag: "en", name: "English", endonym: "English", rtl: false }],
    quantity_unit: "litre",
    quantity_unit_label: "L",
    units: ["litre", "kg"],
    trade_unit: null,
    trade_unit_label: null,
    conversion_factor: null,
    conversion_effective_from: null,
    modules: ["collection", "sales"],
    available_modules: [
      { key: "collection", label: "collects", description: "in" },
      { key: "sales", label: "sells", description: "out" },
    ],
  };
  function session(pending: typeof PENDING | null): Session {
    return {
      authenticated: true,
      acting_tenant_id: null,
      user: USER,
      tenant_id: "org-1",
      organization: ORGANIZATION,
      membership: null,
      roles: [{ name: "DRIVER", description: "", center_id: null }],
      center_scope: null,
      permissions: [],
      pending_email_change: pending,
    };
  }

  function stubSettings() {
    const calls: Call[] = [];
    let pending: typeof PENDING | null = null;
    const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      calls.push({ url, method, body });
      if (url.includes("/api/auth/session")) return json(session(pending));
      if (url.endsWith("/v1/organizations/settings/locale")) return json(LOCALE);
      if (url.endsWith("/v1/auth/me/profile") && method === "PUT")
        return json({ ...USER, full_name: body.full_name });
      if (url.endsWith("/v1/auth/me/email-change") && method === "POST") {
        pending = { ...PENDING, new_email: body.new_email };
        return json(pending, 202);
      }
      if (url.endsWith("/v1/auth/me/email-change") && method === "DELETE") {
        pending = null;
        return new Response(null, { status: 204 });
      }
      return json({ title: "not_found" }, 404);
    });
    vi.stubGlobal("fetch", spy);
    return calls;
  }

  it("saves my name, and asks for an email change that the new address must confirm", async () => {
    const calls = stubSettings();
    const user = userEvent.setup();
    render(<OrganizationSettingsPage />);
    const section = await screen.findByTestId("my-account");
    const name = within(section).getByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Raghavan");
    await user.click(within(section).getByRole("button", { name: "Save name" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")).toMatchObject({
        url: "/api/proxy/v1/auth/me/profile",
        body: { full_name: "Raghavan" },
      }),
    );

    expect(section.textContent).toMatch(/must confirm from its inbox/);
    expect(section.textContent).toMatch(/every session is signed out/);
    await user.type(within(section).getByLabelText("New email"), "raghavan@kilima.example");
    await user.click(within(section).getByRole("button", { name: "Send confirmation code" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")).toMatchObject({
        url: "/api/proxy/v1/auth/me/email-change",
        body: { new_email: "raghavan@kilima.example" },
      }),
    );
    const pending = await screen.findByTestId("my-pending-email");
    expect(pending.textContent).toMatch(/raghavan@kilima.example/);
    // The current address is still the login, and still shown as such.
    expect(section.textContent).toMatch(/raghvan@kilima.example/);
    await user.click(within(pending).getByRole("button", { name: "cancel" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "DELETE")?.url).toBe("/api/proxy/v1/auth/me/email-change"),
    );
  });
});

describe("the confirm page (WO-87 §3)", () => {
  it("spends the code from the link through the pre-auth handler, then sends the person to sign in", async () => {
    searchParams = new URLSearchParams("token=code-xyz");
    const calls: Call[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        calls.push({
          url: String(input),
          method: init?.method ?? "GET",
          body: init?.body ? JSON.parse(String(init.body)) : null,
        });
        return new Response(null, { status: 204 });
      }),
    );
    const assign = vi.fn();
    vi.stubGlobal("location", { assign, pathname: "/confirm-email" });
    const user = userEvent.setup();
    await act(async () => {
      render(<ConfirmEmailPage />);
    });
    expect(screen.getByLabelText("Confirmation code")).toHaveValue("code-xyz");
    expect(screen.getByText(/old address keeps working/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toMatchObject({
      url: "/api/auth/email-change/confirm",
      method: "POST",
      body: { token: "code-xyz" },
    });
    // No session proxy, no bearer: the pre-auth handler alone.
    expect(calls[0].url.startsWith("/api/proxy")).toBe(false);
    expect(await screen.findByText(/Every earlier session was signed out/)).toBeInTheDocument();
    await user.click(screen.getByTestId("confirm-email-login"));
    expect(assign).toHaveBeenCalledWith("/login");
  });

  it("says why a dead code failed and keeps the form", async () => {
    searchParams = new URLSearchParams("token=stale");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json({ title: "invalid_token", status: 400, detail: "invalid or expired token" }, 400),
      ),
    );
    const user = userEvent.setup();
    await act(async () => {
      render(<ConfirmEmailPage />);
    });
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(
      await alertSaying(/expired, been cancelled, or already been used/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Confirmation code")).toHaveValue("stale");
  });
});
