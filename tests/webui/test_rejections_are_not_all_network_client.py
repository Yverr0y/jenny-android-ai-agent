"""Non ogni rifiuto e' un errore di rete, e un file illeggibile e' un rifiuto.

Due meta':

- il gestore globale ``unhandledrejection`` dell'officina diceva «errore di
  rete» a **ogni** rifiuto, anche a un difetto del codice: ora lo dice solo
  quando ``isNetworkFailure`` (``shared/utils.js``) riconosce un ``fetch`` che
  non e' partito o non e' tornato;
- ``ImageHandler._handleFiles`` non gestiva l'errore del ``FileReader``: il
  rifiuto saliva senza padrone, i file dopo sparivano e ``onChange`` non
  arrivava. Ora il file si rifiuta con ``decode``, come farebbe il server.
"""

from __future__ import annotations

from support.js_harness import ASSETS, requires_node, run_js

pytestmark = requires_node

UTILS = (ASSETS / "shared" / "utils.js").as_uri()
IMAGES = (ASSETS / "shared" / "image-handler.js").as_uri()
APP_SRC = (ASSETS / "mobile-app.js").read_text(encoding="utf-8")


def test_only_a_fetch_that_failed_is_the_network() -> None:
    run_js(
        "import assert from 'node:assert/strict';\n"
        f"const {{ isNetworkFailure }} = await import('{UTILS}');\n"
        """
      assert.equal(isNetworkFailure(new TypeError('Failed to fetch')), true);
      assert.equal(isNetworkFailure(new TypeError('NetworkError when attempting to fetch resource.')), true);
      assert.equal(isNetworkFailure(new TypeError('Load failed')), true);
      assert.equal(isNetworkFailure(new TypeError("Cannot read properties of null (reading 'x')")), false);
      assert.equal(isNetworkFailure(new Error('Cron failed: 500')), false);
      assert.equal(isNetworkFailure(undefined), false);
      assert.equal(isNetworkFailure('boom'), false);
    """
    )


def test_the_global_handler_asks_before_saying_network() -> None:
    handler = APP_SRC.split("window.addEventListener('unhandledrejection'", 1)[1].split("});", 1)[0]
    assert "isNetworkFailure(e.reason)" in handler, handler
    assert "common.genericError" in handler, handler


def test_an_unreadable_file_is_refused_and_the_rest_still_arrive() -> None:
    run_js(
        "import assert from 'node:assert/strict';\n"
        """
      let n = 0;
      globalThis.FileReader = class {
        readAsDataURL(file) {
          n += 1;
          setTimeout(() => {
            if (file.name === 'rotto.png') { this.error = new Error('NotReadableError'); this.onerror?.(); }
            else { this.result = 'data:x'; this.onload?.(); }
          }, 0);
        }
      };
      globalThis.console = { ...console, warn() {} };
      """
        f"const {{ ImageHandler }} = await import('{IMAGES}');\n"
        """
      const h = new ImageHandler();
      const refused = [];
      let changed = null;
      h.onReject = (r) => refused.push(r);
      h.onChange = (items) => { changed = items.map((i) => i.name); };
      await h._handleFiles([
        { name: 'rotto.png', type: 'image/png', size: 10 },
        { name: 'buono.png', type: 'image/png', size: 10 },
      ]);
      assert.deepEqual(refused, ['decode']);
      assert.deepEqual(changed, ['buono.png']);
      assert.equal(n, 2);
    """
    )
