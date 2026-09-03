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
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, describeDetail, describeError, login } from "@/lib/api";

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

/**
 * WO-68 — a validation error must not crash the page (LACTEVA-ADMIN-021).
 *
 * The body below is the REAL 422 captured from the live API when the day book
 * sent the half-typed date a `<input type="date">` emits while someone types.
 * `detail` is an ARRAY of objects; the portal declared it a string and React
 * threw error #31 rendering it. Not a hand-made shape — this is what the
 * platform sends.
 */
const CAPTURED_422 = {
  detail: [
    {
      type: "date_from_datetime_parsing",
      loc: ["query", "business_date"],
      msg: "Input should be a valid date or datetime, month value is outside expected range of 1-12",
      input: "0008-30-2026",
      ctx: { error: "month value is outside expected range of 1-12" },
    },
  ],
};

function respond(body: unknown, status: number) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status,
      statusText: status === 422 ? "Unprocessable Entity" : "Error",
      json: async () => body,
    } as unknown as Response),
  );
}

describe("describeError and a real 422 (WO-68)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("turns FastAPI's validation array into text that names the field", async () => {
    respond(CAPTURED_422, 422);
    let caught: unknown;
    try {
      await api("/v1/reports/day-book?business_date=0008-30-2026");
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(ApiError);
    const error = caught as ApiError;
    // The construction site already made it a string — every direct reader
    // of `.detail` is safe, not only the ones that go through describeError.
    expect(typeof error.detail).toBe("string");
    expect(error.detail).toBe(
      "business_date: Input should be a valid date or datetime, month value is outside expected range of 1-12",
    );
    expect(error.detail).not.toContain("query");
    expect(error.issues).toHaveLength(1);
    expect(error.issues?.[0].loc).toEqual(["query", "business_date"]);

    const shown = describeError(error);
    expect(typeof shown).toBe("string");
    expect(shown).toContain("business_date");
    expect(shown).not.toContain("[object Object]");
  });

  it("never returns a non-string for any shape the platform emits", () => {
    // The guard: string detail, dict extra, 422 list — and a hand-built error
    // whose detail is an object, which is what a forgotten path would produce.
    const shapes: unknown[] = [
      new ApiError(404, "Not found."),
      new ApiError(409, "The request conflicts with the current state.", {
        stage: "product",
        rows: 3,
      }),
      new ApiError(
        422,
        CAPTURED_422.detail as unknown as string,
        undefined,
        "unprocessable",
      ),
      new ApiError(422, describeDetail(CAPTURED_422.detail)),
      new ApiError(500, { unexpected: true } as unknown as string),
      new ApiError(500, undefined as unknown as string),
      new Error("network down"),
      undefined,
      null,
      42,
    ];
    for (const shape of shapes) {
      const shown = describeError(shape, "fallback");
      expect(typeof shown, `for ${JSON.stringify(shape)}`).toBe("string");
      expect(shown.length).toBeGreaterThan(0);
      expect(shown).not.toContain("[object Object]");
    }
  });

  it("lists several issues one per line, and copes with an issue that names no field", () => {
    expect(
      describeDetail([
        { loc: ["body", "quantity"], msg: "Input should be greater than 0" },
        { loc: ["body", "lines", 2, "rate"], msg: "Field required" },
        { msg: "Value error, at least one line is required" },
        "a bare string issue",
        null,
      ]),
    ).toBe(
      [
        "quantity: Input should be greater than 0",
        "lines.2.rate: Field required",
        "Value error, at least one line is required",
        "a bare string issue",
      ].join("\n"),
    );
    expect(describeDetail([], "nothing useful")).toBe("nothing useful");
    expect(describeDetail({ a: 1 }, "nothing useful")).toBe("nothing useful");
    expect(describeDetail("", "nothing useful")).toBe("nothing useful");
  });

  it("folds the 422 shape on the pre-auth routes too", async () => {
    // login(), the password-reset pair and the tenant switch never touch
    // api(); each had its own copy of the throw. One helper now.
    respond(
      { detail: [{ loc: ["body", "email"], msg: "value is not a valid email address" }] },
      422,
    );
    await expect(login("not-an-email", "pw")).rejects.toMatchObject({
      detail: "email: value is not a valid email address",
    });
  });
});
