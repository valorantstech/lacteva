/**
 * The subscription screen (DEMO-026, extended by DEMO-027).
 *
 * What is asserted is that the page RENDERS THE SERVER'S ANSWER — status,
 * trial dates, centre counts, and now the amount to pay — and cannot change
 * any of it. The page may ASK the server to open a checkout or to look again;
 * it never computes a price, never names a status, and never reports a payment
 * as successful on its own. A screen that could do any of those would be a
 * screen that could grant itself free software.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/admin/subscription",
}));

import SubscriptionPage from "@/app/admin/subscription/page";
import * as api from "@/lib/api";

const TRIAL: api.SubscriptionView = {
  plan_code: "LACTEVA_TRIAL",
  plan_name: "Lacteva Trial",
  status: "trialing",
  trial_started_on: "2026-08-14",
  trial_ends_on: "2026-09-13",
  started_on: null,
  current_period_end: null,
  subscribed_centres: 0,
  billing_period: "month",
  currency_code: "INR",
  price: null,
};

const ENTITLED: api.EntitlementView = {
  status: "trialing",
  business_date: "2026-08-16",
  trial_days_remaining: 28,
  can_operate: true,
  can_read: true,
  active_centres: 3,
  subscribed_centres: 0,
  centre_allowance: null,
  within_centre_allowance: true,
  grace_ends_on: null,
  current_period_end: null,
};

const QUOTE: api.QuoteView = {
  plan_code: "LACTEVA_STANDARD",
  plan_name: "Lacteva Standard",
  currency_code: "INR",
  unit_price: "1200.00",
  quantity: 3,
  amount: "3600.00",
  billing_period: "month",
  active_centres: 3,
  payable: true,
  payable_reason: null,
};

const PENDING: api.SubscriptionPaymentView = {
  id: "11111111-1111-1111-1111-111111111111",
  plan_code: "LACTEVA_STANDARD",
  unit_price: "1200.00",
  quantity: 3,
  amount: "3600.00",
  currency_code: "INR",
  status: "pending",
  provider: "test",
  provider_reference: "test_ref_1",
  checkout_url: "https://payments.test.invalid/checkout/1",
  failure_code: null,
  failure_message: null,
  created_at: "2026-08-16T09:00:00Z",
  completed_at: null,
};

/** The default: nothing pending, a payable quote. Tests override what matters. */
function stubApi({
  subscription = TRIAL,
  entitlement = ENTITLED,
  payments = [] as api.SubscriptionPaymentView[],
  quote = QUOTE,
}: Partial<{
  subscription: api.SubscriptionView;
  entitlement: api.EntitlementView;
  payments: api.SubscriptionPaymentView[];
  quote: api.QuoteView;
}> = {}) {
  vi.spyOn(api, "getSubscription").mockResolvedValue(subscription);
  vi.spyOn(api, "getEntitlement").mockResolvedValue(entitlement);
  vi.spyOn(api, "getSubscriptionPayments").mockResolvedValue(payments);
  vi.spyOn(api, "getSubscriptionQuote").mockResolvedValue(quote);
}

afterEach(() => vi.restoreAllMocks());

describe("the subscription screen", () => {
  it("shows the trial, its end date and the centre count", async () => {
    stubApi();

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
    stubApi({
      quote: { ...QUOTE, unit_price: null, amount: null, payable: false },
    });

    render(<SubscriptionPage />);
    await waitFor(() =>
      expect(screen.getByText("not yet published")).toBeInTheDocument(),
    );
    // A zero would read as "free forever", which is not what is being offered.
    expect(screen.queryByText("0.00")).not.toBeInTheDocument();
  });

  it("explains an ended subscription without threatening the data", async () => {
    stubApi({
      subscription: { ...TRIAL, status: "expired" },
      entitlement: {
        ...ENTITLED,
        status: "expired",
        trial_days_remaining: -2,
        can_operate: false,
      },
    });

    render(<SubscriptionPage />);
    await waitFor(() =>
      expect(screen.getByText(/records remain readable/)).toBeInTheDocument(),
    );
    expect(screen.getByText("ended 2 day(s) ago")).toBeInTheDocument();
  });

  it("offers no control that could set the subscription's status", async () => {
    // DEMO-026 asserted there were NO buttons at all. DEMO-027 gives the page
    // a pay button, so that phrasing is obsolete — but the guarantee it stood
    // for is not, and this is it: a control may ASK the server to do something,
    // and no control anywhere names a status, an amount or a currency.
    stubApi();

    render(<SubscriptionPage />);
    await waitFor(() =>
      expect(screen.getAllByText("trialing").length).toBeGreaterThan(0),
    );

    for (const button of screen.queryAllByRole("button")) {
      const label = (button.textContent ?? "").toLowerCase();
      for (const forbidden of [
        "activate",
        "mark paid",
        "set status",
        "succeeded",
      ]) {
        expect(label).not.toContain(forbidden);
      }
    }
    // And the only thing the client ever sends is a plan and a quantity.
    const checkout = vi.spyOn(api, "startSubscriptionCheckout");
    expect(checkout.getMockImplementation()).toBeUndefined();
  });
});

describe("paying for a subscription", () => {
  it("shows the amount the SERVER calculated and never multiplies it here", async () => {
    stubApi();

    render(<SubscriptionPage />);
    await waitFor(() =>
      expect(screen.getByText(/1200.00 INR per centre/)).toBeInTheDocument(),
    );
    expect(screen.getByText("INR 3600.00")).toBeInTheDocument();
    // The page asked the server for the quote rather than working it out.
    expect(api.getSubscriptionQuote).toHaveBeenCalledWith(
      "LACTEVA_STANDARD",
      3,
    );
  });

  it("sends only a plan and a centre count when starting a checkout", async () => {
    stubApi();
    const checkout = vi
      .spyOn(api, "startSubscriptionCheckout")
      .mockResolvedValue(PENDING);

    render(<SubscriptionPage />);
    await waitFor(() =>
      expect(screen.getByText("INR 3600.00")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Pay for 3 centre/ }));

    await waitFor(() => expect(checkout).toHaveBeenCalledTimes(1));
    expect(checkout).toHaveBeenCalledWith("LACTEVA_STANDARD", 3);
  });

  it("offers no checkout when the deployment cannot take money", async () => {
    stubApi({
      quote: {
        ...QUOTE,
        unit_price: null,
        amount: null,
        payable: false,
        payable_reason:
          "no payment provider is configured for this deployment — subscriptions are activated by the Lacteva team",
      },
    });

    render(<SubscriptionPage />);
    await waitFor(() =>
      expect(
        screen.getByText(/no payment provider is configured/),
      ).toBeInTheDocument(),
    );
    // A button that opened nothing would be the one dishonest thing here.
    expect(screen.queryByRole("button", { name: /Pay for/ })).toBeNull();
  });

  it("asks the server about a pending payment instead of claiming success", async () => {
    stubApi({ payments: [PENDING] });
    const refresh = vi
      .spyOn(api, "refreshSubscriptionCheckout")
      .mockResolvedValue(PENDING);

    render(<SubscriptionPage />);
    await waitFor(() =>
      expect(screen.getByText(/awaiting confirmation/)).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /Check payment status/ }),
    );
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    // It takes no argument: the browser cannot name a payment or an outcome.
    expect(refresh).toHaveBeenCalledWith();
  });

  it("says a past-due subscription still works, and until when", async () => {
    stubApi({
      subscription: {
        ...TRIAL,
        plan_code: "LACTEVA_STANDARD",
        status: "past_due",
      },
      entitlement: {
        ...ENTITLED,
        status: "past_due",
        can_operate: true,
        grace_ends_on: "2026-09-30",
        trial_days_remaining: null,
      },
    });

    render(<SubscriptionPage />);
    await waitFor(() =>
      expect(
        screen.getByText(/last renewal did not go through/),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("2026-09-30")).toBeInTheDocument();
    expect(screen.getByText(/Nothing has been deleted/)).toBeInTheDocument();
  });

  it("lists payment history without exposing anything secret", async () => {
    stubApi({
      payments: [
        {
          ...PENDING,
          status: "succeeded",
          checkout_url: null,
          completed_at: "2026-08-16T09:05:00Z",
        },
      ],
    });

    render(<SubscriptionPage />);
    await waitFor(() =>
      expect(screen.getByText("Payment history")).toBeInTheDocument(),
    );
    expect(screen.getByText("test_ref_1")).toBeInTheDocument();
    expect(screen.getAllByText("INR 3600.00").length).toBeGreaterThan(0);
    for (const secret of ["secret", "signature", "api_key"]) {
      expect(document.body.textContent?.toLowerCase()).not.toContain(secret);
    }
  });
});
