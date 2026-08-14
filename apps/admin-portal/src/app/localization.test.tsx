/**
 * The portal speaks the person's language and the organization's money
 * (DEMO-013 §6, §7, §11, §12).
 *
 * What is asserted is the ARCHITECTURE, not the vocabulary: that a screen
 * looks a string up by key, that the key comes from the session rather than
 * the browser, and that money and dates come from the organization. A test
 * that only checked "Hindi appears" would pass just as well against a
 * hard-coded conditional, which is the thing the work order forbids.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/admin/settings",
}));

import SettingsPage from "@/app/admin/settings/page";
import { LocaleProvider, baseLanguage, translatorFor, useT } from "@/lib/i18n";
import { CATALOGS, KEYS } from "@/lib/messages";

function routeFetch(routes: Record<string, unknown>) {
  const spy = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const match = Object.keys(routes).find((key) => url.includes(key));
    if (!match) {
      return new Response(JSON.stringify({ title: "not_found", detail: "No route." }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(routes[match]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

const INDIA_SETTINGS = {
  country_code: "IN",
  country_name: "India",
  currency_code: "INR",
  currency_symbol: "₹",
  timezone: "Asia/Kolkata",
  default_language: "en-IN",
  supported_languages: ["en-IN", "hi-IN"],
  languages: [
    { tag: "en-IN", name: "English", endonym: "English", rtl: false },
    { tag: "hi-IN", name: "Hindi", endonym: "हिन्दी", rtl: false },
  ],
};

const KENYA_SETTINGS = {
  country_code: "KE",
  country_name: "Kenya",
  currency_code: "KES",
  currency_symbol: "KSh",
  timezone: "Africa/Nairobi",
  default_language: "en-KE",
  supported_languages: ["en-KE"],
  languages: [{ tag: "en-KE", name: "English", endonym: "English", rtl: false }],
};

function session(overrides: Record<string, unknown> = {}) {
  return {
    authenticated: true,
    acting_tenant_id: null,
    tenant_id: "t-1",
    user: { id: "u-1", email: "a@b.example", full_name: "A", locale: "en-IN", is_active: true },
    organization: { id: "t-1", name: "Lacteva India Demo", slug: "india", ...INDIA_SETTINGS },
    membership: null,
    roles: [],
    center_scope: null,
    permissions: ["organization.read", "organization.settings.manage"],
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the catalogs", () => {
  it("has a Hindi string for every English key the portal defines", () => {
    // A missing key is not fatal — it falls back to English — but a catalog
    // that has quietly stopped keeping up is worth knowing about, and this is
    // cheaper than noticing on a screen.
    const missing = KEYS.filter((key) => !(key in CATALOGS.hi));
    expect(missing, `Hindi is missing: ${missing.join(", ")}`).toEqual([]);
  });

  it("falls back to English rather than showing a blank", () => {
    const t = translatorFor("hi-IN");
    expect(t("nav.customers")).toBe("ग्राहक");
    // A key no catalog defines comes back as the key: something an engineer
    // can grep for, rather than an empty space in front of a dairy manager.
    expect(t("nav.doesNotExist")).toBe("nav.doesNotExist");
  });

  it("reads the catalog by language, ignoring the region", () => {
    expect(baseLanguage("hi-IN")).toBe("hi");
    expect(translatorFor("hi-IN")("action.save")).toBe(translatorFor("hi")("action.save"));
  });

  it("treats an unknown language as English rather than failing", () => {
    expect(translatorFor("kl-GL")("action.save")).toBe("Save");
  });
});

describe("a screen renders in the session's language", () => {
  function Probe() {
    const t = useT();
    return <p>{t("nav.customers")}</p>;
  }

  it("shows English to an English user", () => {
    render(
      <LocaleProvider locale="en-IN">
        <Probe />
      </LocaleProvider>,
    );
    expect(screen.getByText("Customers")).toBeInTheDocument();
  });

  it("shows Hindi to a Hindi user — same component, no conditional", () => {
    render(
      <LocaleProvider locale="hi-IN">
        <Probe />
      </LocaleProvider>,
    );
    expect(screen.getByText("ग्राहक")).toBeInTheDocument();
  });
});

describe("organization settings", () => {
  it("shows an Indian dairy its own currency and clock", async () => {
    routeFetch({
      "/v1/organizations/settings/locale": INDIA_SETTINGS,
      "/api/auth/session": session(),
    });
    render(
      <LocaleProvider locale="en-IN">
        <SettingsPage />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("org-currency")).toBeInTheDocument());
    expect(screen.getByTestId("org-currency")).toHaveTextContent("₹ INR");
    expect(screen.getByTestId("org-timezone")).toHaveTextContent("Asia/Kolkata");
    expect(screen.getByText("India")).toBeInTheDocument();
  });

  it("shows a Kenyan dairy KES and Nairobi — the same page, different tenant", async () => {
    routeFetch({
      "/v1/organizations/settings/locale": KENYA_SETTINGS,
      "/api/auth/session": session({
        organization: { id: "t-2", name: "Kilima", slug: "kilima", ...KENYA_SETTINGS },
      }),
    });
    render(
      <LocaleProvider locale="en-KE">
        <SettingsPage />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("org-currency")).toBeInTheDocument());
    expect(screen.getByTestId("org-currency")).toHaveTextContent("KSh KES");
    expect(screen.getByTestId("org-timezone")).toHaveTextContent("Africa/Nairobi");
  });

  it("offers only the languages the organization enabled", async () => {
    routeFetch({
      "/v1/organizations/settings/locale": KENYA_SETTINGS,
      "/api/auth/session": session({ permissions: ["organization.read"] }),
    });
    render(
      <LocaleProvider locale="en-KE">
        <SettingsPage />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("choose-language-en-KE")).toBeInTheDocument());
    // Hindi is a language the platform speaks and this dairy has not enabled.
    // Offering it would be a control that leads to a refusal.
    expect(screen.queryByTestId("choose-language-hi-IN")).toBeNull();
  });

  it("hides the organization-wide controls from someone who may only read", async () => {
    routeFetch({
      "/v1/organizations/settings/locale": INDIA_SETTINGS,
      "/api/auth/session": session({ permissions: ["organization.read"] }),
    });
    render(
      <LocaleProvider locale="en-IN">
        <SettingsPage />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("org-currency")).toBeInTheDocument());
    expect(screen.queryByTestId("toggle-language-hi-IN")).toBeNull();
    // ...but a person may always choose their OWN language.
    expect(screen.getByTestId("choose-language-hi-IN")).toBeInTheDocument();
  });

  it("sends a language change to the platform and reloads", async () => {
    const spy = routeFetch({
      "/v1/organizations/settings/locale": INDIA_SETTINGS,
      "/api/auth/session": session(),
      "/v1/auth/me/language": { id: "u-1", locale: "hi-IN" },
    });
    const reload = vi.fn();
    Object.defineProperty(window, "location", {
      value: { reload, assign: vi.fn(), href: "/" },
      writable: true,
    });

    render(
      <LocaleProvider locale="en-IN">
        <SettingsPage />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("choose-language-hi-IN")).toBeInTheDocument());
    await userEvent.click(screen.getByTestId("choose-language-hi-IN"));

    await waitFor(() => {
      const sent = spy.mock.calls.find((call) =>
        String(call[0]).includes("/v1/auth/me/language"),
      ) as unknown as [string, RequestInit] | undefined;
      expect(sent, "the language was never sent to the platform").toBeTruthy();
      expect(String(sent?.[1]?.body)).toContain("hi-IN");
    });
    await waitFor(() => expect(reload).toHaveBeenCalled());
  });
});
