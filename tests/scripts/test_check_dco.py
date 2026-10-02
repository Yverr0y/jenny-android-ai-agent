"""``scripts/check_dco.sh`` conta solo il trailer vero, non una riga qualunque.

La versione precedente cercava ``Signed-off-by: <autore>`` in *tutto* il
messaggio: una firma citata nel corpo, o seguita da altra prosa (quindi non piu'
un trailer), passava. Qui lo script gira davvero, su un repo usa-e-getta in
``tmp_path``, con un commit per ogni caso.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_dco.sh"
AUTHOR = "Alice Example <alice@example.com>"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("bash") is None,
    reason="servono git e bash",
)


def _git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Alice Example",
        "GIT_AUTHOR_EMAIL": "alice@example.com",
        "GIT_COMMITTER_NAME": "Alice Example",
        "GIT_COMMITTER_EMAIL": "alice@example.com",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env=env, check=True
    )
    return proc.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "base")
    return tmp_path


def _check(repo: Path, message: str) -> subprocess.CompletedProcess[str]:
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return subprocess.run(
        ["bash", str(SCRIPT), base, "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def test_a_real_trailer_passes(repo: Path) -> None:
    proc = _check(repo, f"Add a thing\n\nWhy it matters.\n\nSigned-off-by: {AUTHOR}\n")
    assert proc.returncode == 0, proc.stdout
    assert proc.stdout.startswith("ok ")


def test_the_key_is_case_insensitive(repo: Path) -> None:
    proc = _check(repo, f"Add a thing\n\nsigned-off-by: {AUTHOR}\n")
    assert proc.returncode == 0, proc.stdout


def test_a_sign_off_quoted_in_the_body_is_not_a_trailer(repo: Path) -> None:
    # Il trailer e' l'ultimo paragrafo: una riga citata in un paragrafo prima,
    # seguito da altra prosa, non lo e' (per git stesso, `interpret-trailers`).
    message = (
        "Explain the DCO\n\n"
        f"Signed-off-by: {AUTHOR}\n\n"
        "That is the line CONTRIBUTING.md asks for; this commit only quotes it.\n"
    )
    proc = _check(repo, message)
    assert proc.returncode == 1, proc.stdout
    assert "FAIL" in proc.stdout


def test_a_trailer_that_only_contains_the_author_fails(repo: Path) -> None:
    proc = _check(repo, f"Add a thing\n\nSigned-off-by: {AUTHOR} and someone else\n")
    assert proc.returncode == 1, proc.stdout


def test_a_sign_off_by_someone_else_fails(repo: Path) -> None:
    proc = _check(repo, "Add a thing\n\nSigned-off-by: Bob Example <bob@example.com>\n")
    assert proc.returncode == 1, proc.stdout
    assert f"missing: Signed-off-by: {AUTHOR}" in proc.stdout
