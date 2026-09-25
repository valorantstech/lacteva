/**
 * The top bar fits whatever a name happens to be (WO-98).
 *
 * Found by the committed phone audit on live, acting as the first real
 * tenant: "Gavyam Dairy & Sweets" made a longer chip than the demo tenant's
 * name, and the bar's right-hand group ended 21px past a 320px phone on 23
 * of 28 pages. jsdom does no layout, so this pins the mechanism — every
 * name in the bar is a `min-w-0` flex child that truncates — and the audit
 * pins the pixels.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/",
}));

import { AppShell } from "@/components/app-shell";
import * as api from "@/lib/api";

beforeEach(() => vi.restoreAllMocks());

describe("the top bar with long names", () => {
  it("truncates the organisation chip and the person's name rather than growing past the phone", async () => {
    vi.spyOn(api, "getSession").mockResolvedValue({
      authenticated: true,
      acting_tenant_id: null,
      user: {
        id: "u1",
        email: "owner@gavyam.example",
        full_name: "Shrimant Gavyam Dairy Proprietor Deshmukh-Patil",
        locale: "en",
        is_active: true,
      },
      tenant_id: "org-1",
      organization: {
        id: "org-1",
        name: "Gavyam Dairy & Sweets and Confectionery Private Limited",
        slug: "gavyam",
        country_code: "IN",
        currency_code: "INR",
        currency_symbol: "₹",
        timezone: "Asia/Kolkata",
        default_language: "en",
        supported_languages: ["en"],
        languages: [{ tag: "en", name: "English", endonym: "English", rtl: false }],
        quantity_unit: "litre",
        quantity_unit_label: "L",
        modules: ["sales"],
      },
      membership: null,
      roles: [{ name: "tenant-admin", description: "", center_id: null }],
      center_scope: null,
      customer_id: null,
      permissions: ["*"],
    } as never);
    render(
      <AppShell>
        <div>PAGE</div>
      </AppShell>,
    );
    const chip = await screen.findByTestId("shell-organization-chip");
    expect(chip.className).toMatch(/\bmin-w-0\b/);
    const chipText = chip.querySelector(".truncate")!;
    expect(chipText.textContent).toContain("Gavyam Dairy");
    expect(chipText.className).toMatch(/max-w-\[7rem\]/);
    const name = screen.getByTestId("shell-user-name");
    expect(name.className).toMatch(/\btruncate\b/);
    expect(name.parentElement!.className).toMatch(/\bmin-w-0\b/);
    // The group that holds them can shrink; Sign out cannot.
    const group = name.parentElement!.parentElement!;
    expect(group.className).toMatch(/\bmin-w-0\b/);
    expect(screen.getByRole("button", { name: "Sign out" }).className).toMatch(/\bshrink-0\b/);
  });
});
