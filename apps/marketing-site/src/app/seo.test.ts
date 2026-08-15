import { describe, expect, it } from "vitest";
import robots from "./robots";
import sitemap from "./sitemap";

/**
 * MKT-004F: the indexing surface, pinned. The sitemap lists exactly the
 * public marketing pages; hand-over and machine routes stay out and are
 * blocked in robots.
 */
describe("indexing surface", () => {
  it("sitemap lists only public marketing pages", () => {
    const urls = sitemap().map((entry) => new URL(entry.url).pathname);
    expect(urls).toContain("/");
    expect(urls).toContain("/product");
    expect(urls).toContain("/solutions");
    expect(urls).toContain("/pricing");
    expect(urls).toContain("/privacy-policy");
    expect(urls).toContain("/terms");
    expect(urls).not.toContain("/login");
    expect(urls).not.toContain("/editions");
    expect(urls).not.toContain("/why-lacteva");
    for (const url of urls) {
      expect(url).not.toMatch(/^\/api/);
    }
  });

  it("robots allows marketing pages and blocks api + login", () => {
    const config = robots();
    const rules = Array.isArray(config.rules) ? config.rules[0] : config.rules;
    expect(rules?.allow).toBe("/");
    expect(rules?.disallow).toEqual(["/api/", "/login"]);
    expect(config.sitemap).toMatch(/\/sitemap\.xml$/);
  });
});
