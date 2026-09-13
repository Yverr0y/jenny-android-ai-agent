"""L'ancora della selezione non si sposta da sola.

Trascinando un manico mentre l'altro estremo è fuori dall'area visibile, la
WebView ricalcola l'estremo fermo dalle sue ultime coordinate **di schermo**,
ritagliate dentro il viewport: l'ancora salta sul bordo e la selezione si mangia
tutto quello che c'è in mezzo. Misurato sul Titan 2 il 13/09/2026 — nel foglio
"Seleziona testo" la selezione è arrivata a prendersi il titolo del dialog, che
non fa parte del messaggio: il salto è geometrico, non di contenuto.

`anchorWasClamped` è la firma di quel salto, isolata apposta come funzione pura:
qui gira davvero in node, su rettangoli, senza bisogno di un browser.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ASSETS = Path(__file__).resolve().parents[2] / "jenny" / "templates" / "ui" / "assets"
SELECTION_JS = ASSETS / "shared" / "selection.js"

_NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(_NODE is None, reason="node non disponibile")

VIEWPORT = 1440


def _harness() -> str:
    src = SELECTION_JS.read_text(encoding="utf-8")
    fn = re.search(r"export function anchorWasClamped\(.*?\n\}", src, re.S)
    assert fn, "anchorWasClamped non trovata"
    # La tolleranza di bordo è una costante del modulo, non un numero magico del
    # test: si estrae anche quella, così la misura sul telefono resta l'unica
    # fonte del valore.
    eps = re.search(r"export const EDGE_EPS = \d+;", src)
    assert eps, "EDGE_EPS non trovata"
    return ("import assert from 'node:assert/strict';\n"
            + eps.group(0).replace("export ", "", 1) + "\n"
            + fn.group(0).replace("export ", "", 1)) + """

/* Un rettangolo di riga alla quota y, come lo restituirebbe getBoundingClientRect
   su un range collassato: coordinate di viewport, quindi negative sopra il bordo. */
function line(y) {
  return { top: y, bottom: y + 40, left: 0, right: 100 };
}
"""


def _run_js(script: str) -> None:
    proc = subprocess.run(
        [str(_NODE), "--input-type=module", "-e", _harness() + script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_the_jump_upwards_is_recognised() -> None:
    """Il caso misurato: ancora sopra il bordo, nuova ancora incollata in cima."""
    _run_js(f"""
      assert.equal(anchorWasClamped(line(-800), line(10), {VIEWPORT}), true);
    """)


def test_the_jump_downwards_too() -> None:
    """Simmetrico: ancora sotto il bordo, nuova ancora incollata in fondo."""
    _run_js(f"""
      assert.equal(anchorWasClamped(line({VIEWPORT} + 500), line({VIEWPORT} - 20), {VIEWPORT}), true);
    """)


def test_an_anchor_still_on_screen_is_never_touched() -> None:
    """Se l'ancora vecchia si vedeva, il cambio è una selezione nuova: giù le mani."""
    _run_js(f"""
      assert.equal(anchorWasClamped(line(300), line(10), {VIEWPORT}), false);
    """)


def test_a_new_anchor_far_from_the_edges_is_not_a_jump() -> None:
    """L'ancora fuori schermo c'è, ma la nuova sta a metà pagina: è un'altra cosa."""
    _run_js(f"""
      assert.equal(anchorWasClamped(line(-800), line(700), {VIEWPORT}), false);
    """)


def test_the_two_sides_do_not_get_confused() -> None:
    """Ancora fuori **sopra** e nuova ancora in **fondo**: non è il salto."""
    _run_js(f"""
      assert.equal(anchorWasClamped(line(-800), line({VIEWPORT} - 10), {VIEWPORT}), false);
    """)


def test_without_the_old_anchor_nothing_happens() -> None:
    """Un nodo staccato non dà rettangolo: senza sapere dov'era, giù le mani."""
    _run_js(f"""
      assert.equal(anchorWasClamped(null, line(10), {VIEWPORT}), false);
    """)


def test_a_missing_new_anchor_does_not_disarm_the_repair() -> None:
    """Chromium torna spesso un rettangolo vuoto per l'ancora nuova.

    Misurato sul Titan 2 il 13/09/2026 (`anc=0/0`): pretendere anche quella
    seconda misura significava non riparare mai il caso vero. Con la vecchia
    ancora fuori schermo e una selezione che non è nuova, il salto è acclarato.
    """
    _run_js(f"""
      assert.equal(anchorWasClamped(line(-800), null, {VIEWPORT}), true);
      // Ma se la vecchia ancora si vedeva, il dubbio resta un no.
      assert.equal(anchorWasClamped(line(300), null, {VIEWPORT}), false);
    """)


def test_the_edge_tolerance_covers_the_clipped_fraction() -> None:
    """La misura vera: `bottom = 0.3`, non `0` e tanto meno negativo.

    La WebView ritaglia i rettangoli dei range all'area visibile e lascia una
    frazione di pixel oltre il bordo. Con `< 0` — e perfino con `<= 0` — la
    riparazione non scattava: è il difetto che ha fatto fallire il primo giro
    sul telefono.
    """
    _run_js(f"""
      assert.equal(anchorWasClamped({{ top: -17.3, bottom: 0.3 }}, null, {VIEWPORT}), true);
      assert.equal(anchorWasClamped({{ top: {VIEWPORT} - 0.3, bottom: {VIEWPORT} + 17 }}, null, {VIEWPORT}), true);
      // Una riga interamente dentro non è "fuori" per nessuna tolleranza.
      assert.equal(anchorWasClamped(line(40), null, {VIEWPORT}), false);
    """)
