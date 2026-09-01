---
id: LACTEVA-ONBOARDING-PLAYBOOK
title: Onboarding Playbook — from signed dairy to first parchi
type: reference
status: Draft
version: "0.1"
owner: Product & Platform Engineering
created: 2026-09-01
last-updated: 2026-09-01
related: [LACTEVA-DEMO-ACCOUNTS, LACTEVA-GO-LIVE-READINESS, LACTEVA-HARDWARE-INTEGRATION-SPEC]
baseline: ARCH-BASELINE-V1
---


Audience: the sales / customer-success person onboarding a new dairy.
Everything here is the product as it exists at dev.phoenixsoft.in (commit 0c752f0+);
the two screens marked **[Batch B7]** are landing now.

## 0 · What sales collects from the dairy (before any login exists)
The information-request pack (docs/20-business) asks for exactly this:
1. Dairy name, address, GST/FSSAI details (for records; not blocking).
2. List of collection centres (name, address, morning/evening shift times).
3. The rate chart they pay farmers by (FAT bands, and SNF if they use it).
4. Farmer list (name, code, phone, centre) — a spreadsheet is enough.
5. Customer/outlet list if they sell milk onward (optional at start).
6. Their machines, per centre: analyzer make/model, scale make/model,
   printer make/model — photos of the rear panels are gold.
7. Who plays which role: owner, centre managers, counter operators,
   finance person, driver(s).

## 1 · Provisioning (Lacteva's side, ~10 minutes)
Done by the Lacteva platform administrator (Phoenix staff), in the portal:
1. Create the Organization (name, slug, country) — currency, timezone and
   language resolve from the country automatically. A 30-day trial starts;
   activation beyond trial is a Lacteva act (no self-serve payment yet).
2. Invite the dairy owner as tenant admin: /admin/users → Invite →
   role "tenant-admin". The owner receives a real email, opens the accept
   link, sets their password. **Login #1 exists.**

## 2 · Dairy setup (the owner in the portal, guided by sales, ~1 hour)
Portal: https://dev.phoenixsoft.in — same credentials work in the mobile app.
1. **Centres**: /centers → create each collection centre with shift hours.
2. **Staff logins** — created by the OWNER via /admin/users → Invite.
   Each person gets an email invitation; accepting sets their password.
   One set of credentials works on portal AND mobile app — the app shows
   each person only their own experience.

   | Role | Where they work | Typical count |
   |---|---|---|
   | tenant-admin (owner) | Portal (everything) + app manager home | 1 |
   | CENTRE_MANAGER | Portal (their centre) + app; **holds rate-override** | 1 per centre |
   | COLLECTION_OPERATOR | Mobile app only (capture) | 1–2 per centre |
   | FINANCE_OFFICER / MANAGER | Portal (settlements, payments) | 0–1 |
   | SALES_OFFICER | Portal sales side + app delivery round | 0–1 |
   | DRIVER | Mobile app (own runs only) | per van |
   | AUDITOR / viewer | Portal read-only | optional |

   Farmers get **no login** — they are records who receive a parchi and a
   notification. Customers (shops/households) can get a read-only app
   login when created under /customers.
3. **Machines and printer** — two halves:
   a. **Register** each instrument in the portal on the centre's page
      (/centers/{centre} → Devices card): category (scale / milk analyzer /
      printer), make, model, serial. **[Batch B7]** A registered scale is
      part of centre readiness; analyzer and printer are advisory.
   b. **Connect** on the counter handset: app → Instruments → pick the
      registered device → enter how the phone reaches it (today: the
      network bridge's address; Bluetooth/USB arrive with bench-proven
      hardware) → Test read shows live values without capturing.
      Printer likewise, with a test print. **[Batch B7]**
   If a machine is down or absent, nothing blocks: the operator types the
   reading and the record says so — provenance is kept on every value.
4. **Rate card** — created by the owner or centre manager:
   /rate-cards → New → add the FAT band matrix (and SNF chart if used) →
   the card moves draft → under review → approved → **published**.
   Collections price only from published cards; a collection taken before
   the card covers it is held "Rate pending" and resolved by an authorized
   reprice once the right card is published — never silently priced.
5. **Farmers** — /suppliers → add individually, or CSV import for the
   whole list (name, code, phone, centre). The farmer's code is what the
   operator types (or scans) at the counter.
6. **Customers** (optional now): /customers, with routes and a driver if
   they deliver.

## 3 · The counter, every morning (the operator on the handset)
1. Operator signs in (their invitation credentials). Home shows their
   centre, the shift, and "Collect milk".
2. Farmer arrives → operator enters/scans the farmer code → farmer's name
   confirms identity → operator picks the **milk type** (cow, buffalo,
   goat, sheep, mixed…). Each type prices from its own rate card.
3. **Quality**: with a connected analyzer — "Read from analyzer" fills
   FAT, SNF, CLR, density, temperature straight from the machine; the
   record stores which device and a fingerprint of its exact output.
   Without one, the operator types the values. Editing any machine value
   marks the whole reading operator-entered — one reading, one author.
4. **Weight**: same — read from the scale, or type gross/tare.
5. **Rate appears automatically** from the published card for that
   centre/product/date and the measured FAT.
6. **Rate edit (owner's control)**: a centre manager or the owner may tap
   "Edit rate" — a reason is mandatory, and both the card rate and the
   edited rate go on the parchi and every record with who/when/why.
   Operators do not see this control at all.
7. **Complete** → the parchi (SLP-…) is minted: quantity, FAT/SNF, rate,
   amount. The farmer is notified on channels the dairy has (email today;
   SMS/WhatsApp when a provider is contracted). **Print** produces the
   thermal receipt where a printer is connected; Share sends the parchi
   (including the Hindi copy) by WhatsApp/anything, always available.
8. No internet? Everything queues on the handset and syncs exactly-once
   when the network returns; queued collections show honestly as pending,
   and are priced when they reach the platform.

## 4 · What the owner sees
- **Portal dashboard**: today's collection litres — total AND by milk
  type — farmer count, average FAT, settlement position, per centre.
- **The Milk Day Book** (per centre, per day, per type): collected ·
  sold to customers · dispatched onward (to a chilling centre, plant or
  another dairy — recorded with destination and who sent it) · remainder.
  This is a flow ledger: it accounts for every litre without pretending
  to meter tanks.
- **/transactions**: every collection with its provenance (machine vs
  typed), any rate edit with who/why, rate-pending items to resolve.
- **Reports**: daily summaries, payables by currency, per-farmer books.
- **Settlements**: run a period → finalize → pay → receipts; every rupee
  traceable back to individual parchis.
- **Mobile manager home**: the day at a glance while standing at the dock.
- Every farmer-facing number the owner sees equals what the farmer's
  parchi says — one source, no reconciliation.

## 5 · If something goes wrong (quick answers for the counter)
| Symptom | Answer |
|---|---|
| Analyzer/scale unreachable | Type the reading — collection never blocks; record is flagged operator-entered |
| Printer dead | Share the parchi (WhatsApp/SMS app) — the print is a convenience, the parchi is the record |
| No internet | Keep collecting — the queue syncs when the network returns |
| Wrong rate on screen | Check the published card's dates/bands; if the card was missing, publish it and use Resolve (reprice) on the pending items |
| Operator locked out | Forgot password on the sign-in screen — a reset code arrives by email |
| New staff member | Owner invites from /admin/users; never share logins |

## 6 · Not yet, and said honestly
SMS/WhatsApp to farmers (needs a contracted provider) · per-model analyzer
drivers and Bluetooth/USB connections (bench hardware first — D-16) ·
physical print proof (same bench) · AI insights (after real pilot data).
The product never claims these before they exist; neither should sales.

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2026-09-01 | Product & Platform Engineering | Committed into the governed tree from the Master workspace (BATCH B7.2 rider). Content unchanged apart from front matter and this log. |
