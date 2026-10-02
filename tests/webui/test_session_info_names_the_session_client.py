"""Info sessione dice in quale conversazione si e', non «default» sempre.

``_showSessionInfo``
(``mobile-chat.js``) scriveva la sessione e il canale fissi, ``default`` e
``websocket``, anche dentro un quaderno. Si esegue il metodo vero su un
documento finto e si legge il popover.
"""

from __future__ import annotations

import json
import re

from support.js_harness import ASSETS, member, requires_node, run_js

pytestmark = requires_node

CHAT_SRC = (ASSETS / "mobile-chat.js").read_text(encoding="utf-8")


def _popover(key: str) -> str:
    out = run_js(
        f"""
const escapeHtml = (s) => String(s);
const i18n = {{ t: (k) => k }};
const getProviderBrand = () => ({{ label: 'P', color: '#000' }});
const sessionManager = {{ currentKey: {json.dumps(key)}, personalKey: 'websocket:default',
                          currentScope: null, runStartedAt: null }};
function el() {{
  return {{ className: '', innerHTML: '', style: {{}}, remove() {{}}, contains: () => false,
           querySelector: () => ({{ addEventListener() {{}} }}) }};
}}
let shown = null;
globalThis.document = {{
  createElement: () => el(),
  body: {{ appendChild(p) {{ shown = p; }} }},
  addEventListener() {{}},
  removeEventListener() {{}},
}};
const chat = {{
  identityEl: null,
  _runtimeModel: null,
  _hideSessionInfo() {{}},
  {member(CHAT_SRC, "_showSessionInfo")}
}};
chat._showSessionInfo();
console.log(JSON.stringify(shown.innerHTML));
"""
    )
    return json.loads(out.strip().splitlines()[-1])


def _values(html: str) -> list[str]:
    return [
        re.sub(r"<[^>]+>", "", v).strip()
        for v in re.findall(r'class="session-info-value"[^>]*>(.*?)</span>', html, re.S)
    ][:2]


def test_the_personal_chat_is_the_websocket_default_session() -> None:
    assert _values(_popover("websocket:default")) == ["websocket:default", "websocket"]


def test_a_notebook_is_its_own_session() -> None:
    assert _values(_popover("project:orto")) == ["project:orto", "project"]
