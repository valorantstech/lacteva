#!/usr/bin/env node
// The marketing site on a phone, measured (WO-97 / owner decision D-45).
//
// READ-ONLY. Every public page at five phone widths; exits non-zero on ANY
// finding. Three checks, each of which was a real defect on live:
//   1. ZOOM — `innerWidth > device width`: at 360px every page laid out at
//      367px and the phone zoomed the whole site out.
//   2. THE MENU IS ON THE PHONE — the `<summary aria-label="Menu">` is the
//      only navigation below md; its right edge ended 7px off the screen.
//   3. THE PANEL STAYS INSIDE — open the menu; its panel and every link in it
//      lie within the viewport.
//
// Usage (from this directory, after `npm ci`):
//   SITE=https://lacteva.com node site.js
//   WIDTHS=320,360,375,390,412 CHROME=/usr/bin/google-chrome node site.js
const { chromium } = require("playwright-core");

const SITE = (process.env.SITE || "http://127.0.0.1:3100").replace(/\/$/, "");
const WIDTHS = (process.env.WIDTHS || "320,360,375,390,412").split(",").map((w) => Number(w.trim())).filter(Boolean);
const CHROME = process.env.CHROME || "/usr/bin/google-chrome";
// The public pages the sitemap publishes, plus /login (the customer's way
// in), which is deliberately a bare page without the site header — so it is
// measured for zoom only.
const ROUTES = ["/", "/product", "/solutions", "/pricing", "/company", "/request-demo", "/start-free-trial", "/privacy-policy", "/terms", "/login"];
const NO_HEADER = new Set(["/login"]);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const failures = [];
  let visits = 0;
  for (const width of WIDTHS) {
    const ctx = await browser.newContext({
      viewport: { width, height: 780 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true,
      userAgent: "Mozilla/5.0 (Linux; Android 14; moto g57) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36",
    });
    const page = await ctx.newPage();
    for (const route of ROUTES) {
      visits++;
      const findings = [];
      let status = 0;
      try {
        const resp = await page.goto(`${SITE}${route}`, { waitUntil: "networkidle", timeout: 60000 });
        status = resp ? resp.status() : 0;
        await page.waitForTimeout(400);
      } catch (e) { findings.push(`goto: ${String(e).slice(0, 100)}`); }
      if (status >= 400) findings.push(`HTTP ${status}`);
      const m = await page.evaluate((W) => {
        const vw = window.innerWidth;
        const menu = document.querySelector('summary[aria-label="Menu"]');
        const r = menu ? menu.getBoundingClientRect() : null;
        return { vw, zoomedOut: vw > W + 1, menu: !!menu, menuVisible: !!(r && r.width && r.height), menuRight: r ? Math.round(r.right) : null, menuLeft: r ? Math.round(r.left) : null };
      }, width).catch((e) => ({ evalError: String(e).slice(0, 100) }));
      if (m.zoomedOut) findings.push(`page is ${m.vw}px wide on a ${width}px phone (zoomed out)`);
      if (!m.menuVisible && !NO_HEADER.has(route)) findings.push("no visible Menu button");
      else if (m.menuRight > width + 1 || m.menuLeft < -1) findings.push(`Menu button off-screen [${m.menuLeft}→${m.menuRight}] on ${width}px`);
      if (m.menuVisible) {
        await page.locator('summary[aria-label="Menu"]').click().catch(() => {});
        await page.waitForTimeout(300);
        const panel = await page.evaluate((W) => {
          const details = document.querySelector('summary[aria-label="Menu"]')?.closest("details");
          if (!details || !details.open) return { open: false };
          const box = details.querySelector("div");
          const r = box ? box.getBoundingClientRect() : null;
          const links = [...details.querySelectorAll("a[href]")].map((a) => { const b = a.getBoundingClientRect(); return { t: a.innerText.trim(), l: Math.round(b.left), r: Math.round(b.right) }; });
          const out = links.filter((x) => x.r > W + 1 || x.l < -1).map((x) => `${x.t} [${x.l}→${x.r}]`);
          return { open: true, panelLeft: r ? Math.round(r.left) : null, panelRight: r ? Math.round(r.right) : null, links: links.length, out };
        }, width).catch(() => ({ open: false }));
        if (!panel.open) findings.push("the Menu did not open");
        else {
          if (panel.panelRight > width + 1 || panel.panelLeft < -1) findings.push(`menu panel outside the viewport [${panel.panelLeft}→${panel.panelRight}]`);
          if (panel.out.length) findings.push(`menu links off-screen: ${panel.out.join(", ")}`);
          if (panel.links < 5) findings.push(`menu holds only ${panel.links} links`);
        }
      }
      console.log(`${String(width).padStart(3)} ${route.padEnd(20)} ${findings.length ? "FAIL " + findings.join("; ") : "ok"}`);
      if (findings.length) failures.push({ width, route, findings });
    }
    await ctx.close();
  }
  await browser.close();
  console.log(`\nSUMMARY: ${visits} page visits at ${WIDTHS.join("/")}px — ${failures.length} with findings`);
  for (const f of failures) console.log(`  ${f.width} ${f.route}: ${f.findings.join("; ")}`);
  process.exit(failures.length ? 1 : 0);
})().catch((e) => { console.error("FATAL", e); process.exit(2); });
