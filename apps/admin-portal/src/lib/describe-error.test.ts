/**
 * One field, two meanings — settled once for the whole portal
 * (LACTEVA-ADMIN-013).
 *
 * The platform puts two different kinds of thing in `extra`, and the status
 * code cannot tell them apart. A validation refusal carries the actionable
 * specific there — "no published rate card covers this center, product, and
 * date" — while `detail` holds the generic translated sentence, "The request
 * conflicts with the current state.", which is true and useless. A 403 carries
 * the raw permission KEY, and `organization.member.manage` tells an
 * administrator nothing at all.
 *
 * Before this the portal held three different opinions about that. Forty-three
 * sites read `detail` and threw the specific away; one — the reprice handler
 * from LACTEVA-BACKEND-001 — got it right with a shape test; and three
 * (settlements, customers, customer detail) preferred `extra` with NO guard,
 * so a 403 on any of them printed a registry key at an administrator. That
 * last group is the reason this is a shared helper and not a documented habit.
 *
 * The rule is the one the handset settled in LACTEVA-MOBILE-001: the tell is
 * the SHAPE, never the status.
 */
import { describe, expect, it } from "vitest";

import { ApiError, describeError } from "@/lib/api";

describe("describeError", () => {
  it("prefers a sentence in extra over the generic detail", () => {
    // The whole point: `detail` is true and unhelpful, `extra` is the remedy.
    const error = new ApiError(
      409,
      "The request conflicts with the current state.",
      "no published rate card covers this center, product, and date",
    );
    expect(describeError(error)).toBe(
      "no published rate card covers this center, product, and date",
    );
  });

  it("never shows a permission key, whatever the status", () => {
    // `<module>.<entity>.<action>`. An administrator cannot act on this, and a
    // real operator was shown one on a real phone before the rule existed.
    for (const key of [
      "organization.member.manage",
      "pricing.ratecard.read",
      "collection.transaction.record",
    ]) {
      const error = new ApiError(
        403,
        "You do not have permission to perform this action.",
        key,
      );
      expect(describeError(error)).toBe(
        "You do not have permission to perform this action.",
      );
      expect(describeError(error)).not.toContain(key);
    }
  });

  it("falls back to detail when there is no extra", () => {
    expect(describeError(new ApiError(404, "Not found."))).toBe("Not found.");
    expect(describeError(new ApiError(400, "Bad request.", ""))).toBe(
      "Bad request.",
    );
  });

  it("leaves a structured extra alone and returns the detail", () => {
    // The import summary and the pricing-resolution stage read `extra` as an
    // object. Stringifying it here would put `[object Object]` in front of an
    // operator and break those callers at the same time.
    const error = new ApiError(422, "pricing failed", {
      stage: "product",
      rows: 3,
    });
    expect(describeError(error)).toBe("pricing failed");
  });

  it("handles the things that are not ApiErrors at all", () => {
    // A transport failure is not a platform refusal, and the fallback is what
    // a screen says when it has nothing better.
    expect(describeError(new Error("network down"))).toBe("network down");
    expect(describeError(undefined, "Could not reach the platform")).toBe(
      "Could not reach the platform",
    );
    expect(describeError("a bare string", "fallback")).toBe("fallback");
  });

  it("treats a shape that merely looks technical as a sentence", () => {
    // The guard is deliberately narrow: only the exact registry shape is
    // suppressed. A real sentence that happens to contain a dot is still the
    // most useful thing the platform said.
    const error = new ApiError(
      409,
      "generic",
      "supplier is not assigned to this collection center.",
    );
    expect(describeError(error)).toBe(
      "supplier is not assigned to this collection center.",
    );
  });
});
