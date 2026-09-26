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


# ---------------------------------------------------------------------------
# WA3: la radice, la cartella dei quaderni e i loro antenati non si cancellano
# ---------------------------------------------------------------------------


def _notebook(workspace_root: Path, rel: str = "wikis/orto") -> Path:
    pages = workspace_root / rel / "wiki"
    pages.mkdir(parents=True)
    (pages / "index.md").write_text("# o", encoding="utf-8")
    return pages


@pytest.mark.parametrize("path", [".", "./", "sub/..", "./sub/../."])
async def test_delete_refuses_the_workspace_root(
    ctx: CommandContext, workspace_root: Path, config_path: Path, path: str
) -> None:
    """``path=.`` faceva la ``rmtree`` della radice del workspace (terza
    revisione, WA3): config, sessioni, memoria, tutto."""
    (workspace_root / "sub").mkdir()
    (workspace_root / "USER.md").write_text("io", encoding="utf-8")
    err = await _refused(ctx, "workspace.delete", {"path": path})
    assert err.code == "forbidden"
    assert (workspace_root / "USER.md").exists()


@pytest.mark.parametrize("path", ["", "   "])
async def test_delete_refuses_an_empty_path(
    ctx: CommandContext, workspace_root: Path, config_path: Path, path: str
) -> None:
    (workspace_root / "USER.md").write_text("io", encoding="utf-8")
    err = await _refused(ctx, "workspace.delete", {"path": path})
    assert err.code == "bad_request"
    assert (workspace_root / "USER.md").exists()


@pytest.mark.parametrize("path", ["wikis", "wikis/", "wikis/."])
async def test_delete_refuses_the_notebooks_folder(
    ctx: CommandContext, workspace_root: Path, config_path: Path, path: str
) -> None:
    """Il rifiuto dei progetti guardava solo i figli diretti di ``wikis/``:
    ``path=wikis`` cancellava tutti i quaderni insieme, lasciando ogni chat
    orfana."""
    pages = _notebook(workspace_root)
    err = await _refused(ctx, "workspace.delete", {"path": path})
    assert err.code == "forbidden"
    assert "orto" in err.message
    assert pages.is_dir()


async def test_delete_refuses_any_ancestor_of_a_notebook(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    config = load_config(config_path)
    config.wiki.wikis_dir = "archivio/wikis"
    save_config(config, config_path)
    pages = _notebook(workspace_root, "archivio/wikis/orto")
    err = await _refused(ctx, "workspace.delete", {"path": "archivio"})
    assert err.code == "forbidden"
    assert pages.is_dir()


async def test_delete_allows_a_folder_that_holds_no_notebook(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    """Il rifiuto e' per chi *contiene* un quaderno, non per ogni cartella."""
    _notebook(workspace_root)
    (workspace_root / "output" / "vecchio").mkdir(parents=True)
    await dispatch_command(ctx, "workspace.delete", {"path": "output"})
    assert not (workspace_root / "output").exists()


async def test_delete_allows_a_notebooks_folder_without_notebooks(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    (workspace_root / "wikis" / "appunti-sparsi").mkdir(parents=True)
    await dispatch_command(ctx, "workspace.delete", {"path": "wikis"})
    assert not (workspace_root / "wikis").exists()


# ---------------------------------------------------------------------------
# WA4: rinomina e copia non spostano quaderni, non sovrascrivono, e rispettano
# ``workspace.allow_write``
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("wikis/orto", "wikis/giardino"),
        ("wikis/orto/wiki", "wikis/orto/pagine"),
        ("wikis", "quaderni"),
    ],
)
async def test_rename_refuses_to_move_a_notebook(
    ctx: CommandContext, workspace_root: Path, config_path: Path, old: str, new: str
) -> None:
    """Il rinomino dal file manager spostava la cartella e lasciava la chat sotto
    il nome vecchio (terza revisione, WA4): si fa con ``project.rename``."""
    pages = _notebook(workspace_root)
    err = await _refused(ctx, "workspace.rename", {"old_path": old, "new_path": new})
    assert err.code == "forbidden"
    assert "Notebooks" in err.message
    assert pages.is_dir()
    assert not (workspace_root / new).exists()


async def test_rename_refuses_the_workspace_root(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    err = await _refused(ctx, "workspace.rename", {"old_path": ".", "new_path": "altro"})
    assert err.code == "forbidden"
    assert workspace_root.is_dir()


async def test_rename_does_not_overwrite_a_file(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    """``Path.rename`` su POSIX sostituisce in silenzio la destinazione."""
    (workspace_root / "a.txt").write_text("a", encoding="utf-8")
    (workspace_root / "b.txt").write_text("b", encoding="utf-8")
    err = await _refused(ctx, "workspace.rename", {"old_path": "a.txt", "new_path": "b.txt"})
    assert err.code == "name_taken"
    assert (workspace_root / "a.txt").read_text(encoding="utf-8") == "a"
    assert (workspace_root / "b.txt").read_text(encoding="utf-8") == "b"


async def test_rename_does_not_replace_an_empty_folder(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    (workspace_root / "a").mkdir()
    (workspace_root / "a" / "f.txt").write_text("a", encoding="utf-8")
    (workspace_root / "vuota").mkdir()
    err = await _refused(ctx, "workspace.rename", {"old_path": "a", "new_path": "vuota"})
    assert err.code == "name_taken"
    assert (workspace_root / "a" / "f.txt").exists()


async def test_rename_can_change_only_the_case(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    """Su un disco che non distingue le maiuscole la destinazione «esiste»: e' lo
    stesso file, e cambiargli il nome resta lecito."""
    (workspace_root / "nota.txt").write_text("n", encoding="utf-8")
    await dispatch_command(ctx, "workspace.rename", {"old_path": "nota.txt", "new_path": "Nota.txt"})
    assert [p.name for p in workspace_root.iterdir()] == ["Nota.txt"]


async def test_rename_requires_allow_write(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    _set_workspace_config(config_path, allow_write=False)
    (workspace_root / "a.txt").write_text("a", encoding="utf-8")
    err = await _refused(ctx, "workspace.rename", {"old_path": "a.txt", "new_path": "b.txt"})
    assert err.code == "forbidden"
    assert (workspace_root / "a.txt").exists()


async def test_copy_requires_allow_write(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    _set_workspace_config(config_path, allow_write=False)
    (workspace_root / "a.txt").write_text("a", encoding="utf-8")
    err = await _refused(ctx, "workspace.copy", {"path": "a.txt", "dest": "b.txt"})
    assert err.code == "forbidden"
    assert not (workspace_root / "b.txt").exists()


async def test_copy_does_not_overwrite_a_file(
    ctx: CommandContext, workspace_root: Path, config_path: Path
) -> None:
    """``shutil.copy2`` sostituisce in silenzio la destinazione."""
    (workspace_root / "a.txt").write_text("a", encoding="utf-8")
    (workspace_root / "b.txt").write_text("b", encoding="utf-8")
    err = await _refused(ctx, "workspace.copy", {"path": "a.txt", "dest": "b.txt"})
    assert err.code == "name_taken"
    assert (workspace_root / "b.txt").read_text(encoding="utf-8") == "b"


# ---------------------------------------------------------------------------
# WA5: cancellare e rinominare un link agisce sul link, non su cosa indica
# ---------------------------------------------------------------------------


@pytest.fixture()
def linked(workspace_root: Path, tmp_path: Path) -> dict[str, Path]:
    """Una cartella vera dentro, una fuori, e un link verso ciascuna."""
    import os

    inside = workspace_root / "vera"
    inside.mkdir()
    (inside / "dato.txt").write_text("resta", encoding="utf-8")
    outside = tmp_path / "fuori"
    outside.mkdir()
    (outside / "segreto.txt").write_text("resta", encoding="utf-8")
    os.symlink(inside, workspace_root / "link-dentro")
    os.symlink(outside, workspace_root / "link-fuori")
    os.symlink(tmp_path / "non-esiste", workspace_root / "link-pendente-fuori")
    return {"inside": inside, "outside": outside}


@pytest.mark.parametrize("name", ["link-dentro", "link-fuori", "link-pendente-fuori"])
async def test_delete_removes_the_link_not_its_target(
    ctx: CommandContext, workspace_root: Path, config_path: Path, linked, name: str
) -> None:
    """La ``rmtree`` seguiva il link: cancellare ``link-dentro`` svuotava la
    cartella vera (terza revisione, WA5); un link verso fuori non si poteva
    cancellare affatto, perche' il gate risolveva il bersaglio."""
    import os

    await dispatch_command(ctx, "workspace.delete", {"path": name})
    assert not os.path.lexists(workspace_root / name)
    assert (linked["inside"] / "dato.txt").read_text(encoding="utf-8") == "resta"
    assert (linked["outside"] / "segreto.txt").read_text(encoding="utf-8") == "resta"


async def test_rename_moves_the_link_not_its_target(
    ctx: CommandContext, workspace_root: Path, config_path: Path, linked
) -> None:
    import os

    await dispatch_command(
        ctx, "workspace.rename", {"old_path": "link-dentro", "new_path": "altro-link"}
    )
    assert not os.path.lexists(workspace_root / "link-dentro")
    assert os.path.islink(workspace_root / "altro-link")
    assert (linked["inside"] / "dato.txt").exists()
    assert [p.name for p in workspace_root.iterdir() if p.name == "vera"] == ["vera"]


async def test_rename_of_a_link_pointing_outside_is_the_link(
    ctx: CommandContext, workspace_root: Path, config_path: Path, linked
) -> None:
    import os

    await dispatch_command(
        ctx, "workspace.rename", {"old_path": "link-fuori", "new_path": "rinominato"}
    )
    assert os.path.islink(workspace_root / "rinominato")
    assert (linked["outside"] / "segreto.txt").exists()


async def test_the_link_path_still_cannot_climb_out(
    ctx: CommandContext, workspace_root: Path, tmp_path: Path, config_path: Path
) -> None:
    """Agire sul link non apre il confine: il *genitore* passa dal gate."""
    (tmp_path / "vittima.txt").write_text("resta", encoding="utf-8")
    for path in ("../vittima.txt", "link-nessuno/../../vittima.txt"):
        err = await _refused(ctx, "workspace.delete", {"path": path})
        assert err.code in ("bad_request", "not_found")
    assert (tmp_path / "vittima.txt").exists()


async def test_copying_a_folder_keeps_its_links_as_links(
    ctx: CommandContext, workspace_root: Path, config_path: Path, linked
) -> None:
    """``copytree`` seguiva i link: una cartella con un link verso fuori portava
    dentro il workspace una copia di quel che c'era fuori."""
    import os

    folder = workspace_root / "album"
    folder.mkdir()
    os.symlink(linked["outside"], folder / "scorciatoia")
    await dispatch_command(ctx, "workspace.copy", {"path": "album", "dest": "album2"})
    assert os.path.islink(workspace_root / "album2" / "scorciatoia")
