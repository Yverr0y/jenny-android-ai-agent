"""I comandi ``workspace.delete``/``rename``/``copy`` del file manager.

Fino al 26/09/2026 erano tre GET di ``/api/workspace/*``: scritture sul disco
su una superficie che ``.agent/design.md`` vuole di sola lettura. Decisione D3
della terza revisione: sono comandi dell'RPC WebSocket (``webui/commands.py``),
come ``project.delete`` e ``page.write``. I test delle rotte che restano sono in
``tests/webui/test_workspace_routes.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jenny.config.loader import load_config, save_config
from jenny.config.schema import Config
from jenny.runtime.context import get_runtime_context
from jenny.webui.commands import CommandContext, CommandError, dispatch_command


@pytest.fixture()
def workspace_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    return root


@pytest.fixture()
def config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "config.json"
    save_config(Config(), path)
    monkeypatch.setattr(get_runtime_context(), "config_path", path)
    return path


@pytest.fixture()
def ctx(workspace_root: Path) -> CommandContext:
    return CommandContext(
        get_workspace_root=lambda: workspace_root,
        invalidate_session=lambda _key: None,
        busy_session_keys=lambda: (),
    )


def _set_workspace_config(config_path: Path, **overrides) -> None:
    config = load_config(config_path)
    for key, value in overrides.items():
        setattr(config.workspace, key, value)
    save_config(config, config_path)


async def _refused(ctx: CommandContext, method: str, params: dict) -> CommandError:
    with pytest.raises(CommandError) as exc:
        await dispatch_command(ctx, method, params)
    return exc.value


# ---------------------------------------------------------------------------
# workspace.delete
# ---------------------------------------------------------------------------


async def test_delete_removes_a_file(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    (workspace_root / "gone.txt").write_text("z", encoding="utf-8")
    result = await dispatch_command(ctx, "workspace.delete", {"path": "gone.txt"})
    assert result == {"success": True, "path": "gone.txt"}
    assert not (workspace_root / "gone.txt").exists()


async def test_delete_removes_a_folder(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    (workspace_root / "cartella" / "dentro").mkdir(parents=True)
    (workspace_root / "cartella" / "dentro" / "f.txt").write_text("z", encoding="utf-8")
    await dispatch_command(ctx, "workspace.delete", {"path": "cartella"})
    assert not (workspace_root / "cartella").exists()


async def test_delete_requires_allow_delete(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    _set_workspace_config(config_path, allow_delete=False)
    (workspace_root / "gone.txt").write_text("z", encoding="utf-8")
    err = await _refused(ctx, "workspace.delete", {"path": "gone.txt"})
    assert err.code == "forbidden"
    assert (workspace_root / "gone.txt").exists()


async def test_delete_fails_closed_when_config_raises(
    ctx: CommandContext, workspace_root: Path, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (workspace_root / "keep.txt").write_text("stay", encoding="utf-8")

    def _boom(*args, **kwargs):
        raise RuntimeError("config unreadable")

    monkeypatch.setattr("jenny.config.loader.load_config", _boom)
    err = await _refused(ctx, "workspace.delete", {"path": "keep.txt"})
    assert err.code == "unavailable"
    assert (workspace_root / "keep.txt").exists()


async def test_delete_missing_path_is_not_found(ctx: CommandContext, config_path: Path) -> None:
    err = await _refused(ctx, "workspace.delete", {"path": "missing.txt"})
    assert err.code == "not_found"


async def test_delete_refuses_path_traversal(
    ctx: CommandContext, tmp_path: Path, config_path: Path
) -> None:
    (tmp_path / "fuori.txt").write_text("resta", encoding="utf-8")
    err = await _refused(ctx, "workspace.delete", {"path": "../fuori.txt"})
    assert err.code == "bad_request"
    assert (tmp_path / "fuori.txt").exists()


async def test_delete_refuses_a_project(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    """Un progetto si cancella con ``project.delete``: la ``rmtree`` da sola
    lascerebbe la sua conversazione sotto un nome libero."""
    (workspace_root / "wikis" / "orto" / "wiki").mkdir(parents=True)
    (workspace_root / "wikis" / "orto" / "wiki" / "index.md").write_text("# o", encoding="utf-8")
    err = await _refused(ctx, "workspace.delete", {"path": "wikis/orto"})
    assert err.code == "forbidden"
    assert "file browser" in err.message
    assert (workspace_root / "wikis" / "orto" / "wiki").is_dir()


# ---------------------------------------------------------------------------
# workspace.rename
# ---------------------------------------------------------------------------


async def test_rename_moves_a_file(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    (workspace_root / "old.txt").write_text("z", encoding="utf-8")
    await dispatch_command(
        ctx, "workspace.rename", {"old_path": "old.txt", "new_path": "new.txt"}
    )
    assert not (workspace_root / "old.txt").exists()
    assert (workspace_root / "new.txt").read_text(encoding="utf-8") == "z"


async def test_rename_missing_source_is_not_found(ctx: CommandContext, config_path: Path) -> None:
    err = await _refused(
        ctx, "workspace.rename", {"old_path": "missing.txt", "new_path": "new.txt"}
    )
    assert err.code == "not_found"


async def test_rename_needs_both_paths(ctx: CommandContext, config_path: Path) -> None:
    err = await _refused(ctx, "workspace.rename", {"old_path": "a.txt"})
    assert err.code == "bad_request"


# ---------------------------------------------------------------------------
# workspace.copy
# ---------------------------------------------------------------------------


async def test_copy_to_a_destination(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    (workspace_root / "src.txt").write_text("dati", encoding="utf-8")
    result = await dispatch_command(ctx, "workspace.copy", {"path": "src.txt", "dest": "dst.txt"})
    assert result["dest"] == "dst.txt"
    assert (workspace_root / "dst.txt").read_text(encoding="utf-8") == "dati"
    assert (workspace_root / "src.txt").exists()


async def test_copy_without_dest_goes_next_to_the_original(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    """Il «Duplica» del file manager non manda ``dest``. La rotta di prima copiava
    nella radice: un file della radice finiva su se stesso, e non funzionava mai."""
    (workspace_root / "note").mkdir()
    (workspace_root / "note" / "a.md").write_text("uno", encoding="utf-8")
    (workspace_root / "b.md").write_text("due", encoding="utf-8")

    first = await dispatch_command(ctx, "workspace.copy", {"path": "note/a.md"})
    second = await dispatch_command(ctx, "workspace.copy", {"path": "note/a.md"})
    root_file = await dispatch_command(ctx, "workspace.copy", {"path": "b.md"})
    folder = await dispatch_command(ctx, "workspace.copy", {"path": "note"})

    assert first["dest"] == "note/a (copy).md"
    assert second["dest"] == "note/a (copy 2).md"
    assert root_file["dest"] == "b (copy).md"
    assert folder["dest"] == "note (copy)"
    assert (workspace_root / "note" / "a (copy 2).md").read_text(encoding="utf-8") == "uno"
    assert (workspace_root / "note (copy)" / "a.md").read_text(encoding="utf-8") == "uno"


async def test_copy_rejects_an_empty_dest(ctx: CommandContext, workspace_root: Path, config_path: Path) -> None:
    (workspace_root / "src.txt").write_text("dati", encoding="utf-8")
    err = await _refused(ctx, "workspace.copy", {"path": "src.txt", "dest": ""})
    assert err.code == "bad_request"
