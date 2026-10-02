"""Una foto allegata si vede come miniatura, non come chip «file».

Regressione di ``2e42db88``:
``_renderAttachPreview`` (``mobile-chat.js``) sceglieva la miniatura su
``item.isImage``, un campo che ``ImageHandler`` non scrive piu' — il secchio e'
``kind``. Ogni foto finiva nel ramo dei file generici. Qui il metodo vero, con
le voci come le produce l'``ImageHandler`` vero.
"""

from __future__ import annotations

from support.js_harness import ASSETS, member, requires_node, run_js

pytestmark = requires_node

CHAT_SRC = (ASSETS / "mobile-chat.js").read_text(encoding="utf-8")
IMAGES = (ASSETS / "shared" / "image-handler.js").as_uri()


def test_a_photo_gets_a_thumbnail_and_a_pdf_a_chip() -> None:
    run_js(
        "import assert from 'node:assert/strict';\n"
        f"const {{ ImageHandler }} = await import('{IMAGES}');\n"
        """
      globalThis.FileReader = class {
        readAsDataURL() { setTimeout(() => { this.result = 'data:image/png;base64,AAAA'; this.onload(); }, 0); }
      };
      const preview = { style: {}, innerHTML: '', querySelectorAll: () => [] };
      globalThis.document = { getElementById: () => preview };
      const escapeHtml = (s) => String(s);
      const chat = {
      """
        + member(CHAT_SRC, "_renderAttachPreview")
        + """
      };
      const h = new ImageHandler();
      await h._handleFiles([
        { name: 'foto.jpg', type: 'image/jpeg', size: 10 },
        { name: 'nota.pdf', type: 'application/pdf', size: 10 },
      ]);
      chat._renderAttachPreview(h._items);
      const thumbs = preview.innerHTML.split('attach-thumb').length - 1;
      assert.equal(thumbs, 2, preview.innerHTML);
      assert.ok(preview.innerHTML.includes('<img src="data:image/png;base64,AAAA" alt="foto.jpg">'), preview.innerHTML);
      assert.equal((preview.innerHTML.match(/attach-file"/g) || []).length, 1, preview.innerHTML);
      assert.ok(preview.innerHTML.includes('nota.pdf'));
    """
    )
