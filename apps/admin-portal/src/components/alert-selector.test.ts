/**
 * Ask for the alert you mean (LACTEVA-QA-005; after QA-003 and QA-004).
 *
 * `findByRole("alert")` and `getByRole("alert")` ask for THE alert. A page
 * with an `ErrorState` on it already has one, so on any screen that can also
 * raise a second — a reconciliation warning, a failed row, an empty-result
 * notice — the singular query does not time out politely. It throws "Found
 * multiple elements", which reads like a flake and was chased as one across
 * three cycles before QA-003 found it was a wrong assumption rather than slow
 * hardware.
 *
 * The fix was `alertSaying(pattern)`: take `getAllByRole("alert")` and pick
 * the one whose text is the assertion's own subject. QA-004 swept it through
 * every page suite. This is the part that keeps it swept — a guard, not a
 * convention, because a convention is what the first eight call sites were.
 *
 * WHAT IS ALLOWED. `src/components/*.test.tsx` renders ONE component at a
 * time, so "the alert" is unambiguous there and the singular query is the
 * clearer thing to write; `foundation.test.tsx` keeps two on exactly that
 * ground. Everything else renders a page, and a page has more than one.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

function testFiles(dir = "src"): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return testFiles(path);
    return /\.test\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

/**
 * The singular alert query, built from parts and returned FRESH each call.
 *
 * Written as a literal, this file would match itself and force an allowlist;
 * and a shared /g/ regex carries `lastIndex` between `matchAll` and `test`.
 * The leading `.` is what keeps prose in a comment from matching — a mention
 * is not a call.
 */
const singularAlertQuery = () =>
  new RegExp("\\.(?:get|find)ByRole\\(\\s*[\"']alert[\"']", "g");

/** Single-component suites, where "the alert" means exactly one thing. */
const isSingleComponentSuite = (file: string) =>
  /^src[/\\]components[/\\][^/\\]+\.test\.tsx$/.test(file);

describe("no page suite asks for THE alert", () => {
  it("finds no singular alert query outside the single-component suites", () => {
    const offenders: string[] = [];
    for (const file of testFiles()) {
      if (isSingleComponentSuite(file)) continue;
      const hits = [...readFileSync(file, "utf8").matchAll(singularAlertQuery())];
      if (hits.length) offenders.push(`${file} (${hits.length})`);
    }
    expect(offenders).toEqual([]);
  });

  it("finds the sanctioned suite really does use one", () => {
    // The counterpart: the guard above must be matching something real, or it
    // would pass just as happily against a pattern that matches nothing.
    const foundation = join("src", "components", "foundation.test.tsx");
    expect(singularAlertQuery().test(readFileSync(foundation, "utf8"))).toBe(true);
  });
});
