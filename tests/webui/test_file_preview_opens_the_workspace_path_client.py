"""«Apri nell'editor» dall'anteprima apre il file dal workspace.

RC4 della terza revisione (26/09/2026): la correzione recente per cui
``_renderFilePreview`` (``mobile-chat.js``) apre ``data.workspace_path`` — il
percorso dal workspace che il server rimanda, dove quello scritto in chat e'
relativo al quaderno (e spesso alla sua ``wiki/``) — non aveva un test: una
mutazione su quella riga restava verde. Il metodo vero, su un DOM finto.
"""

from __future__ import annotations

import json

import pytest
from support.js_harness import ASSETS, member, requires_node, run_js

pytestmark = requires_node

CHAT_SRC = (ASSETS / "mobile-chat.js").read_text(encoding="utf-8")


def _opened(payload: dict) -> list:
    out = run_js(
        f"""
const escapeHtml = (s) => String(s);
const i18n = {{ t: (k) => k }};
const sessionManager = {{ currentKey: 'project:orto' }};
const api = {{ fetchFilePreview: async () => ({json.dumps(payload)}) }};
function el() {{
  const node = {{
    className: '', listeners: {{}}, children: [],
    set innerHTML(v) {{ this._html = v; }},
    get innerHTML() {{ return this._html || ''; }},
    remove() {{}},
    addEventListener(t, fn) {{ this.listeners[t] = fn; }},
    querySelector(sel) {{
      if (sel === '.file-preview') return null;
      return (this.parts ||= {{}})[sel] ||= el();
    }},
    appendChild(c) {{ this.children.push(c); return c; }},
  }};
  return node;
}}
globalThis.document = {{ createElement: () => el() }};
const opened = [];
const chat = {{
  async _openFileInWorkspace(p) {{ opened.push(p); }},
  {member(CHAT_SRC, "_renderFilePreview")}
}};
const container = el();
await chat._renderFilePreview('entities/Pothos.md', container);
const preview = container.children[0];
await preview.parts['.file-preview-action'].listeners.click({{ preventDefault() {{}} }});
process.stdout.write(JSON.stringify(opened));
"""
    )
    return json.loads(out)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"content": "x", "workspace_path": "wikis/orto/wiki/entities/Pothos.md"},
         "wikis/orto/wiki/entities/Pothos.md"),
        ({"content": "x"}, "entities/Pothos.md"),
    ],
    ids=["from-the-server", "fallback"],
)
def test_the_editor_opens_what_the_server_resolved(payload: dict, expected: str) -> None:
    assert _opened(payload) == [expected]
