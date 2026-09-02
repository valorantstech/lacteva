---
id: LACTEVA-DEMO-ACCOUNTS
title: Demo Accounts — the dairies to show a client
type: reference
status: Draft
version: "0.2"
owner: Product & Platform Engineering
created: 2026-08-30
last-updated: 2026-09-02
related: [LACTEVA-GO-LIVE-READINESS, LACTEVA-BUSINESS-OPERATING-MODEL]
baseline: ARCH-BASELINE-V1
---

# Demo Accounts

Who to sign in as when showing Lacteva, what each one is meant to prove, and
where the data comes from.

**How the demo password is set, exactly.** It is supplied as `DEMO_PASSWORD`
in the environment of the `seed_demo.py` run that builds the dataset, and
nowhere else. It is **not** stored in this repository, and it is **not** in
`/etc/lacteva/.env.production` on the host — a demo credential filed beside the
production secrets becomes a production secret. So the password in force on a
deployment is whichever value that run was given; there is no place to look it
up, by design, and the owner holds it.

If it is unknown, the answer is another `reset` under a password you choose.
That is safe now and was not always: the seeder purges before it seeds, and it
used to authenticate as a demo admin account created by the *previous* run, so
a reset under a different `DEMO_PASSWORD` deleted the dairy and then could not
rebuild it. LACTEVA-DEMO-003 fixed that — the seeder adopts its own admin under
the current password and says so in its output.

Everything below is a demo tenant on a demo host — none of it is a customer,
and none of it may ever be reused for one.

---

## 1 · The dairies

Both are built by `infra/demo/seed_demo.py`, which drives the platform's own
API in process. Every figure on every screen was calculated by the pricing
engine and the settlement rules, not written by the seeder — which is the
point: a demo that fakes its numbers is a demo that lies about the product.

| Tenant | Market | Shows |
|---|---|---|
| **Lacteva India Demo** | India (INR) | The cycle-4 dairy: 32 farmers across three centres, a fourth centre opened late, three weeks of collections, settlements paid through to receipts, a customer side with invoices, routes with a driver |
| Lacteva Demo Cooperative | Kenya (KES) | The original demo, kept because the evidence trail of several milestones refers to it |
| Lacteva Isolation Demo | — | Exists to be looked at from the other tenant and found invisible |

---

## 2 · The logins

Same password for all of them, from `DEMO_PASSWORD`.

| Email | Person | Role | What it demonstrates |
|---|---|---|---|
| `manager@lacteva-india.example.com` | Priya Raghavan | tenant-admin | The whole dairy: dashboards, reports, settlements, rate cards |
| `operations@lacteva-india.example.com` | Deepak Shenoy | ORGANIZATION_MANAGER | Running the operation without the administrative powers |
| `operator@lacteva-india.example.com` | Sunita Bhat | COLLECTION_OPERATOR | The handset: the collection wizard and the operator's home |
| `sales@lacteva-india.example.com` | Rahul Verma | SALES_OFFICER | The customer side — deliveries, invoices, payments |
| `viewer@lacteva-india.example.com` | Arun Menon | tenant-viewer | What a read-only account can and cannot reach |

The Kenyan tenant carries the same five at `@lacteva-demo.example.com`.

### Which dairy to demonstrate (WO-60 rider)

**Demonstrate an Indian dairy with the INDIA tenant** —
`manager@lacteva-india.example.com`, rupees, Indian farmer and household
names. The Kenyan cooperative exists to prove the platform is multi-currency
and multi-market, not to be shown to an Indian client: a demonstration that
opens on "Amina Njoroge" and KES answers a question nobody asked, and the
"KES on some pages, INR on others" report that produced this note was somebody
moving between the two tenants and having no way to tell which one they were
looking at. The organization chip now names the dairy on every screen, so that
question is answerable at a glance — check it before sharing your screen.

### Demonstrating the rate override (BR-0029)

`pricing.rate.override` is the permission behind D-15's "the owner may edit
the rate". Of the demo logins, **only `manager@` holds it** — it is a
tenant-admin, and the permission is otherwise granted to `CENTRE_MANAGER`,
which none of these five is.

That makes the pair worth showing together, in this order:

1. Sign in as **`manager@`**, open a priced collection in the wizard's review
   step, and use **Edit rate**. It shows the card rate, requires a reason, and
   the parchi then carries both numbers and the reason. The portal's
   transaction detail shows the same, with who changed it and when.
2. Sign in as **`operator@`** and open the same step. **There is no Edit rate
   control** — not a greyed-out one. A disabled button would tell the person
   at the counter that the capability exists and they are not trusted with it,
   which is a different and worse message than not offering it.

`operations@`, `sales@` and `viewer@` behave like the operator here: the
control is absent. If a demonstration needs a second holder, grant a user the
`CENTRE_MANAGER` role rather than widening the operator's.

**Roles, not people, decide what is visible.** Signing in as the viewer and
finding the settlement actions absent is a demonstration, not a limitation —
the platform gates on capabilities, and a dairy that renames a role keeps the
same screen.

---

## 3 · Where it runs

The demo host is **always on** (D-13). It is not stopped after a session, and
only the owner decides when it sleeps.

**The data survives a stop and start**, which was confirmed rather than
assumed: PostgreSQL's data is a named Docker volume on the instance's root
EBS disk, every service carries `restart: unless-stopped`, the image's
`docker-entrypoint-initdb.d` scripts run only against an EMPTY data
directory, and no systemd unit or boot hook on the host references the
seeder. Nothing purges on boot; the dairy is simply there again.

---

## 4 · Rebuilding it

```bash
# Inside the api container, which is where the platform package lives.
python /tmp/seed_demo.py reset      # purge the demo tenants, then rebuild
python /tmp/seed_demo.py verify     # assert it is complete and correct
```

`reset` deletes **only** the three demo tenants — it is keyed on their ids, so
anything else on the host is untouched. `seed india` rebuilds one market
without disturbing the other.

The script is not in the API image (it copies `src`, `migrations`,
`alembic.ini` and `pyproject.toml`, and there is no `/app/infra`), so it is
copied in for the run. See the WO-38 report for the exact commands.

`DEMO_PASSWORD` is **not** set in `/etc/lacteva/.env.production`, deliberately
and confirmed by inspection — a demo password stored beside the production
secrets is a production secret. It is supplied to the `reset` that builds the
dataset, so the password in force is whichever value that run was given. If it
has been lost, the answer is another `reset` with a known one, not a lookup.

The five India accounts above were confirmed present and active on the live
host on 2026-08-29, immediately after a deployment that recreated every
container — which is the restart-survival evidence in §3, observed rather
than argued.

---

## 5 · Rules

- **Demo only.** These accounts exist on the demo deployment. They are not
  created on a customer's tenant, and the password is not reused anywhere.
- **No real personal data.** Every name, phone number and address in the
  dataset is invented. The email domains are `example.com` subdomains, which
  are reserved for documentation and cannot receive mail.
- **Say what is demo.** A screen shown to a client is showing a demo dairy,
  and that is worth saying out loud rather than letting them assume the
  numbers are somebody's.

## Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 0.2 | 2026-09-02 | Product & Platform Engineering | WO-60 rider: which dairy to demonstrate, and why the Kenyan tenant is the multi-currency proof rather than the client-facing demo. |
| 0.1 | 2026-08-30 | Product & Platform Engineering | First draft (WO-38b). The five India logins, what each demonstrates, where the password comes from, and the evidence that the dataset survives a host restart. |
