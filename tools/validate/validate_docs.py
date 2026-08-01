#!/usr/bin/env python3
"""Lacteva repository documentation validator.

Enforces machine-checkable rules from the repository standards:
  STD-0001  front matter completeness; layer/context keys where required
  STD-0002  document filename conventions
  STD-0003  ID/filename agreement; ID uniqueness; registered prefixes
  links     relative links resolve (skipping code fences, inline code,
            and template placeholder files)
  CAP model capability-ID cross-references resolve against CAP-0001

Exit code 0 = clean, 1 = violations found. Run from anywhere:
    python3 tools/validate/validate_docs.py [--root <repo-root>]
"""
import argparse
import os
import re
import sys

REGISTERED_PREFIXES = {
    "STD", "GOV", "TPL", "ADR", "DOM", "BRD", "PRD", "SRS", "CAP", "API",
    "DBD", "AIM", "EVT", "OPS", "QR",
    "CON", "BPR", "PSV", "PDT", "AGG", "ENT", "VAL", "REP", "POL", "SPC", "AGT",
    "PSP",
}
FRONT_MATTER_REQUIRED = ["id", "title", "type", "status", "version",
                         "created", "last-updated", "owner"]
VALID_STATUS = {"Draft", "In Review", "Approved", "Deprecated", "Superseded"}
# Types whose artifacts must carry `context:` front matter (domain tactical artifacts)
CONTEXT_REQUIRED_TYPES = {"agg", "ent", "val", "rep", "pol", "spc"}
# Files exempt from front matter (indexes are docs; these are infrastructure)
FM_EXEMPT = {"README.md", "CONTRIBUTING.md", "CHANGELOG.md",
             "PULL_REQUEST_TEMPLATE.md", "CODEOWNERS"}
# Auto-generated files: front matter required, change-log section not
# (their history is the generator run, recorded in front matter)
GENERATED = {"XREF.md"}

DOC_ID_RE = re.compile(r"^([A-Z]{2,4})-(\d{4})-[a-z0-9-]+\.md$")
CAP_ID_RE = re.compile(r"\b[A-Z]{3}\.[A-Z]{3}\.\d{2}\b")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+)(#[^)]*)?\)")
FENCE_RE = re.compile(r"```.*?```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def strip_code(text):
    return INLINE_CODE_RE.sub("", FENCE_RE.sub("", text))


def parse_front_matter(text):
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    fm = {}
    for line in parts[1].splitlines():
        m = re.match(r"^([a-z-]+):\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"')
    return fm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    args = ap.parse_args()
    root = args.root or os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

    errors = []
    md_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".git") and d != "node_modules"]
        md_files += [os.path.join(dirpath, f) for f in filenames
                     if f.endswith(".md")]
    md_files.sort()

    seen_ids = {}
    defined_caps = set()
    referenced_caps = {}

    for path in md_files:
        rel = os.path.relpath(path, root)
        base = os.path.basename(path)
        text = open(path, encoding="utf-8").read()
        is_template = "/02-templates/" in path.replace(os.sep, "/")

        # --- filename & prefix checks (STD-0002 / STD-0003) ---
        m = DOC_ID_RE.match(base)
        if m and m.group(1) not in REGISTERED_PREFIXES:
            errors.append(f"{rel}: unregistered document prefix '{m.group(1)}'")

        # --- front matter (STD-0001) ---
        fm = parse_front_matter(text)
        if base in FM_EXEMPT:
            pass
        elif fm is None:
            errors.append(f"{rel}: missing front matter")
        else:
            for key in FRONT_MATTER_REQUIRED:
                if key not in fm:
                    errors.append(f"{rel}: front matter missing '{key}'")
            if fm.get("status") and fm["status"] not in VALID_STATUS:
                errors.append(f"{rel}: invalid status '{fm['status']}'")
            if m:  # ID/filename agreement + uniqueness
                fid = f"{m.group(1)}-{m.group(2)}"
                if fm.get("id") != fid:
                    errors.append(f"{rel}: front matter id '{fm.get('id')}' "
                                  f"!= filename id '{fid}'")
                if fid in seen_ids:
                    errors.append(f"{rel}: duplicate ID {fid} "
                                  f"(also {seen_ids[fid]})")
                seen_ids.setdefault(fid, rel)
            if (not is_template and fm.get("type") in CONTEXT_REQUIRED_TYPES
                    and not fm.get("context")):
                errors.append(f"{rel}: type '{fm['type']}' requires "
                              f"'context:' front matter")
            # Revision history: every front-mattered doc carries a Change Log
            if base not in GENERATED and "## Change Log" not in text:
                errors.append(f"{rel}: missing '## Change Log' section "
                              f"(STD-0001 revision-history rule)")
            # Status/version coherence (STD-0004: drafts are 0.x,
            # approved docs are >= 1.0)
            ver = fm.get("version", "")
            vm = re.match(r"^(\d+)\.(\d+)$", ver)
            if vm:
                major = int(vm.group(1))
                if fm.get("status") == "Draft" and major >= 1:
                    errors.append(f"{rel}: status Draft but version {ver} "
                                  f"(drafts are 0.x per STD-0004)")
                if fm.get("status") == "Approved" and major < 1:
                    errors.append(f"{rel}: status Approved but version {ver} "
                                  f"(approved docs are >= 1.0 per STD-0004)")
            elif "version" in fm:
                errors.append(f"{rel}: version '{ver}' not MAJOR.MINOR")

        # --- links (skip fences/inline code; templates hold placeholders) ---
        if not is_template:
            for lm in LINK_RE.finditer(strip_code(text)):
                target = lm.group(1)
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                if "<" in target or "NNNN" in target:
                    continue  # placeholder pattern
                resolved = os.path.normpath(
                    os.path.join(os.path.dirname(path), target))
                if not os.path.exists(resolved):
                    errors.append(f"{rel}: broken link -> {target}")

        # --- capability IDs ---
        if "/05-capabilities/" in path.replace(os.sep, "/"):
            defined_caps.update(
                re.findall(r"^### ([A-Z]{3}\.[A-Z]{3}\.\d{2}) — ",
                           text, re.M))
        for cid in CAP_ID_RE.findall(strip_code(text)):
            referenced_caps.setdefault(cid, rel)

    for cid, where in sorted(referenced_caps.items()):
        if cid not in defined_caps:
            errors.append(f"{where}: dangling capability reference {cid}")

    if errors:
        print(f"FAIL — {len(errors)} violation(s):")
        for e in errors:
            print(f"  {e}")
        return 1
    print(f"OK — {len(md_files)} markdown files, "
          f"{len(seen_ids)} document IDs, "
          f"{len(defined_caps)} capabilities: all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
