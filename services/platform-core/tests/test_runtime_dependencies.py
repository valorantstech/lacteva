"""Every import under src/ is something the production image has (WO-106 · LACTEVA-BUILD-002).

The 4b46e15 deploy rolled back: `turnstile.py` imported httpx, which was a
dev-group extra (FastAPI's TestClient pulls it in), so every one of 2,747
tests passed in the venv and the production image — built with
`uv sync --no-dev` — could not import the app. The image BUILD succeeded,
because building never imports anything.

Two guards, so this class of defect fails CI and not a deploy: this static
check, and the image-run step in `.github/workflows/images.yml`.

This walks every module under `src/platform_core` with `ast`, collects every
imported top-level name — at module level AND inside functions, which is
where fcm.py and providers.py import httpx — and asserts each is the
standard library, the package itself, or a distribution the production
image installs — `[project.dependencies]` and what they require, with
extras' markers honoured — never something only the dev group brings. The module → distribution
map comes from the venv's own metadata, so `jwt` is PyJWT and `yaml` is
PyYAML without a hand-kept table.
"""

from __future__ import annotations

import ast
import importlib.metadata
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "platform_core"


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared(section: list[str]) -> set[str]:
    return {_normalise(re.split(r"[\[<>=!~; ]", spec, maxsplit=1)[0]) for spec in section}


_IMPORT_GUARDS = {"ImportError", "ModuleNotFoundError", "Exception"}


def _guarded(tree: ast.AST) -> set[int]:
    """Line numbers of imports inside a `try` that catches ImportError — an
    OPTIONAL dependency the code lives without (the OTel hook), which is a
    different thing from a missing one."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        caught = set()
        for handler in node.handlers:
            if handler.type is None:
                caught.add("Exception")
            for name in ast.walk(handler.type) if handler.type else []:
                if isinstance(name, ast.Name):
                    caught.add(name.id)
        if caught & _IMPORT_GUARDS:
            for inner in node.body:
                for sub in ast.walk(inner):
                    if isinstance(sub, ast.Import | ast.ImportFrom):
                        lines.add(sub.lineno)
    return lines


def _imports(path: pathlib.Path) -> set[tuple[str, int]]:
    tree = ast.parse(path.read_text(), filename=str(path))
    guarded = _guarded(tree)
    found: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        if node.lineno in guarded if hasattr(node, "lineno") else False:
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add((alias.name.split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add((node.module.split(".")[0], node.lineno))
    return found


def _runtime_closure(declared: list[str]) -> set[str]:
    """Every distribution the production image installs: the declared
    dependencies and, recursively, what THEY require — with each
    requirement's environment marker evaluated for the extras that were
    actually asked for (`pyjwt[crypto]` brings cryptography; plain `fastapi`
    does not bring `fastapi[standard]`'s httpx)."""
    from packaging.requirements import Requirement

    closure: set[str] = set()
    queue: list[tuple[str, frozenset[str]]] = []
    for spec in declared:
        req = Requirement(spec)
        queue.append((req.name, frozenset(req.extras)))
    while queue:
        name, extras = queue.pop()
        key = _normalise(name)
        if key in closure:
            continue
        closure.add(key)
        try:
            requires = importlib.metadata.requires(name) or []
        except importlib.metadata.PackageNotFoundError:
            continue
        for line in requires:
            req = Requirement(line)
            if req.marker is not None:
                wanted = any(req.marker.evaluate({"extra": extra}) for extra in extras or {""})
                if not wanted and not req.marker.evaluate({"extra": ""}):
                    continue
            queue.append((req.name, frozenset(req.extras)))
    return closure


def offenders_for(declared: list[str], dev_group: list[str]) -> list[str]:
    """Every import under src/ that an image built from `declared` would not
    have — a function, so the check can be shown to refuse."""
    runtime = _runtime_closure(declared)
    dev = _declared(dev_group)
    provided = importlib.metadata.packages_distributions()
    stdlib = set(sys.stdlib_module_names)

    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        for module, lineno in _imports(path):
            if module in stdlib or module == "platform_core" or module.startswith("_"):
                continue
            distributions = {_normalise(d) for d in provided.get(module, [])}
            if not distributions:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno} imports {module!r}, which no installed "
                    "distribution provides"
                )
                continue
            if not distributions & runtime:
                where = "the dev group" if distributions & dev else "nothing"
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno} imports {module!r} "
                    f"({', '.join(sorted(distributions))}) — declared by {where}, not by "
                    "[project.dependencies] or anything they require; the production image "
                    "will not have it"
                )
    return offenders


def _project() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_every_runtime_import_is_a_declared_runtime_dependency():
    project = _project()
    offenders = offenders_for(
        project["project"]["dependencies"], project.get("dependency-groups", {}).get("dev", [])
    )
    assert offenders == [], "\n".join(offenders)


def test_the_check_refuses_the_import_that_rolled_the_deploy_back():
    """The proof can refuse: with httpx back in the dev group and out of the
    runtime list — 4b46e15's pyproject — turnstile.py, fcm.py and the HTTP
    providers are all reported, by file and line."""
    project = _project()
    runtime = [d for d in project["project"]["dependencies"] if not d.startswith("httpx")]
    dev = [*project["dependency-groups"]["dev"], "httpx>=0.27"]
    offenders = offenders_for(runtime, dev)
    files = {line.split(":")[0] for line in offenders}
    assert "src/platform_core/core/turnstile.py" in files, offenders
    assert "src/platform_core/modules/notification/fcm.py" in files
    assert "src/platform_core/modules/notification/providers.py" in files
    assert all("'httpx'" in line and "the dev group" in line for line in offenders), offenders


def test_httpx_is_a_runtime_dependency_by_name():
    """The one that rolled a deploy back, pinned by name so the general check
    above cannot be weakened without this saying so."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert "httpx" in _declared(project["project"]["dependencies"])
    assert "httpx" not in _declared(project["dependency-groups"]["dev"])


def test_the_image_is_run_in_ci_not_just_built():
    """The other guard: after CI builds the platform image it RUNS it —
    imports the app and every module under it, then starts it against a
    PostgreSQL and asks /health/live. A missing runtime dependency fails CI."""
    workflow = (ROOT.parents[1] / ".github/workflows/images.yml").read_text()
    assert "import platform_core.main" in workflow
    assert "pkgutil.walk_packages" in workflow
    assert "/health/live" in workflow
    # And it runs against the image that was PUSHED, under the same tag.
    assert "docker run --rm" in workflow and "docker pull" in workflow
