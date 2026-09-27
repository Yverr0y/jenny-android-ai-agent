"""Lasciare un quaderno lo dice al gateway; lasciare la chat personale no.

Lato client. ``detachChat``
(``shared/ws-manager.js``) toglieva la chat solo dall'elenco locale: il gateway
conosceva solo ``attach``, e la connessione continuava a ricevere i frame di
ogni quaderno lasciato. Ora, a socket aperto e per una chiave ``project:``,
manda ``{"type": "detach", "chat_id": "project:<nome>"}`` — la forma
dell'``attach``. La risposta ``detached`` non si aspetta. La chat personale
non si stacca mai: e' li' che arrivano gli avvisi proattivi.

Il modulo vero gira in node con i vicini finti.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import textwrap
from pathlib import Path

from support.js_harness import ASSETS, requires_node, run_module

pytestmark = requires_node

_NEIGHBORS = {
    "api-client.js": "export const api = { getToken: () => 't', token: 't' };\n",
    "i18n.js": "export const i18n = { t: (k) => k };\n",
    "state.js": "export const AppState = { readonlyTurn: false };\n",
}

_PRELUDE = """
import assert from 'node:assert/strict';
globalThis.window = {
  location: { protocol: 'http:', host: '127.0.0.1:1' },
  addEventListener() {},
};
class FakeWS {
  static OPEN = 1;
  constructor() { this.readyState = 0; this.sent = []; }
  send(d) { this.sent.push(JSON.parse(d)); }
  close() {}
}
globalThis.WebSocket = FakeWS;
const { wsManager } = await import('./shared/ws-manager.js');
const ws = new FakeWS();
ws.readyState = FakeWS.OPEN;
wsManager.chatWs = ws;
"""


def _run(body: str) -> list:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "shared").mkdir()
        shutil.copy(ASSETS / "shared" / "ws-manager.js", root / "shared" / "ws-manager.js")
        for name, text in _NEIGHBORS.items():
            (root / "shared" / name).write_text(text, encoding="utf-8")
        entry = root / "prova.mjs"
        entry.write_text(
            _PRELUDE + textwrap.dedent(body) + "\nconsole.log(JSON.stringify(ws.sent));\n",
            encoding="utf-8",
        )
        return json.loads(run_module(entry).strip().splitlines()[-1])


def test_leaving_a_notebook_detaches_it_on_the_server() -> None:
    sent = _run(
        """
        wsManager.attachChat('project:orto');
        wsManager.detachChat('project:orto');
        assert.equal(wsManager.knownChats.has('project:orto'), false);
        """
    )
    assert sent == [
        {"type": "attach", "chat_id": "project:orto"},
        {"type": "detach", "chat_id": "project:orto"},
    ], sent


def test_the_personal_chat_is_never_detached() -> None:
    sent = _run(
        """
        wsManager.attachChat('websocket:default');
        wsManager.detachChat('websocket:default');
        """
    )
    assert sent == [{"type": "attach", "chat_id": "default"}], sent


def test_a_closed_socket_only_forgets_locally() -> None:
    sent = _run(
        """
        wsManager.attachChat('project:orto');
        ws.readyState = 3;
        wsManager.detachChat('project:orto');
        assert.equal(wsManager.knownChats.has('project:orto'), false);
        """
    )
    assert sent == [{"type": "attach", "chat_id": "project:orto"}], sent
