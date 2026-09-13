"""Il pulsante Copia: cosa copia, e su quali bolle compare.

Il testo di una bolla non si ricostruisce da ``innerText`` — perde le recinzioni
dei blocchi di codice e il loro linguaggio, che è esattamente ciò che si vuole
quando si copia una risposta per incollarla altrove. Il sorgente si registra
dove la bolla nasce (cinque punti) e si legge da una ``WeakMap``; ``innerText``
resta come rete, così un pulsante Copia non copia mai il vuoto.

Due cose che una asserzione sul sorgente non vedrebbe, e che qui girano davvero:
una bolla con **più** ``.chat-content`` (turno testo → tool → testo) si copia
intera, e ``_appendMsgActions`` chiamato due volte lascia una riga sola — in
coda, anche se nel frattempo è arrivata la meta-row della latenza.

I metodi si estraggono dal sorgente e si eseguono in node su un `this` finto,
come in ``test_message_bubble_client.py``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ASSETS = Path(__file__).resolve().parents[2] / "jenny" / "templates" / "ui" / "assets"
CHAT_JS = ASSETS / "mobile-chat.js"

_NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(_NODE is None, reason="node non disponibile")

_METHODS = (
    "_setMessageSource",
    "_messageText",
    "_messagePlain",
    "_buildMsgActionButton",
    "_appendMsgActions",
)


def _method(source: str, name: str) -> str:
    body = re.search(rf"\n  (?:async )?{name}\(([^)]*)\)\s*\{{(.*?)\n  \}}", source, re.S)
    assert body, f"{name} non trovato"
    return f"{name}({body.group(1)}) {{{body.group(2)}\n  }}"


def _harness() -> str:
    chat = CHAT_JS.read_text(encoding="utf-8")
    methods = ",\n    ".join(_method(chat, name) for name in _METHODS)
    return """
import assert from 'node:assert/strict';

/* ── DOM minimo ──────────────────────────────────────────────────────────────
   Solo ciò che questi metodi toccano. `appendChild` **sposta** un figlio che è
   già dentro, come quello vero: è il meccanismo su cui poggia l'idempotenza
   della riga di azioni. */
function el(tag) {
  const node = {
    tag,
    className: '',
    innerHTML: '',
    innerText: '',
    title: '',
    attrs: {},
    children: [],
    setAttribute(k, v) { this.attrs[k] = v; },
    appendChild(child) {
      const at = this.children.indexOf(child);
      if (at !== -1) this.children.splice(at, 1);
      this.children.push(child);
      return child;
    },
    querySelector(sel) {
      if (sel === ':scope > .chat-msg-actions') {
        return this.children.find((c) => c.className.split(' ').includes('chat-msg-actions')) || null;
      }
      return null;
    },
    querySelectorAll(sel) {
      const want = sel.replace('.', '');
      return this.children.filter((c) => c.className.split(' ').includes(want));
    },
  };
  node.classList = { contains: (c) => node.className.split(' ').includes(c) };
  return node;
}
const document = { createElement: el };
const i18n = { t: (key) => key };

function bubble(role, ...texts) {
  const msg = el('div');
  msg.className = `chat-msg chat-msg-${role}`;
  for (const text of texts) {
    const content = el('div');
    content.className = 'chat-content';
    content.innerText = text;
    msg.appendChild(content);
  }
  return msg;
}

function chat() {
  return {
    _msgSource: new WeakMap(),
    __METHODS__,
  };
}

/* Le classi della riga di azioni, nell'ordine. */
function actions(msg) {
  const row = msg.children.find((c) => c.className.split(' ').includes('chat-msg-actions'));
  return row ? row.children.map((b) => b.className.split(' ')[1]) : null;
}
""".replace("__METHODS__", methods)


def _run_js(script: str) -> None:
    proc = subprocess.run(
        [str(_NODE), "--input-type=module", "-e", _harness() + script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


FENCED = "Ecco:\n\n```python\nprint(1)\n```"


def test_the_recorded_source_wins_over_inner_text() -> None:
    """Il sorgente porta le recinzioni; `innerText` le avrebbe perse."""
    _run_js(f"""
      const c = chat();
      const msg = bubble('ai', 'Ecco:\\n\\nprint(1)');
      c._setMessageSource(msg, {FENCED!r});
      assert.equal(c._messageText(msg), {FENCED!r});
      // E la versione leggibile resta quella renderizzata, senza i backtick.
      assert.equal(c._messagePlain(msg), 'Ecco:\\n\\nprint(1)');
    """)


def test_inner_text_is_the_net_when_nothing_was_recorded() -> None:
    _run_js("""
      const c = chat();
      const msg = bubble('ai', 'una risposta dallo storico');
      assert.equal(c._messageText(msg), 'una risposta dallo storico');
    """)


def test_a_turn_with_several_segments_copies_whole() -> None:
    """Testo → tool → testo: una bolla, due `.chat-content`, una copia sola."""
    _run_js("""
      const c = chat();
      const msg = bubble('ai', 'primo', 'secondo');
      c._setMessageSource(msg, 'primo');
      c._setMessageSource(msg, 'secondo');
      assert.equal(c._messageText(msg), 'primo\\n\\nsecondo');
      assert.equal(c._messagePlain(msg), 'primo\\n\\nsecondo');
    """)


def test_the_actions_row_is_added_once_and_stays_last() -> None:
    """Due chiamate (blocco `message` e poi `turn_end`) lasciano una riga sola."""
    _run_js("""
      const c = chat();
      const msg = bubble('ai', 'risposta');
      c._appendMsgActions(msg);
      // Nel frattempo arriva la meta-row della latenza.
      const meta = el('div');
      meta.className = 'chat-meta';
      msg.appendChild(meta);
      c._appendMsgActions(msg);

      const rows = msg.children.filter((x) => x.className.split(' ').includes('chat-msg-actions'));
      assert.equal(rows.length, 1, 'la riga è stata duplicata');
      assert.equal(msg.children[msg.children.length - 1], rows[0], 'la riga non è in coda');
    """)


def test_a_user_bubble_gets_the_menu_but_no_copy_button() -> None:
    """Le bolle utente sono corte: basta la selezione nativa, più il `⋯`."""
    _run_js("""
      const c = chat();
      const msg = bubble('user', 'ciao');
      c._appendMsgActions(msg);
      assert.deepEqual(actions(msg), ['chat-msg-more']);
    """)


def test_an_answer_gets_copy_and_the_menu() -> None:
    _run_js("""
      const c = chat();
      const msg = bubble('ai', 'risposta');
      c._appendMsgActions(msg);
      assert.deepEqual(actions(msg), ['chat-msg-copy', 'chat-msg-more']);
    """)


def test_a_tools_only_turn_offers_nothing_to_copy() -> None:
    """Un turno di soli tool non ha testo: nessuna riga, nessun pulsante muto."""
    _run_js("""
      const c = chat();
      const msg = bubble('ai');
      c._appendMsgActions(msg);
      assert.equal(actions(msg), null);
    """)
