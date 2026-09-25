/**
 * The site's own address survives a rebuild (WO-76).
 *
 * `layout.tsx`, `sitemap.ts` and `robots.ts` read LACTEVA_SITE_URL at BUILD
 * time, so it has to be a Dockerfile ARG passed by the images workflow —
 * exactly the shape `portal-url.test.ts` guards for the portal URL, and
 * the defect it missed by one variable: for three weeks the live site told
 * Google and WhatsApp that it lived at lacteva.example, a domain that does
 * not resolve, and a shared link showed a bare grey card. The guard reads
 * the build inputs, comments stripped, because a Dockerfile that only
 * mentions the variable in a comment builds the same broken image.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..", "..");
const REPO = join(ROOT, "..", "..");
const dockerfile = readFileSync(join(ROOT, "Dockerfile"), "utf8");
const workflow = readFileSync(join(REPO, ".github/workflows/images.yml"), "utf8");
const instructions = dockerfile
  .split("\n")
  .filter((line) => !line.trimStart().startsWith("#"))
  .join("\n");

describe("the site URL survives a rebuild", () => {
  it("is a build ARG, set BEFORE the build, defaulting to empty", () => {
    expect(instructions).toMatch(/^ARG LACTEVA_SITE_URL=""\s*$/m);
    expect(instructions).toMatch(/^ENV LACTEVA_SITE_URL=\$\{LACTEVA_SITE_URL\}/m);
    const env = instructions.indexOf("ENV LACTEVA_SITE_URL");
    const build = instructions.indexOf("RUN npm run build");
    expect(env).toBeGreaterThan(-1);
    expect(env).toBeLessThan(build);
  });

  it("is passed by the workflow that builds the published image, and is the real domain", () => {
    const marketing = workflow.slice(
      workflow.indexOf("- name: marketing-site"),
      workflow.indexOf("- name: admin-portal"),
    );
    const value = /LACTEVA_SITE_URL=(\S+)/.exec(marketing)?.[1] ?? "";
    expect(value).toBe("https://lacteva.com");
  });

  it("falls back on an EMPTY value too, so the ARG's default cannot crash the build", () => {
    for (const file of ["app/layout.tsx", "app/sitemap.ts", "app/robots.ts"]) {
      const src = readFileSync(join(ROOT, "src", file), "utf8");
      expect(src, file).toContain('process.env.LACTEVA_SITE_URL || "https://lacteva.example"');
      expect(src, file).not.toContain("LACTEVA_SITE_URL ??");
    }
  });

  it("publishes the tags WhatsApp reads: og:url on every page, and og:locale", () => {
    const layout = readFileSync(join(ROOT, "src/app/layout.tsx"), "utf8");
    expect(layout).toMatch(/openGraph:\s*\{[^}]*url:\s*"\/"/);
    expect(layout).toMatch(/locale:\s*"en_IN"/);
    // Every page that names its canonical names the same og:url.
    const pages: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const p = join(dir, name);
        if (statSync(p).isDirectory()) walk(p);
        else if (name === "page.tsx") pages.push(p);
      }
    };
    walk(join(ROOT, "src/app"));
    let checked = 0;
    for (const page of pages) {
      const src = readFileSync(page, "utf8");
      const canonical = /alternates:\s*\{\s*canonical:\s*"([^"]+)"/.exec(src)?.[1];
      if (!canonical) continue;
      const og = /openGraph:\s*\{\s*url:\s*"([^"]+)"/.exec(src)?.[1];
      expect(og, `${page} names a canonical but no og:url`).toBe(canonical);
      checked++;
    }
    expect(checked).toBeGreaterThanOrEqual(6);
  });
});
