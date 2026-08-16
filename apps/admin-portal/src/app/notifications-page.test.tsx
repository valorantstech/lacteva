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
import { render, screen, waitFor } from "@testing-library/react";
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
