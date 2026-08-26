/**
 * Staff invitation, both ends (LACTEVA-ADMIN-002).
 *
 * The endpoint has been implemented and SMTP-proven since SEC-003 and had
 * zero client callers, so onboarding a dairy's staff meant raw API calls.
 * These tests defend the two properties that make the UI trustworthy rather
 * than merely present:
 *
 *   1. the portal never handles the invitation TOKEN. The platform withholds
 *      it deliberately — it used to be returned, which let whoever issued an
 *      invitation accept it themselves under the invitee's email — so the
 *      invite response must carry none, and nothing here may invent one;
 *   2. a refusal shows the PLATFORM's sentence. A viewer without
 *      `organization.member.manage` gets a 403, and watching nothing happen is
 *      the failure this replaces.
 *
 * The accept page is asserted through the pre-auth route it must use: the
 * ordinary `/api/proxy` pipe requires the very session the call creates.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/admin/users",
}));

import AcceptInvitationPage from "@/app/accept-invitation/page";
import UsersPage from "@/app/admin/users/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const ROLES = [
  {
    id: "r1",
    name: "tenant-viewer",
    description: "Read-only",
    tenant_id: null,
    system: true,
    permissions: [],
    assignments: 1,
  },
  {
    id: "r2",
    name: "COLLECTION_OPERATOR",
    description: "The person at the intake bay",
    tenant_id: null,
    system: true,
    permissions: ["collection.transaction.record"],
    assignments: 3,
  },
];

/** The platform's real answer shape — metadata only, never a token. */
const INVITATION = {
  id: "inv-1",
  email: "colleague@dairy.example",
  role_name: "COLLECTION_OPERATOR",
  status: "pending",
  expires_at: "2026-09-02T10:00:00Z",
};

/** Routes every call the users page makes; `invite` decides the POST answer. */
function stubPortal(invite: () => Response) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/v1/invitations") && init?.method === "POST") {
      return invite();
    }
    if (url.includes("/v1/authz/roles")) return json(ROLES);
    if (url.includes("/v1/members")) return json([]);
    if (url.includes("/v1/collection-centers"))
      return json({ items: [], total: 0, limit: 100, offset: 0 });
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => {
  vi.unstubAllGlobals();
  // The accept page navigates on success; jsdom would otherwise refuse it.
  vi.stubGlobal("location", { assign: vi.fn(), pathname: "/accept-invitation" });
});
afterEach(() => vi.unstubAllGlobals());

describe("inviting a colleague", () => {
  it("sends the invitation and reports when it expires", async () => {
    const spy = stubPortal(() => json(INVITATION, 201));
    render(<UsersPage />);

    // The roles offered come from the platform, never a compiled-in list.
    await screen.findByRole("option", { name: "COLLECTION_OPERATOR" });

    await userEvent.type(
      screen.getByLabelText("Invite by email"),
      "colleague@dairy.example",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Role"),
      "COLLECTION_OPERATOR",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Send invitation" }),
    );

    await waitFor(() =>
      expect(
        screen.getByText(/Invitation sent to colleague@dairy\.example/),
      ).toBeTruthy(),
    );

    // Sent to the platform's real path, with the role the admin chose.
    const post = spy.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "POST",
    )!;
    expect(String(post[0])).toContain("/v1/invitations");
    expect(
      JSON.parse(String((post[1] as RequestInit).body)),
    ).toEqual({
      email: "colleague@dairy.example",
      role_name: "COLLECTION_OPERATOR",
    });
  });

  it("surfaces a viewer's 403 rather than doing nothing", async () => {
    stubPortal(() =>
      json(
        {
          title: "forbidden",
          status: 403,
          detail: "You do not have permission to perform this action.",
          extra: "organization.member.manage",
        },
        403,
      ),
    );
    render(<UsersPage />);
    await screen.findByRole("option", { name: "COLLECTION_OPERATOR" });

    await userEvent.type(
      screen.getByLabelText("Invite by email"),
      "colleague@dairy.example",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Send invitation" }),
    );

    await waitFor(() =>
      expect(
        screen.getByText("You do not have permission to perform this action."),
      ).toBeTruthy(),
    );
    // The registry key is the platform's business, not the administrator's.
    expect(screen.queryByText("organization.member.manage")).toBeNull();
  });
});

describe("accepting an invitation", () => {
  it("joins through the PRE-AUTH route, never the session proxy", async () => {
    let seenUrl = "";
    let seenBody = "";
    const spy = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      seenUrl = String(url);
      seenBody = String(init?.body ?? "");
      return json({ id: "u9" }, 201);
    });
    vi.stubGlobal("fetch", spy);

    render(<AcceptInvitationPage />);
    await userEvent.type(screen.getByLabelText("Invitation code"), "code-abc");
    await userEvent.type(screen.getByLabelText("Full name"), "Asha Verma");
    await userEvent.type(
      screen.getByLabelText("Password"),
      "correct-horse-battery",
    );
    await userEvent.click(screen.getByRole("button", { name: "Join" }));

    await waitFor(() => expect(spy).toHaveBeenCalled());
    // /api/proxy would refuse this: the session does not exist yet.
    expect(seenUrl).toBe("/api/auth/invitation");
    expect(seenUrl).not.toContain("/api/proxy");
    // The code travels in the BODY. A token in a query string reaches browser
    // history, referrers and every access log on the way.
    expect(JSON.parse(seenBody)).toEqual({
      token: "code-abc",
      full_name: "Asha Verma",
      password: "correct-horse-battery",
    });
  });

  it("shows the platform's reason for a spent code, and keeps the form", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json(
          {
            title: "invalid_token",
            status: 400,
            detail: "That invitation has already been used.",
          },
          400,
        ),
      ),
    );

    render(<AcceptInvitationPage />);
    await userEvent.type(screen.getByLabelText("Invitation code"), "spent-code");
    await userEvent.type(screen.getByLabelText("Full name"), "Asha Verma");
    await userEvent.type(
      screen.getByLabelText("Password"),
      "correct-horse-battery",
    );
    await userEvent.click(screen.getByRole("button", { name: "Join" }));

    await waitFor(() =>
      expect(
        screen.getByText("That invitation has already been used."),
      ).toBeTruthy(),
    );
    // Retyping a long code because one field was wrong is a small cruelty.
    expect(
      (screen.getByLabelText("Invitation code") as HTMLInputElement).value,
    ).toBe("spent-code");
    expect(
      (screen.getByLabelText("Full name") as HTMLInputElement).value,
    ).toBe("Asha Verma");
  });
});
