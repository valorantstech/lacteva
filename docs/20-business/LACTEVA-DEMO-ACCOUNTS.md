---
id: LACTEVA-DEMO-ACCOUNTS
title: Demo Accounts — the dairies to show a client
type: reference
status: Draft
version: "0.1"
owner: Product & Platform Engineering
created: 2026-08-30
last-updated: 2026-08-30
related: [LACTEVA-GO-LIVE-READINESS, LACTEVA-BUSINESS-OPERATING-MODEL]
baseline: ARCH-BASELINE-V1
---

# Demo Accounts

Who to sign in as when showing Lacteva, what each one is meant to prove, and
where the data comes from.

**No password is written in this repository.** The seeder reads
`DEMO_PASSWORD` from the environment and falls back to a documented
development default; the value in use on a given deployment is held by the
owner. Everything below is a demo tenant on a demo host — none of it is a
customer, and none of it may ever be reused for one.

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
| 0.1 | 2026-08-30 | Product & Platform Engineering | First draft (WO-38b). The five India logins, what each demonstrates, where the password comes from, and the evidence that the dataset survives a host restart. |
