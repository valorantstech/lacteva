#!/usr/bin/env python3
"""No private key and no service-account identity anywhere in the tree (WO-77).

    python3 tools/validate/check_secrets.py [ROOT]

The Firebase service-account key can push to every handset in the project. It
belongs on the host, in `/etc/lacteva/fcm-service-account.json`, and nowhere
in this repository — not committed, not copied into a test fixture, not pasted
into a document. `.gitignore` refuses the two file names it usually has; this
refuses the CONTENTS, whatever the file is called, because a secret that is
one careless `git add` away from a public history needs a machine watching
rather than a note.

Two markers, both of which appear in every Google service-account key and in
no legitimate file of this repository:

    -----BEGIN PRIVATE KEY-----      the PEM body of the private key
    .iam.gserviceaccount.com         the service account's identity

Every text file under ROOT is scanned except the directories no secret has any
business in and this tool's own source. A hit names the file and the line,
and exit 1 fails the gate. Exit 0 = the tree carries neither marker.
"""

from __future__ import annotations

import pathlib
import sys

MARKERS = ("-----BEGIN PRIVATE KEY-----", ".iam.gserviceaccount.com")
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    ".next",
    ".dart_tool",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    ".gradle",
}
#: Binary-looking suffixes are not read: a marker cannot be in a JPEG, and
#: reading fonts as text is a source of nothing but noise.
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".woff", ".woff2",
    ".ttf", ".otf", ".jks", ".keystore", ".zip", ".apk", ".aab", ".db", ".sqlite3",
    ".lock", ".pyc",
}
SELF = pathlib.Path(__file__).resolve()


def scan(root: pathlib.Path) -> list[str]:
    hits: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES or path.resolve() == SELF:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for marker in MARKERS:
                if marker in line:
                    hits.append(f"{path.relative_to(root)}:{number}: contains {marker!r}")
    return hits


def main(argv: list[str]) -> int:
    root = pathlib.Path(argv[1]).resolve() if len(argv) > 1 else SELF.parents[2]
    hits = scan(root)
    if hits:
        print("check_secrets: a service-account secret is in the tree", file=sys.stderr)
        for hit in hits:
            print(f"  {hit}", file=sys.stderr)
        print(
            "  The Firebase key lives on the host at /etc/lacteva/fcm-service-account.json "
            "and nowhere here. Remove it, and rotate the key if it was ever committed.",
            file=sys.stderr,
        )
        return 1
    print(f"check_secrets: no private key or service-account identity under {root.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
