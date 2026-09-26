#!/usr/bin/env node
// The Lacteva lockup as an EMAIL can carry it (WO-105 · LACTEVA-NOTIFY-003).
//
// Gmail does not render SVG, strips data: URIs, and its dark mode turns navy
// on transparency into navy on black — so the mark, the wordmark and the
// tagline are rasterised ONCE, at 2x, onto an opaque white background, and
// committed as a versioned static asset the marketing site serves at
// https://lacteva.com/email/lacteva-logo-v1@2x.png. A new version is a new
// filename, never an overwrite: mail clients and Gmail's image proxy cache
// aggressively.
//
// The artwork is the generated lockup in tools/brand (the owner's letterforms
// traced by trace_wordmark.py), which already carries the tagline between its
// rules; nothing is drawn here.
//
//   node tools/email-preview/render_logo.js            # writes the PNG
//   CHROME=/usr/bin/google-chrome node tools/email-preview/render_logo.js
const path = require("path");
const fs = require("fs");
const { chromium } = require(path.join(__dirname, "..", "mobile-audit", "node_modules", "playwright-core"));

const REPO = path.join(__dirname, "..", "..");
const OUT = path.join(REPO, "apps/marketing-site/public/email/lacteva-logo-v1@2x.png");
const CHROME = process.env.CHROME || "/usr/bin/google-chrome";
const WIDTH = 180; // CSS px; the PNG is 2x this
const lockup = fs.readFileSync(path.join(REPO, "tools/brand/lacteva-lockup.svg"), "utf8");

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{margin:0;padding:0;background:#FFFFFF;}
  #logo{display:inline-block;width:${WIDTH}px;padding:0;background:#FFFFFF;}
  #logo svg{display:block;width:${WIDTH}px;height:auto;}
</style></head><body><div id="logo">${lockup}</div></body></html>`;

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: 400, height: 200 }, deviceScaleFactor: 2 });
  await page.setContent(html);
  const el = await page.$("#logo");
  await el.screenshot({ path: OUT, omitBackground: false });
  const box = await el.boundingBox();
  await browser.close();
  console.log(`wrote ${path.relative(REPO, OUT)} for a ${Math.round(box.width)}x${Math.round(box.height)} CSS px display`);
})().catch((e) => { console.error(e); process.exit(1); });
