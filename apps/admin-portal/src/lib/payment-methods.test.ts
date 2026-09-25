/**
 * The portal's payment methods are the platform's (WO-83 §4).
 *
 * Two lists used to be hard-coded in `api.ts`; a method added on one side
 * and not the other becomes unofferable without anybody noticing. This test
 * reads the platform's tuples out of the repository and fails on any drift.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  CUSTOMER_PAYMENT_METHODS,
  CUSTOMER_PAYMENT_METHOD_LABELS,
  PAYMENT_METHODS,
} from "@/lib/api";
import { billSummary, waMeLink, waMeNumber } from "@/lib/whatsapp";

function platformTuple(file: string): string[] {
  const source = readFileSync(resolve(__dirname, "../../../../services/platform-core/src/platform_core/modules", file), "utf8");
  const match = source.match(/^PAYMENT_METHODS = \(([^)]*)\)/m);
  if (!match) throw new Error(`no PAYMENT_METHODS in ${file}`);
  return match[1].split(",").map((s) => s.trim().replace(/"/g, "")).filter(Boolean);
}

describe("payment methods", () => {
  it("the customer list is the platform's billing tuple, in order", () => {
    expect([...CUSTOMER_PAYMENT_METHODS]).toEqual(platformTuple("billing/models.py"));
    expect(CUSTOMER_PAYMENT_METHODS).toContain("UPI");
    for (const method of CUSTOMER_PAYMENT_METHODS) {
      expect(CUSTOMER_PAYMENT_METHOD_LABELS[method].en).toBeTruthy();
      expect(CUSTOMER_PAYMENT_METHOD_LABELS[method].hi).toBeTruthy();
    }
  });

  it("the supplier list is the platform's payment tuple, in order", () => {
    expect([...PAYMENT_METHODS]).toEqual(platformTuple("payment/models.py"));
  });
});

describe("Send on WhatsApp", () => {
  it("opens wa.me with the digits of an E.164 number and the summary", () => {
    expect(waMeNumber("+91 98450 12345")).toBe("919845012345");
    expect(waMeNumber("")).toBeNull();
    expect(waMeNumber("12345")).toBeNull();
    const text = billSummary({
      organization: "Gavyam Dairy & Sweets",
      invoice_number: "INV-2026-000031",
      period_from: "2026-08-01",
      period_to: "2026-08-31",
      currency: "INR",
      delivered_quantity: "31",
      quantity_unit: "L",
      items_count: 1,
      total: "2294.00",
      previous_balance: "-412.00",
      amount_due: "1882.00",
      pay_to: "UPI gavyam@upi",
    });
    expect(text).toContain("bill INV-2026-000031 for 2026-08-01 to 2026-08-31");
    expect(text).toContain("Milk delivered: 31 L");
    expect(text).toContain("Advance: 412.00 INR");
    expect(text).not.toContain("-412");
    expect(text).toContain("Pay to: UPI gavyam@upi");
    expect(text).toContain("available from the shop");
    const link = waMeLink("+91 98450 12345", text)!;
    expect(link.startsWith("https://wa.me/919845012345?text=")).toBe(true);
    expect(decodeURIComponent(link.split("text=")[1])).toBe(text);
    expect(waMeLink(null, text)).toBeNull();
  });
});
