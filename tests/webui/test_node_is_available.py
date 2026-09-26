"""In CI le prove che eseguono il JS reale devono girare, non saltare.

Una ventina di suite della WebUI (`*_client.py`, più il contratto del grafo)
lanciano `node` sugli asset veri e sono sotto `skipif`. Un salto è la risposta
giusta sulla macchina di chi sviluppa e non ha node; in CI invece è una
sparizione — e una sparizione **in verde**, che è il modo peggiore di perdere
copertura: nessuno la nota finché non serve.

Prima di questo file la CI non installava node nel job di test: quelle prove
passavano solo perché l'immagine `ubuntu-latest` lo include per conto suo. Il
guard qui non ripara quel caso, lo rende **rumoroso**: se un domani l'immagine
cambia, o il passo `setup-node` viene tolto, questo test diventa rosso invece di
lasciare le altre duecento sparire.
"""

from __future__ import annotations

import os
import shutil

import pytest

# Le variabili che i runner impostano da sé. `CI` la mettono tutti; le altre due
# distinguono GitHub Actions, così il guard non si arma su una shell in cui
# qualcuno ha esportato `CI` per altri motivi.
_IN_CI = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))


@pytest.mark.skipif(not _IN_CI, reason="guard di CI: in locale node è opzionale")
def test_node_is_installed_in_ci() -> None:
    node = shutil.which("node")
    assert node, (
        "node non è nel PATH: le suite `tests/webui/*_client.py` si salterebbero "
        "in silenzio. Manca il passo `actions/setup-node` nel job `test` di "
        ".github/workflows/ci.yml."
    )


@pytest.mark.skipif(not _IN_CI, reason="guard di CI: in locale jsdom è opzionale")
def test_jsdom_is_installed_in_ci() -> None:
    """Stesso ragionamento per jsdom: non è una dipendenza del repo, e senza le
    suite che montano la casa intera (``support.home_dom``) e il contratto del
    grafo si saltano in verde. La CI lo installa con ``npm install --no-save
    jsdom`` e lo rende visibile con ``NODE_PATH``."""
    from support.home_dom import _has_jsdom

    assert _has_jsdom(), (
        "jsdom non si risolve da node: le suite `requires_jsdom` si salterebbero "
        "in silenzio. Mancano `npm install --no-save jsdom` o `NODE_PATH` nel job "
        "`test` di .github/workflows/ci.yml."
    )


@pytest.mark.skipif(not _IN_CI, reason="guard di CI: in locale Pillow è opzionale")
def test_pillow_is_installed_in_ci() -> None:
    """``test_mascot_layer_sources.py`` si salta per intero senza Pillow, che
    arriva con l'extra ``dev`` di ``pyproject.toml``."""
    import importlib.util

    assert importlib.util.find_spec("PIL") is not None, (
        "Pillow manca: tests/webui/test_mascot_layer_sources.py si salterebbe per "
        'intero. Il job `test` deve installare `pip install -e ".[dev]"`.'
    )


def test_ci_installs_an_exact_jsdom() -> None:
    """Senza versione ogni giro della CI prendeva l'ultimo jsdom uscito: un
    rilascio nuovo poteva cambiare l'esito delle suite senza che il repo
    cambiasse. Gira anche in locale: legge soltanto il workflow."""
    import re
    from pathlib import Path

    ci = (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    installs = re.findall(r"npm install --no-save (jsdom\S*)", ci)
    assert installs, "il job `test` non installa piu' jsdom"
    for spec in installs:
        assert re.fullmatch(r"jsdom@\d+\.\d+\.\d+", spec), f"versione non esatta: {spec}"
