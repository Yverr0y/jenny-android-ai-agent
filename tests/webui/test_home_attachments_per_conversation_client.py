"""Gli allegati preparati restano nella conversazione in cui li hai scelti.

La bozza del campo e' per conversazione dal primo giorno (``_drafts``): mezza
frase scritta in casa non deve partire nel quaderno che apri dopo. Gli
allegati in attesa no — erano uno solo per tutta la casa — e una foto scelta
dentro un quaderno partiva col primo messaggio della conversazione personale
(terza revisione, HJ9). Stessa famiglia di guasto, un attimo prima.
"""

from __future__ import annotations

from support.home_dom import requires_jsdom, run_home

pytestmark = requires_jsdom

_HEAD = """
import assert from 'node:assert/strict';
import { boot, tick, sent, rpcAnswers, $ } from './boot.mjs';
const app = await boot();
const photo = { data_url: 'data:image/png;base64,AAAA', name: 'plant.png', mime: 'image/png', kind: 'image' };
/* Come se il selettore avesse appena letto un file: `_handleFiles` fa questo. */
const pick = () => { app.files._items.push({ ...photo }); app.files.onChange?.(app.files._items); };
const lastMessage = () => sent.filter((f) => f.type === 'message').pop();
"""


def test_an_attachment_picked_in_a_notebook_does_not_leave_with_the_personal_chat() -> None:
    run_home(_HEAD + """
await app.showConversation('project:orto');
await tick(20);
pick();
assert.equal($('home-pending').hidden, false);

await app.showConversation('websocket:default');
await tick(20);
assert.equal(app.files.count, 0, 'la foto del quaderno e\\u2019 venuta a casa');
assert.equal($('home-pending').hidden, true, 'la striscia degli allegati e\\u2019 ancora a schermo');
app.input.value = 'hello';
app._send();
assert.deepEqual(lastMessage().media || [], []);

await app.showConversation('project:orto');
await tick(20);
assert.equal(app.files.count, 1, 'tornando nel quaderno la foto non c\\u2019e\\u2019 piu\\u2019');
assert.equal($('home-pending').hidden, false);
app.input.value = 'for the notebook';
app._send();
assert.equal(lastMessage().chat_id, 'project:orto');
assert.deepEqual(lastMessage().media.map((m) => m.name), ['plant.png']);
""")


def test_the_attachments_of_a_deleted_notebook_go_with_it() -> None:
    run_home(_HEAD + """
await app.showConversation('project:orto');
await tick(20);
pick();
await app.showConversation('websocket:default');
await tick(20);
assert.ok(app._attachments.has('project:orto'));
rpcAnswers['project.delete'] = () => ({ ok: true });
app.deleteNotebook('orto');
await tick(20);
document.getElementById('oc-confirm-ok').click();
await tick(40);
assert.equal(app._attachments.has('project:orto'), false);
""")
