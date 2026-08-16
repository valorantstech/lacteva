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
