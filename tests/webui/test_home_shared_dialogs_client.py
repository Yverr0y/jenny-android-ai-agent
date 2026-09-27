"""I dialoghi condivisi sopra la casa: Indietro e Home li chiudono per primi.

«Elimina quaderno?», «Nuovo nome per …» e il dettaglio sono i `<dialog>` di
``shared/dialog.js`` (``oc-confirm``, ``oc-prompt``, ``oc-detail``): stanno
nel top layer, sopra tutto. La casa chiudeva i suoi fogli e non questi, quindi
Indietro portava via la pagina **sotto** la domanda e la domanda restava
aperta sopra un'altra pagina — un «Conferma» che cancellava un quaderno da
una stanza in cui non eri piu'. E la chat che ci stava
sotto contava come vista, cancellando avvisi mai letti.

Come l'officina (``mobile-app.js``, ``_dismissTopDialog``): il dialogo si
congeda con la semantica di Esc — l'evento ``cancel`` — cosi' chi aspettava la
risposta la riceve, ed e' un no.
"""

from __future__ import annotations

from support.home_dom import requires_jsdom, run_home

pytestmark = requires_jsdom

_HEAD = """
import assert from 'node:assert/strict';
import { boot, tick, $, sent } from './boot.mjs';
const app = await boot();
const deletes = () => sent.filter((f) => f.type === 'rpc' && /delete/i.test(f.method || ''));
"""


def test_back_closes_the_delete_question_before_the_page_under_it() -> None:
    run_home(_HEAD + """
app.homePages.goToId('notebooks');
await tick(20);
const asked = app.deleteNotebook('orto');
await tick(20);
assert.equal($('oc-confirm-dialog').open, true, 'la domanda non si e\\u2019 aperta');

app.handleHardwareBack();
await tick(20);
assert.equal($('oc-confirm-dialog').open, false, 'Indietro ha lasciato la domanda aperta');
assert.equal(app._entry.id, 'notebooks', 'una pressione ha tolto anche la pagina');
assert.equal(await asked, false, 'chiudere la domanda non e\\u2019 un no');
assert.deepEqual(deletes(), []);
""")


def test_home_closes_the_rename_prompt_and_goes_home() -> None:
    run_home(_HEAD + """
app.homePages.goToId('notebooks');
await tick(20);
const asked = app.renameNotebook('orto');
await tick(20);
assert.equal($('oc-prompt-dialog').open, true);
app.goHome();
await tick(20);
assert.equal($('oc-prompt-dialog').open, false, 'Home ha lasciato la domanda aperta');
assert.equal(app._entry.kind, 'chat');
assert.equal(await asked, false);
""")


def test_the_chat_under_a_shared_dialog_is_not_on_screen() -> None:
    run_home(_HEAD + """
assert.equal(app.isChatOnScreen(), true);
const asked = app.renameNotebook('orto');
await tick(20);
assert.equal(app.isChatOnScreen(), false, 'una domanda aperta copre la chat');
app.handleHardwareBack();
await asked;
assert.equal(app.isChatOnScreen(), true);
""")
