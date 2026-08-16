/**
 * The subscription screen (DEMO-026).
 *
 * What is asserted is that the page RENDERS THE SERVER'S ANSWER — status,
 * trial dates, centre counts — and offers no way to change any of it. A screen
 * that could move a subscription would be a screen that could grant itself
 * free software.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/admin/subscription",
}));

import SubscriptionPage from "@/app/admin/subscription/page";
import * as api from "@/lib/api";

const TRIAL = {
  plan_code: "LACTEVA_TRIAL",
  plan_name: "Lacteva Trial",
  status: "trialing" as const,
  trial_started_on: "2026-08-14",
  trial_ends_on: "2026-09-13",
  started_on: null,
  current_period_end: null,
  subscribed_centres: 0,
  billing_period: "month",
  currency_code: "INR",
  price: null,
};

const ENTITLED = {
  status: "trialing",
  business_date: "2026-08-16",
  trial_days_remaining: 28,
  can_operate: true,
  can_read: true,
  active_centres: 3,
  subscribed_centres: 0,
  centre_allowance: null,
  within_centre_allowance: true,
};

afterEach(() => vi.restoreAllMocks());

describe("the subscription screen", () => {
  it("shows the trial, its end date and the centre count", async () => {
    vi.spyOn(api, "getSubscription").mockResolvedValue(TRIAL);
    vi.spyOn(api, "getEntitlement").mockResolvedValue(ENTITLED);

    render(<SubscriptionPage />);

    await waitFor(() =>
      expect(screen.getAllByText("trialing").length).toBeGreaterThan(0),
    );
    expect(screen.getAllByText("2026-09-13").length).toBeGreaterThan(0);
    expect(screen.getByText("28 day(s) remaining")).toBeInTheDocument();
    expect(screen.getByText("3 active")).toBeInTheDocument();
    expect(screen.getByText("unlimited during the trial")).toBeInTheDocument();
  });

  it("says no price rather than inventing one", async () => {
    vi.spyOn(api, "getSubscription").mockResolvedValue(TRIAL);
    vi.spyOn(api, "getEntitlement").mockResolvedValue(ENTITLED);

    render(<SubscriptionPage />);
    await waitFor(() =>
      expect(screen.getByText("not yet published")).toBeInTheDocument(),
    );
    // A zero would read as "free forever", which is not what is being offered.
    expect(screen.queryByText("0.00")).not.toBeInTheDocument();
  });

  it("explains an ended subscription without threatening the data", async () => {
    vi.spyOn(api, "getSubscription").mockResolvedValue({
      ...TRIAL,
      status: "expired" as const,
    });
    vi.spyOn(api, "getEntitlement").mockResolvedValue({
      ...ENTITLED,
      status: "expired",
      trial_days_remaining: -2,
      can_operate: false,
    });

    render(<SubscriptionPage />);
    await waitFor(() =>
      expect(screen.getByText(/records remain readable/)).toBeInTheDocument(),
    );
    expect(screen.getByText("ended 2 day(s) ago")).toBeInTheDocument();
  });

  it("offers no control that could change the subscription", async () => {
    vi.spyOn(api, "getSubscription").mockResolvedValue(TRIAL);
    vi.spyOn(api, "getEntitlement").mockResolvedValue(ENTITLED);

    render(<SubscriptionPage />);
    await waitFor(() =>
      expect(screen.getAllByText("trialing").length).toBeGreaterThan(0),
    );
    // The guarantee: nothing on this page can be pressed to become `active`.
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(
      screen.getByText(/activated by the Lacteva team/),
    ).toBeInTheDocument();
  });
});
