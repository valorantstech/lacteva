"""WO-77 — the gate refuses a service-account secret anywhere in the tree.

`tools/validate/check_secrets.py` is what stands between the Firebase key and
a public git history. Proven the way every guard here is proven: it must
REFUSE — a synthesised key in a scratch tree fails it, by file and line — and
it must pass the repository as it is.
"""

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
GUARD = ROOT / "tools" / "validate" / "check_secrets.py"


def _run(target: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GUARD), str(target)], capture_output=True, text=True, check=False
    )


def _marker(*parts: str) -> str:
    # Assembled at runtime so this test file does not itself trip the guard.
    return "".join(parts)


def test_a_synthesised_key_is_refused_by_file_and_line(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.md").write_text("nothing to see\n")
    key = tmp_path / "docs" / "innocent-name.json"
    key.write_text(
        '{"type": "service_account", "private_key": "'
        + _marker("-----BEGIN ", "PRIVATE KEY-----")
        + '\\nMIIE..."}\n'
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "docs/innocent-name.json:1" in result.stderr
    assert "rotate the key" in result.stderr

    key.write_text('{"client_email": "x@proj' + _marker(".iam.", "gserviceaccount.com") + '"}\n')
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "gserviceaccount" in result.stderr


def test_a_key_under_an_ignored_build_directory_is_still_not_the_tree_s_problem(tmp_path):
    # node_modules and friends are skipped: the guard is about what is
    # COMMITTED, and those directories never are.
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "k.json").write_text(_marker("-----BEGIN ", "PRIVATE KEY-----"))
    assert _run(tmp_path).returncode == 0


def test_the_repository_passes():
    result = _run(ROOT)
    assert result.returncode == 0, result.stderr


def test_the_two_file_names_are_ignored_by_git():
    ignore = (ROOT / ".gitignore").read_text()
    assert "*fcm-service-account*.json" in ignore
    assert "*firebase-adminsdk*.json" in ignore
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "tools/validate/check_secrets.py" in ci
