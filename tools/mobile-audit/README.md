# Mobile audit — the portal on a phone, measured

Owner decision **D-45 (2026-09-26)**: every portal page works on phones 320–412px
wide. This is the check that makes that a rule rather than a memory: it visits
every page the signed-in menu offers (plus the detail pages), under mobile
emulation, and **exits non-zero on any finding**.

What it checks, and why each check exists — every one found a real defect on
live before it was written:

| Check | The defect it caught |
| --- | --- |
| `innerWidth > device width` (the page zoomed out) | `/customers` was 376px on a 360px phone: a header row of buttons that did not wrap. The naive `scrollWidth > innerWidth` check passes falsely, because mobile Chrome zooms out and `innerWidth` grows with it. |
| On the seven card pages (`/billing`, `/receivables`, `/deliveries`, `/routes`, `/admin/users`, a bill, a customer): no cards, or any action button off the right edge | `/billing` hid *Amount due* and *Send on WhatsApp*; `/admin/users` hid every button, 1,100px to the right. |
| Any other wide table: it may scroll, but it must carry the scroll cue (`ScrollHint`); hidden columns on a cued table are printed, not failed | Clipped columns read as missing. |
| An input under 16px | iOS Safari zooms on every focused field. |
| Broken pages, HTTP ≥ 400 | — |

Console errors are reported, not failed on.

## Running it

It needs a Chrome on the machine (`CHROME`, default `/usr/bin/google-chrome` —
`playwright-core` drives an installed browser and downloads none; on a runner
without one, `npx playwright install chromium` and point `CHROME` at it) and a
portal to point at. It never submits a form.

```bash
cd tools/mobile-audit && npm ci
BASE=https://app.lacteva.com EMAIL=<a manager login> PASSWORD=<its password> node audit.js
# Options: WIDTHS=320,360,412  CHROME=/usr/bin/google-chrome  SHOP_TENANT=<org uuid>  OUT=./out
```

Against a local build: run the platform on SQLite with the India demo seeded
(`infra/demo/seed_demo.py seed india`, twenty-odd minutes), build the portal
and serve its **standalone** output with its static files copied beside it —
without that copy the server answers without a stylesheet and every input
measures 13px, which is not a finding:

```bash
cd apps/admin-portal && npm run build
cp -r .next/static .next/standalone/.next/static && cp -r public .next/standalone/public
cd .next/standalone && PORT=3000 HOSTNAME=localhost LACTEVA_API_URL=http://127.0.0.1:8000 node server.js
# then, from tools/mobile-audit:  BASE=http://localhost:3000 node audit.js
```

`localhost`, not `127.0.0.1`: the production build sets its cookies `Secure`,
and Chrome honours that over plain http only for `localhost`.

## Where it runs

**A post-deploy step, documented in DEPLOYMENT.md §3, run by the deployer
against production** — not a CI job. The reason: the check needs a seeded
full stack (PostgreSQL, the API, the portal, the demo tenant) and a Chrome, and
seeding the demo takes over twenty minutes on SQLite; a CI job of that weight
would be skipped the first time it was slow, and a skipped proof is worse than
an absent one. Running it against the deployed site after every deploy costs
two minutes and measures the thing that matters. When the e2e harness
(`infra/e2e/run-e2e.sh`) grows a Chrome, this is the script it should call.

## The marketing site (WO-97)

`site.js` does the same for lacteva.com: every public page at 320, 360, 375,
390 and 412px — no page zoomed out, the Menu button (the only navigation on a
phone) fully on screen, and its panel and every link inside the viewport.

```bash
SITE=https://lacteva.com node site.js
```

Locally: build the site, serve its standalone output with `.next/static` and
`public` copied beside it (as for the portal above) on port 3100, and run with
the default `SITE=http://127.0.0.1:3100`.
