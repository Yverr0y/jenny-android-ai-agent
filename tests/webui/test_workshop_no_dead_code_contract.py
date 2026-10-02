"""Niente import mai usati, niente metodi vuoti tenuti in vita da nessuno.

``batteryExemptionNeeded`` importato e
mai chiamato in ``mobile-settings.js``, ``isOpenableProjectName`` in
``shared/scope-chip.js``, un ``_voiceTimerInterval`` scritto e mai letto e un
``handleAction(action) {}`` vuoto in ``mobile-chat.js`` (il guscio lo chiama
solo se c'e': ``mobile-header.js``). Il controllo sugli import e' generale,
per i file dell'officina e di ``shared/``: un nome importato deve comparire
anche fuori dalla riga che lo importa.
"""

from __future__ import annotations

import re

import pytest
from support.js_harness import ASSETS

_FILES = sorted(
    [p for p in ASSETS.glob("mobile-*.js")] + [p for p in (ASSETS / "shared").glob("*.js")]
)
_IMPORT = re.compile(r"^import\s+\{([^}]*)\}\s+from\s+['\"][^'\"]+['\"];?", re.M)


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"(?m)(^|[^:'\"\\])//.*$", r"\1", src)


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.relative_to(ASSETS).as_posix())
def test_every_imported_name_is_used(path) -> None:
    src = path.read_text(encoding="utf-8", errors="replace")
    body = _strip_comments(_IMPORT.sub(" ", src))
    unused = []
    for block in _IMPORT.findall(src):
        for spec in block.split(","):
            spec = spec.strip()
            if not spec:
                continue
            local = spec.split(" as ")[-1].strip()
            # Non dopo un punto (`obj.name` e' un altro nome), ma si' dopo uno
            # spread (`...NAME`).
            if not re.search(rf"(?:(?<![\w$.])|(?<=\.\.\.)){re.escape(local)}(?![\w$])", body):
                unused.append(local)
    assert not unused, f"import mai usati: {unused}"


def test_the_dead_members_are_gone() -> None:
    chat = (ASSETS / "mobile-chat.js").read_text(encoding="utf-8", errors="replace")
    assert "_voiceTimerInterval" not in chat
    assert not re.search(r"\n  handleAction\([^)]*\)\s*\{\s*\}", chat)
