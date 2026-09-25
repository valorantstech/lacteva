#!/usr/bin/env node
// The portal on a phone, measured (WO-96 / owner decision D-45).
//
// READ-ONLY: visits pages, measures, never submits a form. Exits non-zero on
// ANY finding, so it can gate a deploy. Four checks, each of which found a
// real defect on live before it was written:
//
//   1. ZOOM. A page wider than the phone does not overflow — mobile Chrome
//      zooms the whole page out to fit it, and `innerWidth` grows with it,
//      so "scrollWidth > innerWidth" passes falsely. The right test, under
//      mobile emulation, is `innerWidth > device width`. (/customers was
//      376px on a 360px phone through a header row that did not wrap.)
//   2. MONEY AND ACTIONS off the right edge of a table: the columns pushed
//      out of view at phone width were exactly the amounts and the buttons.
//      On the card pages there must be no table at all below `md`; on every
//      other page, a table that scrolls must carry the scroll cue.
//   3. INPUTS under 16px: iOS Safari zooms on focus, and the person pinches
//      back out after every field.
//   4. BROKEN pages and console errors.
//
// Usage (from this directory, after `npm ci`):
//   BASE=https://app.lacteva.com EMAIL=… PASSWORD=… node audit.js
//   WIDTHS=320,360,412 CHROME=/usr/bin/google-chrome node audit.js
//   SHOP_TENANT=<org uuid> — also browse that tenant's menu as the platform admin.
//
// Credentials come from the environment and are never written anywhere.
const { chromium } = require("playwright-core");
const fs = require("fs");
const path = require("path");

const BASE = (process.env.BASE || "http://127.0.0.1:3000").replace(/\/$/, "");
const EMAIL = process.env.EMAIL || "manager@lacteva-india.example.com";
const PASSWORD = process.env.PASSWORD || "Demo-Lacteva-2026!";
const SHOP_TENANT = process.env.SHOP_TENANT || "";
const WIDTHS = (process.env.WIDTHS || "320,360").split(",").map((w) => Number(w.trim())).filter(Boolean);
const CHROME = process.env.CHROME || "/usr/bin/google-chrome";
const OUT = process.env.OUT || path.join(__dirname, "out");
/** The seven pages whose rows become cards below `md` (WO-96 §1). */
const CARD_PAGES = ["/billing", "/receivables", "/deliveries", "/routes", "/admin/users"];
const CARD_DETAIL = [["/billing", "/invoices/"], ["/customers", "/customers/"]];
fs.mkdirSync(OUT, { recursive: true });

const MEASURE = (deviceWidth) => {
  const vw = window.innerWidth;
  const zoomedOut = vw > deviceWidth + 1;
  const tables = [...document.querySelectorAll("table")].map((tb) => {
    const heads = [...tb.querySelectorAll("thead th")].map((th) => ({ t: th.innerText.trim(), r: th.getBoundingClientRect().right }));
    const hiddenCols = heads.filter((h) => h.r > vw + 2).map((h) => h.t || "(unnamed)");
    const hiddenActions = [...new Set([...tb.querySelectorAll("tbody button, tbody a[href]")]
      .filter((e) => e.getBoundingClientRect().right > vw + 2)
      .map((e) => (e.innerText || e.getAttribute("aria-label") || "(icon)").trim()))];
    let sc = tb.parentElement;
    while (sc && sc !== document.body && !(sc.scrollWidth > sc.clientWidth + 2)) sc = sc.parentElement;
    const scrolls = !!(sc && sc !== document.body);
    const hint = scrolls ? sc.closest("[data-scroll-hint]") : null;
    const cued = scrolls ? !!(hint && hint.getAttribute("data-more-right") === "true") : null;
    return { cols: heads.length, hiddenCols, hiddenActions, scrolls, cued };
  });
  const cards = document.querySelectorAll('[data-testid="row-card"]').length;
  // What pushed the page past the phone: the outermost elements whose right
  // edge lies beyond the device width and that no scroller contains.
  const inScroller = (el) => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) { const ox = getComputedStyle(p).overflowX; if ((ox === "auto" || ox === "scroll" || ox === "hidden" || ox === "clip") && p.getBoundingClientRect().right <= deviceWidth + 1) return true; } return false; };
  const wide = new Set();
  if (zoomedOut) for (const el of document.querySelectorAll("body *")) { const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue; const st = getComputedStyle(el); if (st.display === "none" || st.visibility === "hidden" || st.position === "fixed") continue; if (r.right > deviceWidth + 2 && !inScroller(el)) wide.add(el); }
  const offenders = [];
  for (const el of wide) { let p = el.parentElement, nested = false; while (p) { if (wide.has(p)) { nested = true; break; } p = p.parentElement; } if (!nested) { const r = el.getBoundingClientRect(); offenders.push(`${el.tagName.toLowerCase()}.${String(el.className).split(/\s+/).slice(0, 3).join(".")} [${Math.round(r.left)}→${Math.round(r.right)}] "${(el.innerText || "").trim().replace(/\s+/g, " ").slice(0, 40)}"`); } }
  const smallInputs = [...document.querySelectorAll("input:not([type=checkbox]):not([type=radio]):not([type=hidden]), select, textarea")]
    .filter((e) => e.getClientRects().length && parseFloat(getComputedStyle(e).fontSize) < 16)
    .map((e) => `${e.tagName.toLowerCase()}#${e.id || e.name || "?"}=${getComputedStyle(e).fontSize}`);
  const body = document.body.innerText;
  const broken = /Application error|Unhandled Runtime Error|Something went wrong|This page could not be found|Internal Server Error/i.test(body);
  return { vw, zoomedOut, offenders: offenders.slice(0, 5), tables, cards, smallInputs, broken, title: document.title };
};

async function login(page) {
  // A dev server compiles the page on first hit and the form can submit
  // natively (to /login?) before React has hydrated; a second attempt after
  // a beat is the honest fix, and a production build never needs it.
  for (let attempt = 1; attempt <= 3; attempt++) {
    await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
    await page.waitForTimeout(attempt * 1000);
    await page.getByLabel("Email").fill(EMAIL);
    await page.getByLabel("Password").fill(PASSWORD);
    try {
      await Promise.all([
        page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20000 }),
        page.getByRole("button", { name: /sign in/i }).click(),
      ]);
      await page.waitForLoadState("networkidle");
      return;
    } catch (e) {
      if (attempt === 3) throw new Error(`could not sign in as ${EMAIL} at ${BASE}: ${String(e).slice(0, 120)}`);
    }
  }
}

async function menuLinks(page) {
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  const opener = page.getByRole("button", { name: "Open navigation" });
  if (!(await opener.isVisible().catch(() => false))) return [];
  await opener.click();
  await page.waitForTimeout(400);
  const links = await page.evaluate(() =>
    [...document.querySelectorAll("nav a[href], [role=dialog] a[href], aside a[href]")]
      .filter((a) => { const r = a.getBoundingClientRect(); return r.width && r.height; })
      .map((a) => a.getAttribute("href")));
  await page.keyboard.press("Escape").catch(() => {});
  return [...new Set(links.filter((h) => h && h.startsWith("/")))];
}

async function firstDetailLink(page, listRoute, prefix) {
  await page.goto(`${BASE}${listRoute}`, { waitUntil: "networkidle" }).catch(() => {});
  await page.waitForTimeout(400);
  return page.evaluate((pre) => {
    const a = [...document.querySelectorAll("a[href]")].map((a) => a.getAttribute("href"))
      .find((h) => h && h.startsWith(pre) && h.length > pre.length + 8 && !h.includes("import") && !h.includes("month"));
    return a || null;
  }, prefix);
}

async function visit(page, width, label, route, results) {
  const errors = [];
  const onConsole = (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 160)); };
  const onPageErr = (e) => errors.push(`pageerror: ${String(e).slice(0, 160)}`);
  page.on("console", onConsole); page.on("pageerror", onPageErr);
  let status = 0;
  try {
    const resp = await page.goto(`${BASE}${route}`, { waitUntil: "networkidle", timeout: 60000 });
    status = resp ? resp.status() : 0;
    await page.waitForTimeout(700);
  } catch (e) { errors.push(`goto: ${String(e).slice(0, 120)}`); }
  let m = {};
  try { m = await page.evaluate(MEASURE, width); } catch (e) { m = { evalError: String(e).slice(0, 120) }; }
  page.off("console", onConsole); page.off("pageerror", onPageErr);
  const isCardPage = CARD_PAGES.includes(route) || CARD_DETAIL.some(([, pre]) => route.startsWith(pre) && route.length > pre.length);
  const findings = [];
  if (m.zoomedOut) findings.push(`page is ${m.vw}px wide on a ${width}px phone (zoomed out): ${(m.offenders || []).join(" | ") || "?"}`);
  if (m.broken) findings.push("page is broken");
  if (status >= 400) findings.push(`HTTP ${status}`);
  // D-45's acceptance, exactly: the seven card pages show no money or action
  // off-screen (their lists are cards, so a table there with hidden columns
  // or buttons is the regression); every OTHER wide table may stay a table
  // as long as its scroller carries the cue. Hidden columns on a cued table
  // are reported for the eye, not failed on.
  const offCols = (m.tables || []).flatMap((t) => t.hiddenCols);
  const offActs = (m.tables || []).flatMap((t) => t.hiddenActions);
  if (isCardPage && (m.cards || 0) === 0 && (m.tables || []).length) findings.push("card page shows a table and no cards");
  if (isCardPage && offActs.length) findings.push(`actions off-screen on a card page: ${offActs.join(", ")}`);
  const uncued = (m.tables || []).filter((t) => t.scrolls && !t.cued).length;
  if (uncued) findings.push(`${uncued} scrolling table(s) without the scroll cue`);
  if (!isCardPage && offActs.length && uncued) findings.push(`actions off-screen without a cue: ${offActs.join(", ")}`);
  if ((m.smallInputs || []).length) findings.push(`inputs under 16px: ${m.smallInputs.join(", ")}`);
  const notes = offCols.length && !findings.length ? ` (cued table scrolls for: ${offCols.slice(0, 6).join(", ")}${offCols.length > 6 ? "…" : ""})` : "";
  // Console errors are reported, not failed on: a blocked third-party asset
  // is not a layout regression. The findings above are.
  const row = { width, label, route, status, ...m, findings, errors: [...new Set(errors)].slice(0, 5) };
  results.push(row);
  console.log(`${String(width).padStart(3)} ${label.padEnd(6)} ${route.padEnd(30)} ${findings.length ? "FAIL " + findings.join("; ") : `ok (${m.cards || 0} cards)${notes}`}`);
  return row;
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const results = [];
  for (const width of WIDTHS) {
    const device = {
      viewport: { width, height: 780 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true,
      userAgent: "Mozilla/5.0 (Linux; Android 14; moto g57) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36",
    };
    // Public pages, as a stranger.
    {
      const ctx = await browser.newContext(device); const page = await ctx.newPage();
      for (const r of ["/login", "/reset-password", "/accept-invitation", "/confirm-email", "/bill/not-a-real-token"]) await visit(page, width, "public", r, results);
      await ctx.close();
    }
    // The signed-in session: every page the menu offers, plus the detail pages.
    {
      const ctx = await browser.newContext(device); const page = await ctx.newPage();
      await login(page);
      if (SHOP_TENANT) {
        const set = await page.request.post(`${BASE}/api/auth/tenant`, { data: { tenant_id: SHOP_TENANT } });
        console.log(`acting in ${SHOP_TENANT}: ${set.status()}`);
      }
      const routes = new Set(await menuLinks(page));
      for (const r of ["/customers/import", "/suppliers/import", "/admin/products", "/notifications", "/deliveries/month", "/admin/settings", "/admin/users", "/admin/organizations"]) routes.add(r);
      for (const r of routes) await visit(page, width, "app", r, results);
      for (const [list, pre] of [["/customers", "/customers/"], ["/billing", "/invoices/"], ["/rate-cards", "/rate-cards/"], ["/centers", "/centers/"], ["/payments", "/payments/"], ["/settlements", "/settlements/"], ["/suppliers", "/suppliers/"], ["/transactions", "/transactions/"]]) {
        if (!routes.has(list)) continue;
        const href = await firstDetailLink(page, list, pre);
        if (href) await visit(page, width, "app", href, results);
      }
      await ctx.close();
    }
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify(results, null, 1));
  const failed = results.filter((r) => r.findings.length);
  const errored = results.filter((r) => r.errors.length);
  console.log(`\nSUMMARY: ${results.length} page visits at ${WIDTHS.join("/")}px — ${failed.length} with findings, ${errored.length} with console errors (reported, not failed)`);
  for (const r of failed) console.log(`  ${r.width} ${r.route}: ${r.findings.join("; ")}`);
  process.exit(failed.length ? 1 : 0);
})().catch((e) => { console.error("FATAL", e); process.exit(2); });
