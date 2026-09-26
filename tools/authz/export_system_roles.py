#!/usr/bin/env python3
"""Export the platform's system roles for the portal's menu tests (WO-104).

The admin portal pins one menu per kind of user against its nav registry.
"Kind of user" means the permission set a role carries, and that set lives in
ONE place — `modules/authz/permissions.py`. Rather than the portal tests
copying those lists by hand (the catalog-without-callers mistake), this writes
them to `apps/admin-portal/src/lib/system-roles.json`, and a backend test
fails when the JSON is behind the registry.

    services/platform-core/.venv/bin/python tools/authz/export_system_roles.py
    services/platform-core/.venv/bin/python tools/authz/export_system_roles.py --check
"""

from __future__ import annotations

import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT = REPO / "apps/admin-portal/src/lib/system-roles.json"


def current() -> dict[str, list[str]]:
    sys.path.insert(0, str(REPO / "services/platform-core/src"))
    from platform_core.modules.authz.permissions import ALL_SYSTEM_ROLES

    return {name: sorted(set(perms)) for name, perms in sorted(ALL_SYSTEM_ROLES.items())}


def render(roles: dict[str, list[str]]) -> str:
    return json.dumps(roles, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    text = render(current())
    if "--check" in argv:
        if OUT.exists() and OUT.read_text() == text:
            print(f"{OUT.relative_to(REPO)} is current")  # noqa: T201
            return 0
        print(f"{OUT.relative_to(REPO)} is BEHIND the permission registry — rerun without --check")  # noqa: T201
        return 1
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(REPO)} ({len(current())} roles)")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
