---
id: LACTEVA-DAIRY-ONBOARDING-INFORMATION-REQUEST-PACK
title: Dairy Onboarding Information Request Pack
type: reference
status: Approved
version: "1.0"
owner: Lacteva Onboarding
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-P0-PILOT-008-REAL-DAIRY-ONBOARDING-READINESS, LACTEVA-PILOT-ONBOARDING-PACK, LACTEVA-COMMERCIAL-MODEL-AND-PACKAGING, LACTEVA-REGULATORY-APPLICABILITY-AUDIT]
baseline: ARCH-BASELINE-V1
---

# Lacteva — Dairy Onboarding Information Request Pack

### Information Required for Lacteva Pilot & Production Onboarding · Version 1.0

---

## Welcome

Thank you for choosing to run a controlled pilot of **Lacteva**. To set the
system up with *your* dairy's real operating rules and data, we need some
information from you.

A few things to know before you begin:

- The purpose of this pack is to configure Lacteva using **your dairy's real
  data and rules** — not sample data.
- **Your dairy remains the source of truth** for all of its information. We do
  not change your business rules; we configure the system to match them.
- We will configure the platform from what you supply, and **nothing goes into
  production until your team has reviewed it and signed off.**
- Please provide what you *actually use today*. Do not simplify or rewrite
  anything for us — especially your rate chart (Section F).

Each section below tells you **what we need, why, the format, who usually
provides it, and whether it is required or optional.** Fillable templates are
provided where helpful.

---

## A. Dairy / Organization details

*Why: to create your dairy's account with the correct name, location and
contact.*

| Field | Required? |
|---|---|
| Legal / registered business name | **Required** |
| Trading / operating name (if different) | Optional |
| Registered / operating address | **Required** |
| Primary contact person | **Required** |
| Contact mobile | **Required** |
| Contact email | Optional (used for notices) |
| Number of branches | **Required** |
| Number of collection centres | **Required** |
| Locations of collection centres | **Required** |

*Format: a short written response or a filled form. Provided by: dairy
owner/manager.*

---

## B. Collection centres

*Why: each physical centre is set up separately so collection, staff and
(later) equipment are organised correctly.*

Please fill one row per collection centre:

| Centre Code* | Centre Name | Location / Address | Operating Hours | Manager | Operator(s) | Existing Scale (make/model, if any) |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |

*\*Centre code is optional — if you already use codes, give them; otherwise we
will assign simple ones with you. Manager/operator names link to Section C.*

*Format: table (this template) or a spreadsheet. Provided by: dairy manager.*

---

## C. Staff who will use Lacteva

*Why: to give the right people the right access.*

**How Lacteva handles logins — please read:**
**One person = one Lacteva login.** That single login works across all the
Lacteva apps that person needs — there are **no separate passwords per app.**
One person can hold more than one responsibility and cover more than one centre
under the same login.

Please list only the staff who will **use the software** (see roles below).
Farmers and customers are **not** users and do **not** need logins (Sections E
and F).

| Name | Mobile | Email (optional) | Role (from list below) | Centre(s) | Apps needed |
|---|---|---|---|---|---|
|  |  |  |  |  |  |
|  |  |  |  |  |  |

**Roles Lacteva supports today, in plain terms:**

| Role | What they use Lacteva for |
|---|---|
| **Owner / Admin / Manager** | Oversee the whole dairy — dashboard, rates, settlements, payments, reports |
| **Centre Manager** | Run one collection centre — its collections, staff and day-to-day operation |
| **Collection Operator** | Record milk collection at a centre (weight, quality, rate, receipt) on the phone app |
| **Finance Manager / Officer** | Settlements, billing, payments and receivables |
| **Sales Officer** | Customers, standing orders, routes and deliveries |
| **Driver** | See today's delivery route on the phone and record deliveries |
| **Auditor** | Read-only access to review records |

*Format: table (this template). Provided by: dairy manager.*

---

## D. Which apps each person gets

*Why: so you know what each person will use. One person can use more than one
app when their job needs it — always under their single login.*

| App | Who typically uses it |
|---|---|
| **Lacteva Management Portal** (computer/browser) | Owner, managers, finance, sales, auditor |
| **Lacteva Collection App** (Android phone) | Collection operators, centre managers |
| **Lacteva Driver App** (Android phone) | Drivers |

*Example: a Centre Manager may use both the Management Portal and the Collection
App — with one login. A driver uses only the Driver App.*

> **Coming soon / future options (not part of this pilot):** a farmer app, a
> customer/outlet portal, automated equipment capture, messaging, analytics and
> more are on the Lacteva roadmap. They are **not** part of the current pilot
> and are mentioned here only so you know the direction — please do not plan the
> pilot around them.

---

## E. Farmer list

*Why: to record milk collection against the correct farmer and pay correctly.*

**Farmers are records in Lacteva — they do not need a login or an app for the
pilot.** Please provide only the information below (nothing extra is needed).

Fillable template (a spreadsheet/CSV with these columns is ideal):

| Farmer Code* | Farmer Name | Mobile | Village / Address | Collection Centre | Milk Type (Cow/Buffalo) |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

*\*If you already use farmer codes, please include them. Provide the list as a
spreadsheet/CSV if you can — that is the fastest to load. Provided by: dairy
manager / centre records.*

---

## F. Customer / outlet list

*Why: to set up who you deliver to, and their standing orders and prices.*

**Customers/outlets are records in Lacteva for the pilot — they do not need a
login.**

Fillable template:

| Code* | Name | Type (shop/household/institution) | Phone | Address | Route (if any) | Product | Standing Qty | Unit (L/kg) | Agreed Price |
|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |  |

*\*Optional. Provide as a spreadsheet/CSV if possible. Provided by: sales /
office.*

---

## G. Your rate chart — the most important item

*Why: this decides exactly what each farmer is paid. Getting it exactly right
is the single most important part of onboarding.*

> **Please give us your ACTUAL current rate chart — do not recreate, round, or
> simplify it for us.** Provide the real chart your dairy uses today.

Preferred, in order:
1. The **original Excel or PDF**, if you have one; **or**
2. A **clear photograph or scan** of the actual chart (front and back).

Please also tell us:

| Detail | |
|---|---|
| Effective date of this chart | |
| Cow and buffalo — same chart or separate? | |
| Do you buy by **litre or by kilogram**? | |
| Is the rate decided by **FAT only**, **FAT + SNF**, or a **formula**? | |
| Are CLR / density used? | |
| Slabs / bands (or attach the chart) | |
| Any deductions or additions | |

**What we do with it:** we digitize and configure it, then **your team reviews
it before it is published.** Before going live, we will take **one of your own
recent real collections** and recompute it through the configured chart to
confirm it matches your own arithmetic **to the paisa**.

*Format: Excel / PDF / clear photo. Provided by: owner / accountant.*

---

## H. Settlement rules

*Why: to calculate and reconcile farmer payments on your cycle.*

If you have a **written settlement policy/document, please send that** rather
than describing everything by hand. Otherwise, tell us:

| Detail | |
|---|---|
| Settlement frequency (e.g. 10-day / fortnight / monthly) | |
| Period start day | |
| Period end day | |
| Approval process (who approves a settlement) | |
| Any deductions (feed, advance recovery, commission, etc.) | |
| Any other settlement rules | |

*Format: written response or your existing settlement document. Provided by:
owner / accountant.*

---

## I. Documents we need on file

*Why: for onboarding, the pilot agreement, and to keep copies of the dairy's own
licences on record. **Your dairy remains responsible for its own regulatory
obligations** — Lacteva is your software provider, not your licensing
authority, and does not take on your regulatory status.*

| Document | Required? |
|---|---|
| **FSSAI licence / registration** copy | **Required** |
| **Legal Metrology (weights & measures) certificate** for the collection scale(s) | **Required where a trade scale is used** |
| **Signed pilot agreement** (we provide the template) | **Required** |
| **Privacy notice / consent** wording for your farmers and customers (we provide the template) | **Required** |

*Format: PDF / photo / signed copy. Provided by: owner / office.*

---

## J. After we receive your information

Once we have your information, Lacteva will:

1. Create and configure your dairy's account.
2. Set up your branches and collection centres.
3. Create logins for your authorized staff.
4. Load your farmer records.
5. Load your customer/outlet records.
6. Configure your rate chart.
7. Configure your settlement rules.
8. Configure day-to-day operational settings.
9. Run our technical checks (Day-0 verification).
10. **Sit with your team to reconcile a real sample** against your own figures.
11. Obtain your **sign-off**.
12. Begin the controlled pilot.

*(We will only set up what the platform does today. Anything on our future
roadmap is not part of this pilot.)*

---

## K. What your dairy will check before go-live

Before we go live, **your team confirms** each of these is correct:

- [ ] Farmer records
- [ ] Customer / outlet records
- [ ] Rate calculations
- [ ] The parchi (collection receipt)
- [ ] Settlement calculation
- [ ] Who can log in and what they can see
- [ ] Each centre's visibility
- [ ] The overall day-to-day workflow

**The key confirmation:** a sample of a real collection, priced by Lacteva,
**matches your own arithmetic — to the paisa.**

---

## L. Submission checklist

| # | Item | Format | Who provides | Required? |
|---|---|---|---|---|
| 1 | Organization details | form / written | owner/manager | **Required** |
| 2 | Collection centre list | table / spreadsheet | manager | **Required** |
| 3 | User / staff list | table | manager | **Required** |
| 4 | Farmer list | spreadsheet / CSV | manager | **Required** |
| 5 | Customer / outlet list | spreadsheet / CSV | sales/office | **Required** (if delivering) |
| 6 | **Actual rate chart** | Excel / PDF / clear photo | owner/accountant | **Required** |
| 7 | Settlement rules | written / document | owner/accountant | **Required** |
| 8 | FSSAI licence copy | PDF / photo | office | **Required** |
| 9 | Legal Metrology scale certificate | PDF / photo | office | **Required where applicable** |
| 10 | Signed pilot agreement | signed copy | owner | **Required** |
| 11 | Privacy / consent wording adopted | signed / on forms | owner | **Required** |

---

## M. How your information is handled

- Your information is collected only to **set up and run Lacteva** for your
  dairy.
- **Access is limited by role and by centre** — staff see only what their job
  requires.
- We configure that access according to the onboarding model agreed with you.
- Your data is stored securely. Applicable data-protection duties are handled
  as part of the standard agreement; **this is general good data governance, not
  a dairy-specific requirement.**

---

## N. What happens, and when

The onboarding sequence is:

**Information received → we validate it → we configure → we import your lists →
you review the rate chart → Day-0 reconciliation with your team → your sign-off
→ pilot starts.**

*Timing depends on how complete the information is and on your team's
availability, and will be **confirmed together** — we will not commit to a date
until we have what we need from you.*

---

## O. Contacts & submission

**Your Lacteva contact:**

- Name: ______________________________
- Mobile: ____________________________
- Email: _____________________________
- How to send your information: _______________________

**Dairy contact (please complete):**

- Name: ______________________________
- Role: ______________________________
- Mobile: ____________________________
- Email: _____________________________

---

*Thank you. Please return the completed checklist (Section L) with the
attachments. We will confirm receipt and the next steps with you.*

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Lacteva Onboarding | Initial dairy-facing onboarding information request pack: organization, centres, staff, apps, farmer + customer lists, rate chart, settlement rules, documents, what-Lacteva-does, dairy verification, submission checklist, privacy note, sequence, contacts. Business-facing; grounded in the onboarding runbook; no invented data, prices, or regulations (P0-PILOT-009). |
