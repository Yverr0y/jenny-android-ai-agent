"""Gli identificatori della casa sono inglesi (terza revisione, HJ15).

La fase 2 del rinomino ne aveva lasciati alcuni, e due erano rinomini
sbagliati: ``BEYOND_NEWLINE`` era «oltre il capo» letto come «a capo», e
``beyondMeta`` era «oltre la meta'» letta come *meta*. La chiave i18n del
quaderno eliminato era rimasta ``eliminato``.

Il valore ``'piena'`` di ``pagesPort().state`` attraversa
``shared/apps-actions.js``: le due correzioni l'hanno rinominato ``'full'`` ognuna
dalla sua parte, e finche' la casa diceva ancora ``'piena'`` le pagine piene
non spegnevano piu' il «Metti come pagina». Qui si tiene che non torni.
"""

from __future__ import annotations

import json
import re

from support.js_harness import ASSETS, I18N_DIR

_GONE = {
    "home-app.js": ("_haComposer", "home.notebook.eliminato", "'piena'"),
    "home-notebook.js": ("'piena'",),
    "home-pages.js": ("BEYOND_NEWLINE",),
    "home-strip.js": ("beyondMeta",),
}

_LOCALS = {
    "home-pages.js": ("corrente",),
    "home-model.js": ("corrente",),
    "home-strip.js": ("fine",),
}


def test_the_renamed_identifiers_do_not_come_back() -> None:
    for name, words in _GONE.items():
        src = (ASSETS / name).read_text(encoding="utf-8")
        for word in words:
            assert word not in src, f"{word} e' tornato in {name}"
    for name, words in _LOCALS.items():
        src = (ASSETS / name).read_text(encoding="utf-8")
        for word in words:
            assert not re.search(rf"\b(?:const|let|var) {word}\b", src), f"{word} in {name}"


def test_the_deleted_notebook_toast_has_an_english_key_in_both_languages() -> None:
    for lang in ("it", "en"):
        locale = json.loads((I18N_DIR / f"{lang}.json").read_text(encoding="utf-8"))
        notebook = locale["home"]["notebook"]
        assert "deleted" in notebook, lang
        assert "eliminato" not in notebook, lang
    assert "i18n.t('home.notebook.deleted'" in (ASSETS / "home-app.js").read_text(encoding="utf-8")
