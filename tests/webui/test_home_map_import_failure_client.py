"""La mappa di un quaderno che non si carica lo dice, e non lascia un rifiuto
di promessa senza padrone.

La mappa arriva con ``import()`` al primo tocco sulla sua linguetta
(``HomeApp._drawMap``), e ``_drawMap`` rilancia l'errore apposta, cosi' il
tocco dopo riprova. Ma chi la chiamava — ``NotebookPages.showTab`` — non la
aspettava ne' la prendeva: un modulo che non arrivava (rete giu', un file
mancante nel pacchetto) era un ``unhandledrejection`` e una linguetta vuota
(terza revisione, HJ18).
"""

from __future__ import annotations

from support.home_dom import requires_jsdom, run_home

pytestmark = requires_jsdom


def test_a_map_that_cannot_be_imported_says_so() -> None:
    run_home("""
import assert from 'node:assert/strict';
import { boot, tick, routes, unhandled, locales, $ } from './boot.mjs';
routes['/api/graph'] = {
  nodes: [{ id: 'a', path: 'a.md', label: 'A' }, { id: 'b', path: 'b.md', label: 'B' }],
  links: [{ source: 'a', target: 'b' }],
};
const app = await boot();
await app.showConversation('project:orto');
await tick(20);
await app.openPages();
await tick(20);
/* Il modulo della mappa che non arriva. */
const gone = Promise.reject(new Error('map module not loaded'));
gone.catch(() => {});
app._mapReady = gone;
$('home-tab-map').click();
await tick(30);
assert.deepEqual(unhandled, []);
const failed = [locales.it.home.map.failed, locales.en.home.map.failed];
assert.ok(failed.includes($('home-map-note').textContent), $('home-map-note').textContent);
assert.equal($('home-map-note').hidden, false);
assert.equal(app._mapReady, null, 'il tocco dopo non riprova');
""")
