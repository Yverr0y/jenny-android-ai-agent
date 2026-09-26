"""Le collezioni JSONL delle mini-app dopo un incidente, e i loro tetti."""

from __future__ import annotations

import json

import pytest

from jenny.apps.manifest import AppAction
from jenny.apps.storage import StorageError, execute_storage_action


def _action(op: str) -> AppAction:
    return AppAction(name=f"{op}_x", description="t", kind="storage", op=op, collection="notes")


def _file(app_dir):
    return app_dir / "data" / "notes.jsonl"


async def test_an_append_after_a_line_cut_short_keeps_the_new_record(tmp_path) -> None:
    """CF7: un append interrotto lascia una riga senza a capo, e il successivo le si
    attaccava: la riga unita non si legge, e spariva anche il record nuovo."""
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('{"id": "aaa", "testo": "intero"}\n{"id": "bbb", "tes', encoding="utf-8")

    result = await execute_storage_action(tmp_path, _action("append"), {"testo": "nuovo"})

    records = (await execute_storage_action(tmp_path, _action("query"), {}))["records"]
    assert [r["id"] for r in records] == ["aaa", result["record"]["id"]]
    assert path.read_text(encoding="utf-8").endswith(json.dumps(result["record"],
                                                                ensure_ascii=False) + "\n")


async def test_an_append_to_a_clean_file_adds_no_blank_line(tmp_path) -> None:
    await execute_storage_action(tmp_path, _action("append"), {"n": 1})
    await execute_storage_action(tmp_path, _action("append"), {"n": 2})

    assert "\n\n" not in _file(tmp_path).read_text(encoding="utf-8")


async def test_update_respects_the_collection_size_cap(tmp_path) -> None:
    """CF11: ``append`` e ``set`` rifiutano una collezione oltre il tetto, ``update``
    no: bastava aggiornare lo stesso record con un campo enorme per farla crescere
    senza limite."""
    first = await execute_storage_action(tmp_path, _action("append"), {"testo": "x"})
    record_id = first["record"]["id"]
    _file(tmp_path).write_text(
        _file(tmp_path).read_text(encoding="utf-8") + "#" * 100 + "\n", encoding="utf-8"
    )

    with pytest.raises(StorageError) as refused:
        await execute_storage_action(
            tmp_path, _action("update"), {"id": record_id, "testo": "y" * 10}, max_bytes=50
        )

    assert refused.value.status == 413


async def test_delete_still_works_on_a_collection_over_the_cap(tmp_path) -> None:
    """Il tetto ferma la crescita, non la pulizia."""
    first = await execute_storage_action(tmp_path, _action("append"), {"testo": "x" * 100})

    result = await execute_storage_action(
        tmp_path, _action("delete"), {"id": first["record"]["id"]}, max_bytes=50
    )

    assert result["deleted"] == first["record"]["id"]
