"""Cancellare un quaderno mentre e' aperto nei Quaderni.

Dal 26/09/2026 un quaderno si apre nella pagina Quaderni, dove l'hai toccato
(``HomePages.notebooksConversation``), e la sua scheda si apre da li' con una
pressione lunga. Cancellarlo da li' deve chiuderlo (``closeNotebook``): la
pagina torna all'elenco, la chat torna alla conversazione della pagina chat, e
si resta sui Quaderni. Non c'era un banco che lo facesse davvero: ``deleteNotebook``
e ``closeNotebook`` si incontrano solo nella casa intera.
"""

from __future__ import annotations

from support.home_dom import requires_jsdom, run_home

pytestmark = requires_jsdom


def test_deleting_the_notebook_open_in_notebooks_closes_it_and_stays_there() -> None:
    run_home("""
import assert from 'node:assert/strict';
import { boot, tick, rpcAnswers, toasts, locales, $ } from './boot.mjs';
rpcAnswers['project.delete'] = () => ({ ok: true });
const app = await boot();
await app.switchConversation('project:orto');
await tick(30);
assert.equal(app.homePages.notebooksConversation, 'project:orto');
assert.equal(app._entry.id, 'notebooks');
assert.equal(app.currentKey(), 'project:orto');

const done = app.deleteNotebook('orto');
await tick(20);
$('oc-confirm-ok').click();
assert.equal(await done, true);
await tick(30);

assert.equal(app.homePages.notebooksConversation, null, 'il quaderno cancellato e\\u2019 ancora aperto');
assert.equal($('home-notebooks').closest('[data-page]')?.hasAttribute('data-open') ?? false, false);
assert.equal(app._entry.id, 'notebooks', 'cancellare ha portato via dai Quaderni');
assert.equal(app.currentKey(), 'websocket:default');
const said = [locales.it, locales.en].map((l) => l.home.notebook.deleted.replace('{name}', 'orto'));
assert.ok(toasts().some((t) => said.includes(t)), JSON.stringify(toasts()));
""")
