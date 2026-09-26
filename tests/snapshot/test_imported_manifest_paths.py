"""Un manifest che arriva da un ``.jbk`` e' dato non fidato (CF10).

La guardia zip-slip di ``_extract_backup`` controlla i nomi **dello zip**, non i
percorsi scritti **dentro** i manifest dello store importato. Quei manifest
entrano nella storia locale al boot (``_merge_snapshot_store``), e ripristinarne
uno scriveva ogni ``entry.path`` sotto lo staging senza guardarlo: un ``..``
usciva dal workspace.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from jenny.config.schema import SnapshotConfig
from jenny.snapshot.backup import BackupError, BackupManager
from jenny.snapshot.engine import SnapshotEngine
from jenny.snapshot.locations import STAGED_SNAPSHOTS_DIR_NAME
from jenny.snapshot.service import SnapshotService
from jenny.snapshot.store import put_blob

_HASH = "a" * 64


def _env(tmp_path: Path) -> SimpleNamespace:
    runtime_root = tmp_path / "data"
    workspace = runtime_root / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "SOUL.md").write_text("anima", encoding="utf-8")
    engine = SnapshotEngine(workspace, runtime_root / "snapshots")
    service = SnapshotService(engine, SnapshotConfig(pbkdf2_iterations=100_000))
    return SimpleNamespace(manager=BackupManager(service), engine=engine,
                           runtime_root=runtime_root, tmp=tmp_path)


def _manifest(path: str, hash_hex: str = _HASH, snapshot_id: str = "b" * 64) -> bytes:
    return json.dumps({
        "id": snapshot_id, "created_at_ms": 1, "trigger": "manual",
        "files": [{"path": path, "hash": hash_hex, "size": 1, "mtime_ns": 0}],
    }).encode("utf-8")


def _archive(manifest: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("metadata.json", b'{"format_version": 1}')
        archive.writestr("tree/SOUL.md", b"anima")
        archive.writestr(f"snapshots/manifests/{'b' * 64}.json", manifest)
    return buffer.getvalue()


@pytest.mark.parametrize("bad", ["../fuori.txt", "a/../../fuori.txt", "/etc/passwd", "", "a//b"])
def test_an_imported_manifest_with_an_unsafe_path_is_refused(tmp_path, bad) -> None:
    env = _env(tmp_path)

    with pytest.raises(BackupError, match="unsafe"):
        env.manager._extract_backup(_archive(_manifest(bad)))

    assert not (env.runtime_root / STAGED_SNAPSHOTS_DIR_NAME).exists()


def test_an_imported_manifest_with_a_hash_that_is_not_a_hash_is_refused(tmp_path) -> None:
    env = _env(tmp_path)

    with pytest.raises(BackupError, match="unsafe"):
        env.manager._extract_backup(_archive(_manifest("ok.txt", hash_hex="../../x")))


def test_a_sane_imported_manifest_is_staged(tmp_path) -> None:
    env = _env(tmp_path)

    env.manager._extract_backup(_archive(_manifest("memory/MEMORY.md")))

    assert (env.runtime_root / STAGED_SNAPSHOTS_DIR_NAME / "manifests").is_dir()


def test_restore_snapshot_refuses_a_path_outside_the_destination(tmp_path) -> None:
    """La guardia sul posto: anche un manifest arrivato da un'altra strada."""
    env = _env(tmp_path)
    content = b"payload"
    hash_hex = put_blob(env.engine.objects_dir, content)
    env.engine.manifests_dir.mkdir(parents=True, exist_ok=True)
    (env.engine.manifests_dir / f"{'b' * 64}.json").write_bytes(
        _manifest("../../fuori.txt", hash_hex=hash_hex)
    )
    dest = tmp_path / "staged" / "workspace"

    with pytest.raises(ValueError, match="unsafe"):
        env.engine.restore_snapshot("b" * 64, dest)

    assert not (tmp_path / "fuori.txt").exists()
    assert not list(tmp_path.rglob("fuori.txt"))
