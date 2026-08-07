"""Compare a restored database against its source, fact for fact (DR-001).

A recovery is only proven if the recovered system holds the same facts as the
one that was lost. "The restore exited zero" and "the row counts look right"
are both weaker claims than they appear: a count matches while the money is
wrong, and an exit code says nothing about content.

## How this compares

By **re-backing-up the restored database** and comparing manifests.

That is not a trick. The backup engine already computes a sha256 per table
over rows serialized in primary-key order, precisely so the same data always
produces the same checksum. So a table whose checksum matches is identical in
every column of every row — not merely the same size, and not merely the same
in the columns somebody thought to check.

The alternative — a hand-written list of `SELECT`s — compares what the author
remembered. This compares all 51 tables including the ones nobody would think
to list, which is where a recovery defect actually hides.

## Projections are compared too, and differently

Rebuildable projections are deliberately absent from the backup (BR-0015:
they are derived from the event log). So they cannot be compared as restored
bytes — they are compared *after a rebuild*, which is the stronger claim: not
"the projection was copied" but "the projection can be reconstructed and comes
out identical".

Usage:

    python infra/ci/dr_compare.py SOURCE_URL RESTORED_URL --backup DIR
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import tempfile

# The entities the recovery report names explicitly. Every one is also covered
# by the table-by-table comparison; naming them makes the report legible to
# somebody deciding whether to trust a recovery, and makes a gap in coverage
# visible as a missing line rather than as silence.
NAMED_FACTS = {
    "users": "SELECT email FROM user_account ORDER BY 1",
    "organizations": "SELECT name || '|' || slug FROM organization ORDER BY 1",
    "suppliers": (
        "SELECT s.code || '|' || s.status || '|' || coalesce(p.full_name, '-') "
        "FROM supplier s LEFT JOIN supplier_profile p ON p.supplier_id = s.id ORDER BY 1"
    ),
    "collection sessions": (
        "SELECT label || '|' || status || '|' || center_id::text FROM collection_session ORDER BY 1"
    ),
    "collections": (
        "SELECT state || '|' || coalesce(net_weight::text, '-') || '|' "
        "|| coalesce(gross_amount::text, '-') || '|' || coalesce(fat::text, '-') "
        "FROM milk_collection_transaction ORDER BY 1"
    ),
    "settlements": (
        "SELECT settlement_number || '|' || net_amount || '|' || status FROM settlement ORDER BY 1"
    ),
    "payments": ("SELECT payment_number || '|' || amount || '|' || status FROM payment ORDER BY 1"),
    "receipts": "SELECT receipt_number || '|' || net_amount FROM receipt ORDER BY 1",
    "reports": (
        "SELECT final_state || '|' || coalesce(duration_seconds::text, '-') "
        "FROM transaction_metrics ORDER BY 1"
    ),
    "audit log": (
        "SELECT action || '|' || resource_type || '|' || coalesce(resource_id::text, '-') "
        "FROM audit_record ORDER BY 1"
    ),
    "outbox": (
        "SELECT event_name || '|' || status || '|' || version::text FROM event_outbox ORDER BY 1"
    ),
    "events": "SELECT event_type || '|' || sequence::text FROM transaction_event ORDER BY 1",
    # The safety property that matters more than any row count: a restored
    # system must not re-deliver. Cursor POSITIONS are compared exactly —
    # a rewound cursor means every farmer is texted again.
    "consumer positions": (
        "SELECT consumer_name || '|' || position_created_at::text || '|' "
        "|| position_event_id::text FROM consumer_cursor ORDER BY 1"
    ),
    # The dispatch consumer's idempotency ledger, which is what makes replay
    # safe. A restore that resets this turns recovery into a duplicate-SMS
    # incident.
    "notification ledger": (
        "SELECT event_id::text FROM consumer_execution "
        "WHERE consumer_name = 'notification-dispatch' ORDER BY 1"
    ),
    "projections": (
        "SELECT day::text || '|' || transactions::text || '|' || accepted::text || '|' "
        "|| payable_amount::text FROM projection_daily_totals ORDER BY 1"
    ),
}


async def _manifest_of(url: str, destination: pathlib.Path) -> dict:
    """Back up `url` and return its manifest, unchanged."""
    import os

    os.environ["LACTEVA_DATABASE_URL"] = url
    # Settings are cached, and this process may already have read a different
    # URL. Clearing is what lets one process look at both databases.
    from platform_core.core.config import get_settings

    get_settings.cache_clear()
    import platform_core.core.db as db

    for attr in ("_engine", "_session_factory"):
        if hasattr(db, attr):
            setattr(db, attr, None)

    from platform_core.core.backup.engine import BackupEngine
    from platform_core.core.rls import platform_factory

    engine = BackupEngine(platform_factory("DR comparison: whole-database read"))
    manifest = await engine.backup(destination)
    return json.loads(manifest.to_json())


async def _facts(url: str) -> dict[str, list[str]]:
    import asyncpg

    dsn, _, host = url.partition("?host=")
    database = dsn.rsplit("/", 1)[1]
    conn = await asyncpg.connect(user="postgres", database=database, host=host)
    out = {}
    for name, sql in NAMED_FACTS.items():
        try:
            out[name] = [str(r[0]) for r in await conn.fetch(sql)]
        except Exception as exc:
            # DR-001, found in this very tool: returning the error as a STRING
            # made two identically-broken queries compare equal, so four
            # checks reported "match" while querying columns that do not
            # exist. A comparison that cannot fail is not a comparison —
            # exactly the failure this whole work order is about. Raise.
            raise SystemExit(
                f"the comparison query for {name!r} is invalid: {exc}\n"
                f"  SQL: {sql}\n"
                "Fix the query — a check that errors identically on both sides "
                "would otherwise pass while proving nothing."
            ) from exc
    await conn.close()
    return out


# Tables whose content cannot be compared byte-for-byte after a restore, each
# with the reason. NEVER extend this to make a failure go away — a silent
# exclusion is how a recovery defect survives. Every entry here is printed.
VOLATILE = {
    "backup_run": (
        "records the act of backing up, so taking the comparison backup writes "
        "a row into the source. It cannot be compared with itself"
    ),
    "consumer_cursor": (
        "the post-restore rebuild touches updated_at. Positions are compared "
        "exactly above, and those are what prevent re-delivery"
    ),
    "consumer_execution": (
        "the rebuild rewrites the PROJECTION consumers' ledger entries as it "
        "replays. The notification consumer's ledger is compared exactly above, "
        "and that is the entry that prevents duplicate sends"
    ),
}


def _compare_manifests(source: dict, restored: dict) -> list[str]:
    problems = []
    src = {t["table"]: t for t in source["tables"]}
    dst = {t["table"]: t for t in restored["tables"]}

    for name in sorted(set(src) - set(dst)):
        problems.append(f"{name}: present in the source backup, ABSENT after restore")
    for name in sorted(set(dst) - set(src)):
        problems.append(f"{name}: appeared after restore, not in the source backup")

    for name in sorted(set(src) & set(dst)):
        if name in VOLATILE:
            print(f"  not compared  {name}: {VOLATILE[name]}")
            continue
        a, b = src[name], dst[name]
        if a["rows"] != b["rows"]:
            problems.append(f"{name}: {a['rows']} rows in source, {b['rows']} restored")
        elif a["checksum"] != b["checksum"]:
            # Same row count, different content — the failure mode a count
            # check cannot see, and the one that costs money.
            problems.append(
                f"{name}: {a['rows']} rows match but the CONTENT differs "
                f"({a['checksum'][:12]} vs {b['checksum'][:12]})"
            )
    return problems


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_url")
    parser.add_argument("restored_url")
    args = parser.parse_args()

    print("== fact-by-fact comparison ==")
    source_facts = await _facts(args.source_url)
    restored_facts = await _facts(args.restored_url)

    failures = []
    for name in NAMED_FACTS:
        a, b = source_facts[name], restored_facts[name]
        if a == b:
            sample = ", ".join(a[:2])[:58] or "(none)"
            print(f"  {name:20s} match   {len(a):4d}  {sample}")
        else:
            print(f"  {name:20s} MISMATCH")
            print(f"      source:   {a[:4]}")
            print(f"      restored: {b[:4]}")
            failures.append(name)

    print("\n== table-by-table content checksums ==")
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        source_manifest = await _manifest_of(args.source_url, root / "source")
        restored_manifest = await _manifest_of(args.restored_url, root / "restored")

    problems = _compare_manifests(source_manifest, restored_manifest)
    total = len(source_manifest["tables"])
    if problems:
        for line in problems:
            print(f"  MISMATCH  {line}")
        failures.extend(problems)
    else:
        compared = [t for t in source_manifest["tables"] if t["table"] not in VOLATILE]
        rows = sum(t["rows"] for t in compared)
        print(
            f"  all {len(compared)} of {total} tables identical — {rows} rows, "
            "checksum for checksum"
        )

    if failures:
        print(f"\nRECOVERY NOT PROVEN — {len(failures)} difference(s)")
        return 1
    print("\nRECOVERY PROVEN — the restored database holds the same facts as its source")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
