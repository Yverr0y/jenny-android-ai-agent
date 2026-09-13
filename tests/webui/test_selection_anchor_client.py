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
    return "import assert from 'node:assert/strict';\n" + fn.group(0).replace("export ", "", 1) + """

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


def test_missing_measures_mean_no_action() -> None:
    """Un nodo staccato non dà rettangolo: senza misura non si tocca niente."""
    _run_js(f"""
      assert.equal(anchorWasClamped(null, line(10), {VIEWPORT}), false);
      assert.equal(anchorWasClamped(line(-800), null, {VIEWPORT}), false);
    """)
