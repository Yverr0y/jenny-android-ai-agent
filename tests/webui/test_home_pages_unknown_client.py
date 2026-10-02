"""Le pagine della casa, quando la prima lettura non e' arrivata.

``HomePages.load`` non alza: se ``/api/home/pages`` fallisce la casa parte con
le sole quattro fisse, ed e' giusto — meglio una casa che apre. Ma la
scrittura manda **l'elenco intero** (``home.pages.set``): con la pista vuota
per una lettura fallita, il primo «Metti come pagina» o il primo «Fatto» della
modalita' ordina riscriveva sul server un elenco senza le pagine che c'erano,
cioe' le cancellava tutte.

Qui la regola: finche' l'elenco non e' stato letto nessuna scrittura parte. Al
primo uso si rilegge; se la rilettura riesce si scrive sull'elenco vero, se no
l'avviso lo dice e non si tocca niente.
"""

from __future__ import annotations

from support.home_dom import requires_jsdom, run_home

pytestmark = requires_jsdom

_HEAD = """
import assert from 'node:assert/strict';
import { boot, tick, routes, hooks, failed, sent, rpcAnswers, toasts, locales } from './boot.mjs';
/* Sul server ci sono gia' due pagine appese... */
routes['/api/home/pages'] = {
  pages: [{ id: 'p1', kind: 'app', ref: 'todo' }, { id: 'p2', kind: 'conversation', ref: 'project:trip' }],
  order: ['app', 'chat', 'p1', 'p2', 'notebooks', 'settings'],
  fixed: ['app', 'chat', 'notebooks', 'settings'], max: 8,
};
rpcAnswers['home.pages.set'] = (p) => ({ ok: true, pages: p.pages, order: p.order });
/* ...ma la lettura fallisce finche' `pagesDown` e' vero. */
let pagesDown = true;
let pageReads = 0;
hooks.fetch = async (u) => {
  if (u.pathname !== '/api/home/pages') return undefined;
  pageReads += 1;
  return pagesDown ? failed(503) : undefined;
};
const writes = () => sent.filter((f) => f.type === 'rpc' && f.method === 'home.pages.set');
const unknownText = [locales.it.home.pages.unknown, locales.en.home.pages.unknown];
const app = await boot();
await tick(30);
assert.deepEqual(app.homePages.pages, [], 'la prova parte da una lettura fallita');
"""


def test_pinning_after_a_failed_read_reads_again_and_keeps_the_pages() -> None:
    run_home(_HEAD + """
pagesDown = false;
await app.notebookCard().perform('pin', 'orto');
await tick(30);
const [write] = writes();
assert.ok(write, 'la pagina non e\\u2019 stata appesa');
assert.deepEqual(write.params.pages.map((p) => p.ref), ['todo', 'project:trip', 'project:orto']);
""")


def test_pinning_while_the_list_is_still_unknown_writes_nothing_and_says_so() -> None:
    run_home(_HEAD + """
const before = pageReads;
const done = await app.notebookCard().perform('pin', 'orto');
await tick(30);
assert.equal(done, false);
assert.equal(pageReads, before + 1, 'al primo uso non si rilegge');
assert.deepEqual(writes(), [], 'una scrittura su un elenco mai letto');
assert.ok(toasts().some((t) => unknownText.includes(t)), JSON.stringify(toasts()));
""")


def test_sort_mode_does_not_open_on_a_list_it_never_read() -> None:
    run_home(_HEAD + """
app.strip.openSort();
await tick(30);
assert.equal(app.strip.sorting, false, 'la modalita\\u2019 ordina si e\\u2019 aperta su un elenco vuoto');
await app.strip.closeSort({ save: true });
assert.deepEqual(writes(), []);
assert.ok(toasts().some((t) => unknownText.includes(t)), JSON.stringify(toasts()));

// La lettura torna: la modalita' ordina si apre, sull'elenco vero.
pagesDown = false;
app.strip.openSort();
await tick(30);
assert.equal(app.strip.sorting, true);
assert.deepEqual(app.strip._draft, ['app', 'chat', 'p1', 'p2', 'notebooks', 'settings']);
""")


def test_detaching_after_a_failed_read_reads_again_and_keeps_the_other_pages() -> None:
    """Staccare una pagina e' una scrittura dell'elenco intero come appenderla:
    sull'elenco vuoto del ripiego la pagina non si troverebbe nemmeno. Si
    rilegge, e si scrive l'elenco vero meno quella."""
    run_home(_HEAD + """
pagesDown = false;
const done = await app.homePages.detach('app', 'todo');
await tick(30);
assert.equal(done, true, 'la pagina non e\\u2019 stata staccata');
const [write] = writes();
assert.ok(write, 'nessuna scrittura');
assert.deepEqual(write.params.pages.map((p) => p.ref), ['project:trip']);
""")


def test_detaching_while_the_list_is_still_unknown_writes_nothing_and_says_so() -> None:
    run_home(_HEAD + """
const before = pageReads;
const done = await app.homePages.detach('app', 'todo');
await tick(30);
assert.equal(done, false);
assert.equal(pageReads, before + 1, 'al primo uso non si rilegge');
assert.deepEqual(writes(), []);
assert.ok(toasts().some((t) => unknownText.includes(t)), JSON.stringify(toasts()));
""")


def test_a_save_on_a_list_never_read_writes_nothing() -> None:
    """L'ultima cintura: una scrittura che arrivasse senza aver chiesto se
    l'elenco si conosce non parte comunque."""
    run_home(_HEAD + """
const saved = await app.homePages.save([], ['app', 'chat', 'notebooks', 'settings']);
await tick(30);
assert.equal(saved, false);
assert.deepEqual(writes(), [], 'un elenco mai letto e\\u2019 stato riscritto sul server');
assert.ok(toasts().some((t) => unknownText.includes(t)), JSON.stringify(toasts()));
""")
