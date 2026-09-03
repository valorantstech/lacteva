import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The Login button has to reach the product (WO-65 · LACTEVA-MARKETING-009).
 *
 * The owner opened lacteva.com, clicked Login, and was told: "The Lacteva
 * platform is a separate application. Its address is not configured in this
 * environment (NEXT_PUBLIC_PORTAL_URL)" — and offered a free trial. On the
 * product's own public site, a customer who wants to SIGN IN being told to
 * SIGN UP is the worst dead end there is.
 *
 * WHY IT COULD NOT BE FIXED IN COMPOSE. `NEXT_PUBLIC_*` is inlined into the
 * bundle by `next build`; the running server never reads it. So the value has
 * to be present when the IMAGE is built, and a deployment that adds it as a
 * runtime environment variable changes nothing at all while looking like a
 * fix. That is the trap this file exists to keep shut.
 *
 * These read the build inputs rather than the running site, because that is
 * where the defect lived and where a future rebuild would lose it again: a
 * Dockerfile that forgets the ARG, or a workflow that stops passing it, both
 * produce a green build and a broken Login button.
 */
const ROOT = join(__dirname, "..", "..");
const REPO = join(ROOT, "..", "..");
const dockerfile = readFileSync(join(ROOT, "Dockerfile"), "utf8");
const workflow = readFileSync(join(REPO, ".github/workflows/images.yml"), "utf8");

/** The Dockerfile with comments stripped — a guard must not match its own
 *  explanation, which this repository has been caught by three times. */
const instructions = dockerfile
  .split("\n")
  .filter((line) => !line.trimStart().startsWith("#"))
  .join("\n");

describe("the portal URL survives a rebuild", () => {
  it("is a build ARG, because next inlines it and compose cannot", () => {
    expect(instructions).toMatch(/^ARG NEXT_PUBLIC_PORTAL_URL/m);
    expect(instructions).toMatch(/^ENV NEXT_PUBLIC_PORTAL_URL=\$\{NEXT_PUBLIC_PORTAL_URL\}/m);
  });

  it("is set BEFORE the build, or the build cannot see it", () => {
    // The one ordering that matters: an ENV after `npm run build` is an ENV
    // the bundle was compiled without.
    const env = instructions.indexOf("ENV NEXT_PUBLIC_PORTAL_URL");
    const build = instructions.indexOf("RUN npm run build");
    expect(env).toBeGreaterThan(-1);
    expect(build).toBeGreaterThan(-1);
    expect(env).toBeLessThan(build);
  });

  it("defaults to empty, so a local build never inherits somebody's portal", () => {
    // An unset build gets the explanatory /login page. Defaulting to the live
    // portal would mean a developer's local site silently hands visitors to
    // production.
    expect(instructions).toMatch(/^ARG NEXT_PUBLIC_PORTAL_URL=""\s*$/m);
  });

  it("is passed by the workflow that builds the published image", () => {
    // The Dockerfile can only accept the value; something has to supply it,
    // and the published image is the one the public site runs.
    const marketing = workflow.slice(
      workflow.indexOf("- name: marketing-site"),
      workflow.indexOf("- name: admin-portal"),
    );
    expect(marketing).toContain("NEXT_PUBLIC_PORTAL_URL=");
    const value = /NEXT_PUBLIC_PORTAL_URL=(\S+)/.exec(marketing)?.[1] ?? "";
    expect(value, "the marketing build ships without a portal URL").not.toBe("");
    expect(value, "the portal is reached over https or not at all").toMatch(/^https:\/\//);
  });

  it("points at a host this platform actually serves", () => {
    // WO-63 fixed the URL map to four names. A portal URL that is not one of
    // them is a Login button pointing at nothing — the same dead end wearing
    // a different address.
    const value = /NEXT_PUBLIC_PORTAL_URL=(\S+)/.exec(workflow)?.[1] ?? "";
    expect(value).toBe("https://app.lacteva.com");
  });

  it("still explains itself when there is genuinely no portal configured", () => {
    // The fallback page is correct and stays: local development has no
    // portal, and a dead redirect would be worse than an explanation. What
    // was wrong was shipping that page to the public site.
    const page = readFileSync(join(__dirname, "login", "page.tsx"), "utf8");
    expect(page).toContain("process.env.NEXT_PUBLIC_PORTAL_URL");
    expect(page).not.toMatch(/https:\/\/app\.lacteva\.com/);
  });
});
