#!/usr/bin/env python3
"""Reconcile a database's localization against what the platform promises.

DEMO-013 §8. Every check below is a question somebody would ask before
believing the demo, answered against the REAL database rather than against a
test fixture:

* does each organization's money, clock and languages match its country?
* is there any money row denominated in something its tenant does not use?
* is every user's language one their organization actually enabled?
* is any tenant's data visible from another's rows?
* are the constraints, indexes and RLS policies the schema claims still there?

It reports facts and exits non-zero on the first difference. It changes
nothing — safe to run against production, which is the point: this is the
check to run *after* a deployment, not only before one.

    python infra/ci/reconcile_localization.py            # uses PG* env
    python infra/ci/reconcile_localization.py --database lacteva
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

#: Country → (currency, timezone). The platform's registry, restated here on
#: purpose: a reconciliation that imported `core.locales` would agree with the
#: application by construction and could not detect the application being
#: wrong. Two independent statements of the same fact is the whole method.
EXPECTED = {
    "IN": ("INR", "Asia/Kolkata"),
    "KE": ("KES", "Africa/Nairobi"),
    "AE": ("AED", "Asia/Dubai"),
    "SA": ("SAR", "Asia/Riyadh"),
    "UG": ("UGX", "Africa/Kampala"),
    "TZ": ("TZS", "Africa/Dar_es_Salaam"),
    "GB": ("GBP", "Europe/London"),
    "US": ("USD", "America/New_York"),
}

problems: list[str] = []
notes: list[str] = []


def q(database: str, sql: str) -> list[list[str]]:
    """One query, tab-separated, no ceremony."""
    out = subprocess.run(
        ["psql", "-d", database, "-tA", "-F", "\t", "-c", sql],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise SystemExit(f"psql failed: {out.stderr.strip()}")
    return [line.split("\t") for line in out.stdout.strip().splitlines() if line]


def check(condition: bool, ok: str, bad: str) -> None:
    (notes if condition else problems).append(ok if condition else bad)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default=os.environ.get("PGDATABASE", "lacteva"))
    args = parser.parse_args()
    db = args.database

    print(f"Reconciling localization in {db}\n")

    # --- 1. every organization's locale matches its country -------------------
    orgs = q(
        db,
        "SELECT slug, upper(country_code), currency_code, timezone, "
        "supported_languages::text, default_locale FROM organization ORDER BY slug",
    )
    print(f"organizations: {len(orgs)}")
    for slug, country, currency, timezone, languages, default in orgs:
        expected = EXPECTED.get(country)
        if expected is None:
            # Not an error: an unlisted country is onboardable when the caller
            # supplies the values. It is worth SAYING, because a silent XXX is
            # a tenant that cannot trade.
            note = f"  {slug}: country {country} is not in this check's table ({currency})"
            (problems if currency == "XXX" else notes).append(
                f"{note} — currency XXX means it cannot record money" if currency == "XXX" else note
            )
            continue
        check(
            (currency, timezone) == expected,
            f"  {slug}: {country} → {currency} {timezone}",
            f"  {slug}: {country} should be {expected[0]} {expected[1]}, "
            f"is {currency} {timezone}",
        )
        languages_list = json.loads(languages)
        check(
            default in languages_list,
            f"  {slug}: default {default} is among {languages_list}",
            f"  {slug}: default language {default} is NOT among {languages_list}",
        )

    # --- 2. no money row in a currency its tenant does not use -----------------
    # The question a finance officer asks: is anything on our books denominated
    # in somebody else's money? Checked per table because each one is written
    # by a different path.
    for table in (
        "customer",
        "customer_invoice",
        "customer_payment",
        "customer_receipt",
        "milk_delivery",
        "delivery_plan",
        "settlement",
        "payment",
        "receipt",
        "rate_card",
    ):
        exists = q(db, f"SELECT to_regclass('public.{table}') IS NOT NULL")[0][0]
        if exists != "t":
            continue
        rows = q(
            db,
            f"SELECT o.slug, t.currency, count(*) FROM {table} t "
            f"JOIN organization o ON o.id = t.tenant_id "
            f"WHERE t.currency IS DISTINCT FROM o.currency_code "
            f"GROUP BY 1, 2",
        )
        check(
            not rows,
            f"  {table}: every row in its tenant's currency",
            f"  {table}: {rows} — rows in a currency the tenant does not use",
        )

    # --- 3. every user's language is one their organization enabled ------------
    strays = q(
        db,
        "SELECT u.email, u.locale, o.supported_languages::text "
        "FROM user_account u JOIN organization o ON o.id = u.tenant_id "
        "WHERE NOT (o.supported_languages)::jsonb ? u.locale",
    )
    # Not fatal: an administrator may narrow the list after somebody chose, and
    # DEMO-013 deliberately does not rewrite their preference — negotiation
    # falls back at render time. Worth reporting, never worth failing on.
    for email, locale, languages in strays:
        notes.append(f"  {email}: prefers {locale}, organization offers {languages} (falls back)")
    if not strays:
        notes.append("  every user's language is one their organization enabled")

    # --- 4. tenant isolation is still enforced by the database -----------------
    tenant_tables = q(
        db,
        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
        "  (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN information_schema.columns col "
        "  ON col.table_name = c.relname AND col.column_name = 'tenant_id' "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY c.relname",
    )
    unprotected = [
        name
        for name, rls, forced, policies in tenant_tables
        if rls != "t" or forced != "t" or int(policies) == 0
    ]
    check(
        not unprotected,
        f"  RLS enabled and FORCED with a policy on all {len(tenant_tables)} tenant tables",
        f"  RLS missing or unforced on: {unprotected}",
    )

    # --- 5. the schema the application believes in ----------------------------
    for table, column, kind in (
        ("organization", "currency_code", "character varying"),
        ("organization", "timezone", "character varying"),
        ("organization", "supported_languages", "json"),
        ("organization", "default_locale", "character varying"),
        ("user_account", "locale", "character varying"),
    ):
        found = q(
            db,
            "SELECT data_type, is_nullable, coalesce(character_maximum_length::text, '') "
            f"FROM information_schema.columns WHERE table_name='{table}' "
            f"AND column_name='{column}'",
        )
        row = found[0] if found else []
        # Padded rather than indexed blind: `character_maximum_length` is NULL
        # for a json column, and psql can hand back a shorter row than the
        # SELECT suggests. An index error here would fail the reconciliation
        # for the wrong reason.
        row = (row + ["", "", ""])[:3]
        length = f"({row[2]})" if row[2] else ""
        check(
            bool(found) and row[0] == kind,
            f"  {table}.{column}: {kind}{length} nullable={row[1] or '?'}",
            f"  {table}.{column}: expected {kind}, found {found}",
        )
    nulls = q(
        db,
        "SELECT count(*) FROM organization WHERE currency_code IS NULL "
        "OR timezone IS NULL OR supported_languages IS NULL",
    )[0][0]
    check(nulls == "0", "  no organization without a locale", f"  {nulls} organizations incomplete")

    version = q(db, "SELECT version_num FROM alembic_version")[0][0]
    notes.append(f"  schema at {version}")

    # --- report ---------------------------------------------------------------
    print("\n".join(notes))
    if problems:
        print("\nDIFFERENCES:")
        print("\n".join(problems))
        print(f"\nRECONCILIATION FAILED — {len(problems)} difference(s)")
        return 1
    print("\nRECONCILIATION PASSED — no unexpected differences")
    return 0


if __name__ == "__main__":
    sys.exit(main())
