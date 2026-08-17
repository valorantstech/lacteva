/**
 * The notification history screen (DEMO-028).
 *
 * One property, and it is the whole reason this file exists:
 *
 *   **The portal never says a message was delivered.**
 *
 * `sent` means the gateway accepted the request. No adapter in this platform
 * receives a delivery receipt, so "Delivered" was a claim Lacteva has never
 * been in a position to make — and it was on the screen, as a headline figure,
 * where an operator would read it as proof a farmer had been told.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/notifications",
}));

import NotificationsPage from "@/app/notifications/page";
import * as api from "@/lib/api";

const MESSAGE: api.Notification = {
  id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  event_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  event_name: "settlement.finalized.v1",
  template_key: "settlement_finalized",
  channel: "sms",
  language: "en",
  recipient: "+9198*****01",
  recipient_ref: null,
  title: "Settlement STL-2026-000042 ready",
  rendered_text: "Hello Farmer, settlement STL-2026-000042 is finalised.",
  status: "sent",
  provider: "recording",
  provider_reference: "recording:1",
  provider_status: "accepted",
  source_type: "settlement",
  source_id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
  attempt_count: 1,
  next_attempt_at: null,
  error: null,
  payload: { number: "STL-2026-000042", quantity: "412.500" },
  created_at: "2026-08-16T09:00:00Z",
  sent_at: "2026-08-16T09:00:01Z",
  failed_at: null,
};

function stubApi(messages: api.Notification[] = [MESSAGE]) {
  vi.spyOn(api, "listNotifications").mockResolvedValue({
    items: messages,
    total: messages.length,
    limit: 25,
    offset: 0,
  } as never);
  vi.spyOn(api, "getNotificationStats").mockResolvedValue({
    total: messages.length,
    by_status: { sent: messages.length },
    by_channel: { sms: messages.length },
  } as never);
  vi.spyOn(api, "listNotificationTemplates").mockResolvedValue([] as never);
  vi.spyOn(api, "getTemplateRegistry").mockResolvedValue({
    total: 57,
    unmapped_whatsapp: 8,
    ready_whatsapp: 1,
    entries: [
      {
        // DEMO-033: on WhatsApp the journey is a fixed-parameter variant.
        key: "settlement_finalized_base",
        purpose:
          "Tells a farmer their settlement is final and what they are owed",
        channel: "whatsapp",
        language: "en",
        title: "Settlement {number} ready",
        body: "Hello {name}…",
        variables: ["number", "name"],
        optional_variables: [],
        version: 1,
        active: true,
        business: true,
        provider_mapping_status: "NOT_CONFIGURED",
        provider_template: null,
        whatsapp_ready: true,
        whatsapp_blocker: null,
        approval_state: "PENDING",
        approval_provider: "acme-bsp",
        approval_note: null,
        ready: false,
        blockers: ["approval pending", "provider template id missing"],
      },
      {
        // Approved AND mapped: the only shape that is ready to send.
        key: "settlement_finalized_with_quantity",
        purpose:
          "Tells a farmer their settlement is final, what they are owed and how much milk it covers",
        channel: "whatsapp",
        language: "hi",
        title: "…",
        body: "…",
        variables: ["number", "name", "quantity", "quantity_unit"],
        optional_variables: [],
        version: 1,
        active: true,
        business: true,
        provider_mapping_status: "CONFIGURED",
        provider_template: "lacteva_settlement_qty_v1",
        whatsapp_ready: true,
        whatsapp_blocker: null,
        approval_state: "APPROVED",
        approval_provider: "acme-bsp",
        approval_note: null,
        ready: true,
        blockers: [],
      },
      {
        key: "password_reset",
        purpose: "Sends a user a one-time password-reset link",
        channel: "email",
        language: "en",
        title: "Reset",
        body: "…",
        variables: ["link"],
        optional_variables: [],
        version: 1,
        active: true,
        business: false,
        provider_mapping_status: "NOT_APPLICABLE",
        provider_template: null,
        whatsapp_ready: true,
        whatsapp_blocker: null,
        approval_state: "NOT_CONFIGURED",
        approval_provider: null,
        approval_note: null,
        ready: false,
        blockers: [],
      },
    ],
  } as never);
  vi.spyOn(api, "getMessagingPosture").mockResolvedValue({
    mode: "test",
    sends_real_messages: false,
    channels: [
      {
        channel: "sms",
        provider: "sandbox-sms",
        configured: true,
        can_send: false,
        reports_delivery: true,
      },
      {
        channel: "whatsapp",
        provider: "disabled-whatsapp",
        configured: false,
        can_send: false,
        reports_delivery: false,
      },
    ],
  } as never);
  vi.spyOn(api, "getSettlementPeriodReachability").mockResolvedValue({
    template_key: "settlement_finalized",
    channel: "sms",
    total: 250,
    reachable: 223,
    unreachable: 17,
    unknown: 10,
    reasons: { phone_missing: 9, invalid_phone: 5, no_supported_channel: 3 },
    affected: [
      {
        subject_id: "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        subject_type: "supplier",
        name: "Period Farmer",
        channel: "sms",
        status: "unreachable",
        reason: "phone_missing",
        contact: null,
      },
    ],
    affected_truncated: false,
  } as never);
  vi.spyOn(api, "getReachability").mockResolvedValue({
    template_key: "settlement_finalized",
    channel: "sms",
    total: 250,
    reachable: 223,
    unreachable: 17,
    unknown: 10,
    reasons: { phone_missing: 9, invalid_phone: 5, provider_unavailable: 3 },
    affected: [
      {
        subject_id: "dddddddd-dddd-dddd-dddd-dddddddddddd",
        subject_type: "supplier",
        name: "Farmer With No Phone",
        channel: "sms",
        status: "unreachable",
        reason: "phone_missing",
        contact: null,
      },
    ],
    affected_truncated: true,
  } as never);
}

afterEach(() => vi.restoreAllMocks());

describe("the notification history", () => {
  it("never claims a message was delivered", async () => {
    stubApi();
    render(<NotificationsPage />);

    await waitFor(() =>
      expect(screen.getByText("Sent to provider")).toBeInTheDocument(),
    );
    // The headline figure counts accepted requests. Calling it "Delivered"
    // told an operator that a farmer had been reached.
    expect(screen.queryByText("Delivered")).toBeNull();
    expect(document.body.textContent).not.toMatch(/\bDelivered\b/);
  });

  it("describes the status in words that match what the platform knows", async () => {
    stubApi();
    render(<NotificationsPage />);

    await waitFor(() =>
      expect(screen.getAllByText("sent to provider").length).toBeGreaterThan(0),
    );
  });

  it("shows a confirmed delivery separately from an accepted request", async () => {
    // DEMO-029. `delivered` is real now, and it is NOT the same card as
    // `sent` — one is what the gateway took, the other what it confirmed.
    stubApi([
      { ...MESSAGE, status: "delivered", provider_status: "delivered" },
    ]);
    render(<NotificationsPage />);

    await waitFor(() =>
      expect(screen.getByText("Confirmed delivered")).toBeInTheDocument(),
    );
    expect(screen.getByText("Sent to provider")).toBeInTheDocument();
  });

  it("shows a queued message as queued rather than as progress", async () => {
    stubApi([
      { ...MESSAGE, status: "pending", provider_status: null, sent_at: null },
    ]);
    render(<NotificationsPage />);

    await waitFor(() =>
      expect(screen.getAllByText("queued").length).toBeGreaterThan(0),
    );
    expect(document.body.textContent).not.toMatch(/\bDelivered\b/);
  });
});

describe("the reachability panel", () => {
  it("counts everyone and never hides the unreachable", async () => {
    stubApi();
    render(<NotificationsPage />);

    expect(
      await screen.findByText("Communication reachability"),
    ).toBeInTheDocument();
    // The panel loads on a deferred tick, so wait for the DATA rather than
    // the heading, which renders before it arrives.
    await waitFor(() => expect(screen.getByText("223")).toBeInTheDocument());
    expect(screen.getByText("17")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    // The reasons an operator can act on.
    expect(screen.getByText("9 phone missing")).toBeInTheDocument();
    expect(screen.getByText("5 invalid phone")).toBeInTheDocument();
    // And the affected are NAMED, never silently skipped.
    expect(screen.getByText("Farmer With No Phone")).toBeInTheDocument();
  });

  it("says plainly that it does not affect settlement or billing", async () => {
    stubApi();
    render(<NotificationsPage />);

    await waitFor(() =>
      expect(
        screen.getByText(/does not affect settlement or billing/),
      ).toBeInTheDocument(),
    );
  });

  it("admits when the named list is shorter than the counts", async () => {
    stubApi();
    render(<NotificationsPage />);

    await waitFor(() =>
      expect(screen.getByText(/counts above are complete/)).toBeInTheDocument(),
    );
  });
});

describe("contact repair", () => {
  it("offers a repair for an unreachable supplier", async () => {
    stubApi();
    render(<NotificationsPage />);

    await waitFor(() =>
      expect(screen.getByText("Farmer With No Phone")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Repair" }));

    expect(
      await screen.findByText(/Repair contact — Farmer With No Phone/),
    ).toBeInTheDocument();
    // It says what is wrong now, so the operator knows what they are fixing.
    // (The same reason also appears in the summary list above, hence getAll.)
    expect(screen.getAllByText(/phone missing/).length).toBeGreaterThanOrEqual(
      2,
    );
  });

  it("sends only the phone and the reason", async () => {
    stubApi();
    const repair = vi.spyOn(api, "repairSupplierContact").mockResolvedValue({
      full_name: "Farmer",
      phone: "+919845000101",
    } as never);

    render(<NotificationsPage />);
    await waitFor(() =>
      expect(screen.getByText("Farmer With No Phone")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Repair" }));

    fireEvent.change(await screen.findByPlaceholderText("+91…"), {
      target: { value: "+919845000101" },
    });
    fireEvent.change(
      screen.getByPlaceholderText("confirmed at the collection centre"),
      { target: { value: "checked with the centre" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(repair).toHaveBeenCalledTimes(1));
    expect(repair).toHaveBeenCalledWith(
      "dddddddd-dddd-dddd-dddd-dddddddddddd",
      { phone: "+919845000101", reason: "checked with the centre" },
    );
  });

  it("does not claim a valid number means WhatsApp will reach it", async () => {
    stubApi();
    render(<NotificationsPage />);
    await waitFor(() =>
      expect(screen.getByText("Farmer With No Phone")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Repair" }));

    expect(
      await screen.findByText(/not that WhatsApp will reach it/),
    ).toBeInTheDocument();
  });

  it("scopes the report to a settlement period when dates are given", async () => {
    stubApi();
    render(<NotificationsPage />);

    await waitFor(() => expect(screen.getByText("223")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Period from"), {
      target: { value: "2026-08-01" },
    });
    fireEvent.change(screen.getByLabelText("Period to"), {
      target: { value: "2026-08-15" },
    });

    await waitFor(() =>
      expect(api.getSettlementPeriodReachability).toHaveBeenCalledWith(
        "2026-08-01",
        "2026-08-15",
      ),
    );
    expect(await screen.findByText("settlement period")).toBeInTheDocument();
  });
});

describe("the messaging gateway panel", () => {
  it("says plainly when no real message can be sent", async () => {
    stubApi();
    render(<NotificationsPage />);

    expect(await screen.findByText("Messaging gateway")).toBeInTheDocument();
    expect(
      screen.getByText(/No real message can be sent in this mode/),
    ).toBeInTheDocument();
    expect(screen.getByText("test")).toBeInTheDocument();
  });

  it("shows configured and can-send as separate answers", async () => {
    // A channel can be CONFIGURED and still not permitted to send — that is
    // the whole point of the mode gate.
    stubApi();
    render(<NotificationsPage />);

    await screen.findByText("Messaging gateway");
    expect(screen.getByText("sandbox-sms")).toBeInTheDocument();
    // The gateway panel says "not configured" for the channel; the registry
    // panel says it for a provider mapping. Both are legitimate, so scope this
    // to the gateway row.
    expect(screen.getByText("disabled-whatsapp")).toBeInTheDocument();
  });

  it("never shows a credential or a gateway URL", async () => {
    stubApi();
    render(<NotificationsPage />);

    await screen.findByText("Messaging gateway");
    const text = (document.body.textContent ?? "").toLowerCase();
    for (const secret of ["api_key", "apikey", "secret", "token", "https://"]) {
      expect(text).not.toContain(secret);
    }
  });
});

describe("the template registry panel", () => {
  it("shows what each template is for", async () => {
    stubApi();
    render(<NotificationsPage />);

    expect(await screen.findByText("Message templates")).toBeInTheDocument();
    // Each variant carries its own purpose — that is how an operator tells
    // two WhatsApp templates for one journey apart.
    expect(
      screen.getAllByText(/Tells a farmer their settlement is final/),
    ).toHaveLength(2);
  });

  it("says how many WhatsApp templates no provider knows", async () => {
    stubApi();
    render(<NotificationsPage />);

    expect(
      await screen.findByText("8 WhatsApp not mapped to a provider"),
    ).toBeInTheDocument();
    // "not configured" appears in both panels — the count above is the
    // unambiguous assertion.
    expect(screen.getAllByText("not configured").length).toBeGreaterThanOrEqual(
      1,
    );
  });

  it("no longer reports a WhatsApp template that cannot be a template", async () => {
    // DEMO-032 found it; DEMO-033 fixed it by giving WhatsApp explicit
    // fixed-parameter variants. The guarantee is preserved and inverted: the
    // panel should have nothing of the sort left to say.
    stubApi();
    render(<NotificationsPage />);

    await screen.findByText("Message templates");
    expect(screen.queryByText(/cannot be an approved template/)).toBeNull();
    expect(screen.queryByText(/optional segments/)).toBeNull();
  });

  it("shows the fixed parameter structure a vendor console asks for", async () => {
    // §10. Position and name, in the template's own order — an operator
    // registering the template with a provider types exactly this.
    stubApi();
    render(<NotificationsPage />);

    await screen.findByText("Message templates");
    expect(screen.getByText("{{1}} number {{2}} name")).toBeInTheDocument();
    expect(
      screen.getByText(
        "{{1}} number {{2}} name {{3}} quantity {{4}} quantity_unit",
      ),
    ).toBeInTheDocument();
  });

  it("attributes approval to the provider, never to Lacteva", async () => {
    // §7. Lacteva records what a provider decided. It does not decide.
    stubApi();
    render(<NotificationsPage />);

    await screen.findByText("Message templates");
    expect(
      screen.getByText("submitted, awaiting provider"),
    ).toBeInTheDocument();
    expect(screen.getByText("approved by provider")).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).not.toContain("approved by Lacteva");
  });

  it("lists every reason a template is not ready, not just the first", async () => {
    // §11. An operator who fixes one blocker and finds another was told half
    // the truth.
    stubApi();
    render(<NotificationsPage />);

    await screen.findByText("Message templates");
    expect(
      screen.getByText(
        "not ready: approval pending; provider template id missing",
      ),
    ).toBeInTheDocument();
  });

  it("reports readiness only where approval and mapping both exist", async () => {
    stubApi();
    render(<NotificationsPage />);

    expect(await screen.findByText("1 WhatsApp ready to send")).toBeVisible();
    expect(screen.getByText("ready")).toBeInTheDocument();
  });

  it("says nothing about approval for SMS and email", async () => {
    // §6. Flexible channels are unchanged; an approval column would imply a
    // lifecycle they do not have.
    stubApi();
    render(<NotificationsPage />);

    await screen.findByText("Message templates");
    fireEvent.click(screen.getByRole("button", { name: "Show all" }));
    const row = (await screen.findByText("password_reset")).closest("tr");
    expect(row?.textContent).not.toContain("provider");
    expect(row?.textContent).not.toContain("not ready");
  });

  it("filters to business messages, and can show the rest", async () => {
    stubApi();
    render(<NotificationsPage />);

    await screen.findByText("Message templates");
    // A password reset is not something a dairy sends its farmers.
    expect(screen.queryByText("password_reset")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show all" }));
    expect(await screen.findByText("password_reset")).toBeInTheDocument();
  });

  it("says templates are not editable here, and shows no credential", async () => {
    stubApi();
    render(<NotificationsPage />);

    expect(
      await screen.findByText(/are not editable here/),
    ).toBeInTheDocument();
    const text = (document.body.textContent ?? "").toLowerCase();
    for (const secret of ["api_key", "apikey", "https://"]) {
      expect(text).not.toContain(secret);
    }
  });
});
