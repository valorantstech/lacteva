---
id: LACTEVA-P0-PILOT-006-DEV-ONBOARDING-REHEARSAL
title: P0-PILOT-006 — Controlled DEV Onboarding Rehearsal
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-MASTER-PRODUCT-ROADMAP, LACTEVA-IDENTITY-ENTERPRISE-ARCHITECTURE-AUDIT, LACTEVA-GO-LIVE-READINESS, LACTEVA-PILOT-ONBOARDING-PACK]
baseline: ARCH-BASELINE-V1
---

# P0-PILOT-006 — Controlled DEV Onboarding Rehearsal & User/Access Validation

**Synthetic data only; no real dairy, no personal data, no architecture change,
no production org modified.** This rehearses the onboarding + access lifecycle
from the master roadmap **before** the real dairy's artifacts arrive, to
validate the existing architecture and surface genuine defects. It does **not**
claim the platform is ready for the real pilot — that remains business/data/
legal gated (final gate below).

**How this was proven, stated honestly:** the onboarding + access + RLS +
workflow lifecycle was exercised as a **comprehensive integration test**
(`tests/test_dev_onboarding_rehearsal.py`, 8 tests) that onboards a wholly
synthetic *"DEMO DAIRY — DEV ONLY"* organisation end to end through the **real**
invitation → accept → role-grant → login flow, with a real login for every
role. This is **TEST-level** proof against the same app stack the deployment
runs. It is complemented by **REAL-on-DEV** evidence: Phase-1 endpoint presence
verified live on `dev.phoenixsoft.in`, and prior milestones' live proofs
(P0-PILOT-004 persona routing + driver run on a physical handset; P0-PILOT-005
live RLS 404). A synthetic org was **not** created on the shared DEV deployment
— deliberately, to avoid cluttering the environment about to host the real
pilot and the DEV invite-token friction (email disabled). That distinction is
kept explicit in §10.

---

## 1. Executive verdict

**PASS (rehearsal) — architecture validated; no genuine defect found.** The
complete onboarding and access lifecycle works: a synthetic org onboards with a
Workspace → Branch → three-Centre hierarchy; all nine currently-supported roles
onboard through one real invite→accept→grant→login flow with **one identity
per person**; multi-role/multi-centre grants coexist safely; the
person/farmer/customer/device distinction holds (records and devices are **not**
logins); RLS is organization-safe (foreign resource = 404, not 403) and
centre-scope narrows action; and the freshly-onboarded synthetic org
**transacts end to end** (priced collection → parchi). **This is not a
go-live claim** — the real pilot's business/data/legal gates are unchanged.

## 2. What was audited (Phase 1 — verified, not assumed)

Live on `dev.phoenixsoft.in`, all onboarding + lifecycle endpoints **GREEN**:
`/v1/organizations`, `/workspaces`, `/branches`, `/collection-centers`,
`/invitations`(+`/accept`), `/authz/assignments`(+`/roles`), `/drivers`,
`/vehicles`, `/routes`, `/rate-cards`, `/suppliers/import`, `/customers/import`,
`/settlements`, `/milk-transactions`, `/deliveries`. Code-verified: identity
tenant-scoped (`User.tenant_id`); `Membership` unique per (tenant,user);
`UserRole` scope-on-grant (`center_id`); RLS FORCED on `Organization.id`.
**Status: GREEN across the board; nothing modified.**

## 3. Synthetic organization structure

```
DEMO DAIRY — DEV ONLY (synthetic)   [org, country IN → INR/Asia-Kolkata/en-IN+hi-IN]
└── Pune Region (workspace)
     └── Pune Branch (PN-BR)
          ├── Wagholi Centre  (WG-C1)
          ├── Hadapsar Centre (HD-C1)
          └── Kharadi Centre  (KH-C1)
```
Onboarded via platform-admin → org create → tenant-admin invite→accept. Proven
by `test_synthetic_org_and_hierarchy_onboard`.

## 4. User / role onboarding results

Nine roles, each via the full **invite → accept (sets credential) → grant named
role at scope → login**, `/auth/me` confirming a usable identity:

| Role | Scope | Onboarded | Login |
|---|---|---|---|
| tenant-admin (owner) | org | ✓ | ✓ |
| ORGANIZATION_ADMIN | org | ✓ | ✓ |
| ORGANIZATION_MANAGER | org | ✓ | ✓ |
| COLLECTION_OPERATOR | centre (WG-C1) | ✓ | ✓ |
| CENTRE_MANAGER | centre (WG-C1) | ✓ | ✓ |
| FINANCE_OFFICER | org | ✓ | ✓ |
| FINANCE_MANAGER | org | ✓ | ✓ |
| SALES_OFFICER | org | ✓ | ✓ |
| AUDITOR | org read | ✓ | ✓ |

Proven by `test_every_current_role_onboards_with_one_identity`.

## 5. Application access matrix

Access is **authorization-driven** (role + scope), not per-application
credentials — the same identity is used everywhere.

| User | Role | Org | Location | Portal | Collection App | Driver App | Future apps | Allowed | Reason |
|---|---|---|---|---|---|---|---|---|---|
| Owner | tenant-admin | DEMO | org | ✓ | (as needed) | — | future | ✓ | admin |
| Org manager | ORGANIZATION_MANAGER | DEMO | org | ✓ | — | — | future | ✓ | ops |
| Operator | COLLECTION_OPERATOR | DEMO | WG-C1 | refused office | ✓ | — | — | scoped | capture only; **403** on settlements (verified) |
| Centre manager | CENTRE_MANAGER | DEMO | WG-C1 | ✓ | ✓ | — | — | scoped | centre ops |
| Finance mgr/officer | FINANCE_* | DEMO | org | ✓ | — | — | future | ✓ | settlement/billing |
| Sales | SALES_OFFICER | DEMO | org | ✓ | — | — | future | ✓ | orders/routes |
| Driver | DRIVER | DEMO | own runs | refused office | — | ✓ | — | scoped | run app only |
| Auditor | AUDITOR | DEMO | org read | ✓ (read) | — | — | future | read | **403** on customer write (verified) |

Verified by `test_access_matrix_is_authorization_not_credentials` (operator
403 on settlements; auditor 403 on customer write) and the live persona-routing
proofs from P0-UX-001 (portal refusal) and P0-PILOT-004 (mobile experienceFor).

## 6. Identity validation

**ONE PERSON → ONE LACTEVA IDENTITY → MULTIPLE APPLICATION CAPABILITIES**
confirmed: each onboarded person has a single identity and single credential;
`/auth/me` answers under that one token; the portal and mobile apps authorise
from the same identity + role + scope. No per-application credential was minted
anywhere in the rehearsal.

## 7. Multi-role / multi-centre validation

One person granted **COLLECTION_OPERATOR @ Wagholi AND CENTRE_MANAGER @ Hadapsar**
— both grants coexist on one identity (both 201), the identity stays usable, and
each grant is **independently revocable** (204 twice), proving two distinct rows
rather than one overwriting the other. No unintended access; scope is on the
grant. Proven by `test_multi_role_multi_centre_grants_coexist_safely`.
**Enterprise multi-organization identity was NOT implemented** — remains
ENTERPRISE/FUTURE.

## 8. Farmer / customer / driver / device distinction

- **Farmer/supplier** and **customer/outlet**: imported as **business records**;
  neither can authenticate (login attempts → 401/422). No account is created.
- **Device** (a scale): registered as an **asset at a location**; no login
  surface (serial cannot authenticate).
- **Driver**: a **person who logs in** (proven live end-to-end in P0-PILOT-004).
Proven by `test_farmer_and_customer_are_records_not_logins` and
`test_device_is_an_asset_not_a_login`.

## 9. Synthetic end-to-end business workflow

The onboarded-from-scratch synthetic org **transacts**: ready centre + published
INR rate card + synthetic farmer → collection driven to **COMPLETED**, `priced`,
cow, with a **parchi (SLP-…)** whose `organization_name` is the synthetic org
and whose `unit_price` is byte-identical to the engine's. Proven by
`test_the_onboarded_synthetic_org_can_transact_end_to_end`. The **sales half**
(order → route → driver → delivery → billing/receivable) is proven by the
existing suite (`test_daily_operations`, `test_dairy_reconciliation`,
`test_driver_execution`) and by the **live driver run on a physical handset**
(P0-PILOT-004).

## 10. RLS / security results (Phase 8)

| Check | Result |
|---|---|
| Org-A user → Org-A data | allowed |
| Org-A user → Org-B data | **denied — 404 (invisibility, not 403 leak)** |
| Foreign centre by id | **404** |
| Org-B admin centre count | 0 (sees none of A's) |
| Operator (centre-scoped) → settlement write | **403** |
| Auditor → customer write | **403** |
| Driver → own run | allowed (P0-PILOT-004) |
| Driver → another driver's run | **404** (P0-PILOT-004) |

Proven by `test_rls_is_organization_safe_across_synthetic_orgs` + prior live
proofs. **RLS was not weakened to make anything pass.**

## 11. Mobile validation (Phase 9)

**NOT PROVEN in this milestone** — no handset is currently attached
(`adb devices` empty). Not fabricated. **Already REAL from P0-PILOT-004**
(same APK, not regressed by this doc-only milestone): login, persona routing,
operator capture, driver run, offline capture + sync, all proven on a physical
Motorola moto g57 power (Android 16). Re-running here would add nothing; if a
handset is reconnected, a 10-minute re-confirmation is available on request.

## 12. REAL vs TEST vs NOT PROVEN

- **REAL (on the live DEV deployment):** all onboarding/lifecycle endpoints
  present (Phase 1); RLS 404 (P0-PILOT-005); persona routing + full operator
  capture + driver run + offline/sync on a physical handset (P0-PILOT-004);
  parchi live (P0-BIZ-003).
- **TEST (this milestone's integration rehearsal, synthetic data):** synthetic
  org + hierarchy onboarding; all nine roles onboarded with one identity; the
  access matrix (operator/auditor refusals); multi-role/multi-centre coexistence;
  farmer/customer/device non-login distinction; the org-safe/centre-scoped RLS
  assertions; the end-to-end priced-collection→parchi in the onboarded org.
- **NOT PROVEN:** a handset re-run this milestone; and — unchanged — **anything
  requiring the real dairy's data** (real rate chart, farmer/outlet lists,
  settlement rules), real hardware (P0-HW-003), or future modules. **This
  synthetic DEV rehearsal is explicitly NOT "real dairy onboarding."**

## 13. Defects discovered

**None genuine.** One test-authoring correction (not a product defect): the
first draft assumed a `GET /v1/authz/assignments` listing that does not exist
(the endpoint offers POST/DELETE only) — the test now proves multi-grant
coexistence behaviorally (independent revocation) instead. The product behaved
correctly throughout.

## 14. Defects fixed

None (none found). The rehearsal is a permanent regression artifact.

## 15. Tests executed

`tests/test_dev_onboarding_rehearsal.py` — **8 tests, all passing** (true exit
code): org+hierarchy onboarding; nine-role one-identity onboarding; access
matrix; multi-role/multi-centre; farmer/customer non-login; device non-login;
org-safe RLS; end-to-end transact→parchi. Plus the **full backend suite** as a
regression gate (result recorded at commit). ruff clean.

## 16. Remaining blockers (unchanged — business/data/legal)

Real rate chart · farmer list · outlet list · settlement rules · FSSAI licence
copy · Legal Metrology scale certificate · signed pilot agreement · production
backup-retention config · actual dairy business validation. **None is code.**

## 17. Production readiness implications

The onboarding + access + RLS + transaction lifecycle is validated for a
freshly-created org — the platform will onboard the real dairy the day its
artifacts arrive. **No new engineering is implied.** DEV invite delivery is
disabled (email off); production must enable a real notification channel (SMTP)
or use the admin-in-tenant bootstrap for the first users — a config note, not a
defect.

## 18. Exact next milestone

Per the master roadmap and the milestone's own gate:
**A. REAL DAIRY GO-LIVE** — when the four artifacts + FSSAI/LM copies + signed
agreement arrive (business-gated). Otherwise **B. P0-HW-003** only if the
P0-HW-002 physical-evidence gate is satisfied (it is not yet). No **C.**
defect-fix milestone is needed — none found. **Do not auto-start any of them.**

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Platform Engineering | Controlled DEV onboarding rehearsal: synthetic org + hierarchy, nine-role one-identity onboarding, access matrix, multi-role/multi-centre, farmer/customer/device non-login distinction, org-safe/centre-scoped RLS, and end-to-end transact→parchi — proven by an 8-test integration rehearsal (synthetic data) plus live DEV endpoint presence and prior physical-handset proofs. No genuine defect; no architecture change; real-pilot gates unchanged (P0-PILOT-006). |
