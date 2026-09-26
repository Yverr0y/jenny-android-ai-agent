"""Le collezioni JSONL delle mini-app dopo un incidente, e i loro tetti."""

from __future__ import annotations

import json

from jenny.apps.manifest import AppAction
from jenny.apps.storage import execute_storage_action


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
