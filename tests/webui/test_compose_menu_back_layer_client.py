"""Una tendina del composer si chiude con una pressione di Indietro, e basta.

WJ5 della terza revisione (26/09/2026). Le tendine sopra il composer (scope,
comandi) avevano un ``keydown`` loro che le chiudeva su Escape; ma Escape e'
anche la scorciatoia del tasto Indietro del guscio (``keyboard.register
('escape', …)`` in ``mobile-app.js``), quindi la stessa pressione chiudeva la
tendina **e** tornava alla schermata prima. Il tasto Indietro di Android, al
contrario, la scavalcava: la tendina non era un livello di ``_overlayLayers``.

Si eseguono in node ``shared/state.js`` vero e ``handleHardwareBack`` +
``_overlayLayers`` veri del guscio.
"""

from __future__ import annotations

from support.js_harness import ASSETS, member, requires_node, run_js

pytestmark = requires_node

STATE = (ASSETS / "shared" / "state.js").as_uri()
APP_SRC = (ASSETS / "mobile-app.js").read_text(encoding="utf-8")

_SETUP = f"""
import assert from 'node:assert/strict';
const docListeners = [];
globalThis.localStorage = {{ getItem: () => null }};
globalThis.document = {{
  addEventListener(type) {{ docListeners.push(type); }},
  querySelector: () => null,
  querySelectorAll: () => [],
}};
const {{ armComposeMenu, claimComposeMenu, composeMenuOpen, closeComposeMenus }} = await import('{STATE}');
function chip(id) {{
  const c = {{
    id, _open: false, closed: 0,
    el: {{ addEventListener() {{}} }},
    menu: {{ addEventListener() {{}} }},
    toggle() {{ this._open ? this.close() : this.open(); }},
    open() {{ claimComposeMenu(id); this._open = true; }},
    close() {{ if (this._open) {{ this._open = false; this.closed += 1; }} }},
  }};
  armComposeMenu(c, id);
  return c;
}}
const scope = chip('scope');
const commands = chip('commands');
"""


def test_escape_is_not_heard_twice() -> None:
    """Nessun ``keydown`` proprio: Escape arriva alla tendina dalla catena di
    Indietro, una volta sola."""
    run_js(
        _SETUP
        + """
      assert.ok(!docListeners.includes('keydown'), docListeners.join(','));
      assert.ok(docListeners.includes('click'), 'il tocco fuori la chiude ancora');
    """
    )


def test_the_menus_answer_the_back_chain() -> None:
    run_js(
        _SETUP
        + """
      assert.equal(composeMenuOpen(), false);
      assert.equal(closeComposeMenus(), false);
      scope.open();
      assert.equal(composeMenuOpen(), true);
      commands.open();
      assert.equal(scope._open, false, 'una sola per volta');
      assert.equal(closeComposeMenus(), true);
      assert.equal(commands._open, false);
      assert.equal(composeMenuOpen(), false);
    """
    )


def test_back_closes_the_menu_instead_of_leaving() -> None:
    run_js(
        _SETUP
        + "class Shell {\n"
        + member(APP_SRC, "_overlayLayers")
        + "\n"
        + member(APP_SRC, "handleHardwareBack")
        + """
      }
      let wentBack = 0;
      globalThis.window = { history: { back() { wentBack += 1; } } };
      const shell = new Shell();
      shell.launcher = { isOpen: () => false };
      shell.drawer = { activeDrawer: null };
      shell.controllers = { chat: { handleBack: () => false } };
      shell.currentMode = 'chat';
      shell._navPos = 2;
      scope.open();
      shell.handleHardwareBack();
      assert.equal(scope._open, false, 'la tendina resta aperta');
      assert.equal(wentBack, 0, 'la stessa pressione ha anche cambiato schermata');
      shell.handleHardwareBack();
      assert.equal(wentBack, 1);
    """
    )
