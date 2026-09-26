/** WO-100: a pasted code is forgiven its surroundings; a fragment is read once and removed. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { normaliseCode, takeCodeFromFragment } from "@/lib/one-time-code";

const TOKEN = "abcXYZ_-09".repeat(4);

describe("normaliseCode", () => {
  it.each([
    `${TOKEN}.`,
    `"${TOKEN}"`,
    `code: ${TOKEN}\n`,
    ` ${TOKEN} \r\n`,
    `https://app.lacteva.com/accept-invitation#code=${TOKEN}`,
  ])("keeps the token and nothing else from %j", (pasted) => {
    expect(normaliseCode(pasted)).toBe(TOKEN);
  });
  it("is empty for nothing", () => {
    expect(normaliseCode("")).toBe("");
    expect(normaliseCode("...")).toBe("");
  });
});

describe("takeCodeFromFragment", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("reads #code= once and removes it from the address bar", () => {
    const replaceState = vi.fn();
    vi.stubGlobal("location", { hash: `#code=${TOKEN}.`, pathname: "/accept-invitation", search: "" });
    vi.stubGlobal("history", { replaceState });
    expect(takeCodeFromFragment()).toBe(TOKEN);
    expect(replaceState).toHaveBeenCalledWith(null, "", "/accept-invitation");
  });
  it("returns nothing when there is no fragment, and touches nothing", () => {
    const replaceState = vi.fn();
    vi.stubGlobal("location", { hash: "", pathname: "/accept-invitation", search: "" });
    vi.stubGlobal("history", { replaceState });
    expect(takeCodeFromFragment()).toBe("");
    expect(replaceState).not.toHaveBeenCalled();
  });
});
