"""Ctrl+, apre un cassetto del dock, non una schermata che il dock non ha.

La scorciatoia faceva
``switchMode('settings')``: un modo che esiste ancora (serve ai banchi e al
controller istanziato da solo) ma non e' nel dock — sedici gruppi in una
pagina e nessuna voce accesa. Ora apre il Cervello, o niente se si e' gia' in
uno dei tre cassetti. Si esegue ``_initKeyboardShortcuts`` vero.
"""

from __future__ import annotations

import re

from support.js_harness import ASSETS, member, requires_node, run_js

pytestmark = requires_node

APP_SRC = (ASSETS / "mobile-app.js").read_text(encoding="utf-8")
SETTINGS_SRC = (ASSETS / "mobile-settings.js").read_text(encoding="utf-8")
WORKSHOP = (ASSETS.parent / "workshop.html").read_text(encoding="utf-8")


def test_the_shortcut_lands_on_a_dock_entry() -> None:
    view_of = next(
        line for line in SETTINGS_SRC.splitlines() if line.startswith("export const VIEW_OF")
    ).replace("export ", "")
    out = run_js(
        "import assert from 'node:assert/strict';\n"
        + view_of
        + """
      const shortcuts = {};
      const keyboard = { register: (combo, fn) => { shortcuts[combo] = fn; } };
      class Shell {
      """
        + member(APP_SRC, "_initKeyboardShortcuts")
        + """
        switchMode(mode) { this.switched.push(mode); this.currentMode = mode; }
      }
      const shell = new Shell();
      shell.switched = [];
      shell.currentMode = 'chat';
      shell._initKeyboardShortcuts();
      shortcuts['mod+,']();
      shortcuts['mod+,']();
      shell.currentMode = 'hands';
      shortcuts['mod+,']();
      console.log(JSON.stringify(shell.switched));
    """
    )
    switched = __import__("json").loads(out)
    assert switched == ["brain"], switched
    dock = set(re.findall(r'class="dock-item[^"]*" data-mode="(\w+)"', WORKSHOP))
    assert switched[0] in dock, dock
