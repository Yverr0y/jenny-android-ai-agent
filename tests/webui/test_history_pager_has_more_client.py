"""Il pager crede al server quando dice che dietro non c'e' altro.

Nessun banco passava davvero
``has_more_before`` a ``shared/history-pager.js`` — ogni finto rispondeva con
una pagina senza quel campo, e ``adopt`` lo legge con ``!== false``. Mutato
(``hasMore`` sempre vero, o il campo ignorato) restava tutto verde. Qui il
``HistoryPager`` vero riceve le tre forme che il server manda
(``webui/transcript``: ``has_more_before`` vero, falso, assente) e si misura
cosa chiede dopo.
"""

from __future__ import annotations

from support.js_harness import ASSETS, requires_node, run_js

pytestmark = requires_node

PAGER = (ASSETS / "shared" / "history-pager.js").as_uri()

_HARNESS = f"""
import assert from 'node:assert/strict';
globalThis.document = {{ createElement: () => ({{ addEventListener() {{}}, remove() {{}} }}) }};
globalThis.console = {{ ...console, error() {{}} }};
const {{ HistoryPager }} = await import('{PAGER}');
const asked = [];
let answers = [];
let onScroll = null;
const scroller = {{ scrollTop: 0, scrollHeight: 1000, clientHeight: 500 }};
const pager = new HistoryPager({{
  scroller: () => scroller,
  listenOn: {{ addEventListener: (t, fn) => {{ onScroll = fn; }} }},
  container: () => ({{ querySelector: () => null }}),
  pageSize: 50,
  begin: () => ({{
    fetch: async (limit, cursor) => {{ asked.push(cursor); return answers.shift(); }},
    stale: () => false,
  }}),
  prepend() {{}},
  mount() {{}},
  label: () => 'x',
}});
"""


def test_the_three_shapes_of_the_first_page() -> None:
    run_js(
        _HARNESS
        + """
      pager.adopt({ before_cursor: 'c1', has_more_before: true });
      assert.equal(pager.hasMore, true);
      assert.equal(pager.cursor, 'c1');
      pager.adopt({ before_cursor: null, has_more_before: false });
      assert.equal(pager.hasMore, false, 'il server ha detto che non c\\'e\\' altro');
      pager.adopt({});
      assert.equal(pager.hasMore, true, 'senza il campo si presume che ci sia');
    """
    )


def test_scrolling_stops_asking_once_the_start_is_reached() -> None:
    run_js(
        _HARNESS
        + """
      pager.bindInfiniteScroll();
      pager.adopt({ before_cursor: 'c1', has_more_before: true });
      answers = [
        { messages: [{ text: 'b' }], page: { before_cursor: 'c2', has_more_before: true } },
        { messages: [{ text: 'a' }], page: { before_cursor: null, has_more_before: false } },
      ];
      await pager.loadMore();
      assert.deepEqual(asked, ['c1']);
      assert.equal(pager.hasMore, true);
      scroller.scrollTop = 0;
      onScroll();
      await new Promise((r) => setTimeout(r, 0));
      assert.deepEqual(asked, ['c1', 'c2'], 'la seconda pagina col cursore nuovo');
      assert.equal(pager.hasMore, false);
      scroller.scrollTop = 0;
      onScroll();
      await pager.loadMore();
      assert.deepEqual(asked, ['c1', 'c2'], 'arrivati all\\'inizio non si chiede piu\\'');
    """
    )
