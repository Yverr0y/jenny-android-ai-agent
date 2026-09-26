"""Un controller pronto in ritardo non si attiva su una vista che non c'e' piu'.

WJ4 della terza revisione (26/09/2026): ``switchMode`` aspettava il ``ready`` di
un controller e poi lo attivava **comunque**. Entrare in chat e andare altrove
prima che fosse pronta lasciava una chat attiva su una vista nascosta, che
chiamava ``chatOpened`` e cancellava avvisi mai visti. E un ``ready`` rifiutato
restava un rifiuto non gestito (WJ23): il toast generico «errore di rete».

Si esegue in node lo ``switchMode`` vero del guscio, come in
``test_workshop_open_file_from_chat_client.py``.
"""

from __future__ import annotations

from support.js_harness import ASSETS, member, requires_node, run_js

pytestmark = requires_node

APP_SRC = (ASSETS / "mobile-app.js").read_text(encoding="utf-8")
SETTINGS_SRC = (ASSETS / "mobile-settings.js").read_text(encoding="utf-8")


def _script(body: str) -> str:
    view_of = next(
        line for line in SETTINGS_SRC.splitlines() if line.startswith("export const VIEW_OF")
    ).replace("export ", "")
    return f"""
import assert from 'node:assert/strict';

{view_of}
const views = {{}};
const view = (id) => (views[id] ||= {{ id, style: {{}} }});
globalThis.document = {{
  getElementById: (id) => view(id),
  querySelectorAll: () => [],
  documentElement: {{ classList: {{ forEach() {{}}, remove() {{}}, add() {{}} }} }},
}};
const viewElement = (mode) => document.getElementById(`view-${{VIEW_OF[mode] || mode}}`);
const readStorage = () => '1';
const AppState = {{ set() {{}} }};
const toasts = [];
const showToast = (m) => toasts.push(m);
const i18n = {{ t: (k) => k }};
const errors = [];
const console = {{ error: (...a) => errors.push(a), warn() {{}}, log() {{}} }};

class Shell {{
{member(APP_SRC, "ensureController")}
{member(APP_SRC, "switchMode")}
  pushNav() {{}}
}}

function deferred() {{
  let resolve, reject;
  const promise = new Promise((a, b) => {{ resolve = a; reject = b; }});
  return {{ promise, resolve, reject }};
}}
const gate = deferred();
class Chat {{
  constructor() {{ this.ready = gate.promise; this.activations = 0; }}
  activate() {{ this.activations += 1; }}
  deactivate() {{}}
}}
class Plain {{ activate() {{ this.activations = (this.activations || 0) + 1; }} }}

const shell = new Shell();
shell.controllers = {{}};
shell.controllerFactories = {{ chat: () => new Chat(), memory: () => new Plain() }};
shell.currentMode = null;
shell._firstRun = false;
shell.header = {{ setMode() {{}} }};
shell.drawer = {{ closeAll() {{}} }};
shell.launcher = {{ close() {{}} }};
const settle = () => new Promise((r) => setTimeout(r, 5));

{body}
"""


def test_a_chat_ready_after_leaving_does_not_activate() -> None:
    run_js(
        _script(
            """
shell.switchMode('chat', false);
shell.switchMode('memory', false);
gate.resolve();
await settle();
assert.equal(shell.controllers.chat.activations, 0, 'attivata su una vista nascosta');
assert.equal(shell.controllers.memory.activations, 1);
"""
        )
    )


def test_a_chat_still_on_screen_activates_once_ready() -> None:
    run_js(
        _script(
            """
shell.switchMode('chat', false);
assert.equal(shell.controllers.chat.activations, 0);
gate.resolve();
await settle();
assert.equal(shell.controllers.chat.activations, 1);
"""
        )
    )


def test_a_failed_ready_is_handled_and_said() -> None:
    """Un rifiuto non gestito farebbe fallire il processo node: il banco lo
    vedrebbe come un'uscita diversa da zero."""
    run_js(
        _script(
            """
shell.switchMode('chat', false);
gate.reject(new Error('boom'));
await settle();
assert.equal(shell.controllers.chat.activations, 0);
assert.equal(errors.length, 1);
assert.deepEqual(toasts, ['common.genericError']);
"""
        )
    )
