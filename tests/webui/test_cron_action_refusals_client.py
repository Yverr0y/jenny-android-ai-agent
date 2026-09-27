"""Un job protetto non si sente dire che la sua ora e' passata.

Il gateway risponde 409
sia a un promemoria scaduto (``expired``) sia, ora, a un job di sistema
(``protected``), col motivo nel corpo. Il toast di ``_runCronAction``
(``mobile-settings.js``) leggeva solo lo stato e diceva «scaduto» a tutti e
due. Si esegue il metodo vero con un ``api`` finto che rifiuta come il gateway.
"""

from __future__ import annotations

import json

import pytest
from support.js_harness import ASSETS, member, requires_node, run_js

pytestmark = requires_node

SRC = (ASSETS / "mobile-settings.js").read_text(encoding="utf-8")


def _toast(status: int, body: str) -> str:
    out = run_js(
        f"""
const toasts = [];
const showToast = (m) => toasts.push(m);
const i18n = {{ t: (k) => k }};
const confirmDialog = async () => true;
const console = {{ warn() {{}} }};
const api = {{
  async cronJobAction() {{
    const err = new Error({json.dumps(body)});
    err.status = {status};
    throw err;
  }},
}};
const s = {{
  async _loadCron() {{}},
  {member(SRC, "_runCronAction")}
}};
await s._runCronAction({{ id: 'j1', name: 'x' }}, 'pause');
process.stdout.write(JSON.stringify(toasts));
"""
    )
    return json.loads(out)[0]


@pytest.mark.parametrize(
    ("status", "body", "key"),
    [
        (409, "expired", "cron.action.expired"),
        (409, "protected", "cron.action.failed"),
        (403, "protected", "cron.action.failed"),
        (500, "cron pause failed", "cron.action.failed"),
    ],
)
def test_each_refusal_says_its_own_thing(status: int, body: str, key: str) -> None:
    assert _toast(status, body) == key
