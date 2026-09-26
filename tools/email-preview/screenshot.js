#!/usr/bin/env node
// Every email, as a mail client would show it (WO-105 §7).
//
// Renders each committed HTML preview at 600px (a laptop) and 375px (a phone)
// in headless Chrome and writes the PNGs beside it, so a reviewer SEES the
// email in the diff. The HTML files come from render_previews.py.
//
//   node tools/email-preview/screenshot.js
const path = require("path");
const fs = require("fs");
const { chromium } = require(path.join(__dirname, "..", "mobile-audit", "node_modules", "playwright-core"));

const REPO = path.join(__dirname, "..", "..");
const DIR = path.join(REPO, "services/platform-core/src/platform_core/modules/notification/previews");
const CHROME = process.env.CHROME || "/usr/bin/google-chrome";
const WIDTHS = [600, 375];

(async () => {
  const files = fs.readdirSync(DIR).filter((f) => f.endsWith(".html")).sort();
  if (!files.length) throw new Error(`no previews in ${DIR} — run render_previews.py first`);
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const logoDir = path.join(REPO, "apps/marketing-site/public/email");
  for (const file of files) {
    let html = fs.readFileSync(path.join(DIR, file), "utf8");
    // The logo is fetched from lacteva.com in a real client; the proof runs
    // offline, so the committed asset stands in for the published one — as a
    // data URI, because Chrome will not load file:// into an in-memory page.
    // (The EMAIL never carries a data URI: Gmail strips them.)
    html = html.replace(/https:\/\/lacteva\.com\/email\/([A-Za-z0-9@._-]+\.png)/g, (_m, name) => {
      const bytes = fs.readFileSync(path.join(logoDir, name));
      return "data:image/png;base64," + bytes.toString("base64");
    });
    for (const width of WIDTHS) {
      const page = await browser.newPage({ viewport: { width, height: 800 }, deviceScaleFactor: 1 });
      await page.setContent(html, { waitUntil: "load" });
      const out = path.join(DIR, file.replace(/\.html$/, `.${width}.png`));
      await page.screenshot({ path: out, fullPage: true });
      await page.close();
      console.log(`wrote ${path.relative(REPO, out)}`);
    }
  }
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
