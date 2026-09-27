"""«N file modificati» in un quaderno apre il file del quaderno.

I percorsi dei ``file_edit`` sono
relativi alla radice del turno, cioe' al quaderno (``wikis/<nome>/``) in una
chat di quaderno; l'editor dell'officina apre dalla radice del workspace. La
lista li apriva com'erano: 404. Si esegue il ``_renderCollapsibleFileEdits``
vero su un DOM finto, e ``workspacePathIn`` vero.
"""

from __future__ import annotations

from support.js_harness import ASSETS, member, requires_node, run_js

pytestmark = requires_node

CHAT_SRC = (ASSETS / "mobile-chat.js").read_text(encoding="utf-8")
LIST = (ASSETS / "shared" / "conversation-list.js").as_uri()


def test_the_path_is_taken_from_the_project_root() -> None:
    run_js(
        "import assert from 'node:assert/strict';\n"
        f"const {{ workspacePathIn }} = await import('{LIST}');\n"
        """
      assert.equal(workspacePathIn('project:orto', 'wiki/entities/Pothos.md', 'wikis'),
                   'wikis/orto/wiki/entities/Pothos.md');
      assert.equal(workspacePathIn('project:orto', './note.md'), 'wikis/orto/note.md');
      assert.equal(workspacePathIn('project:orto', 'wikis/orto/note.md'), 'wikis/orto/note.md');
      assert.equal(workspacePathIn('project:orto', 'a.md', 'quaderni'), 'quaderni/orto/a.md');
      assert.equal(workspacePathIn('websocket:default', 'memory/MEMORY.md'), 'memory/MEMORY.md');
      assert.equal(workspacePathIn('project:orto', '/abs/x.md'), '/abs/x.md');
    """
    )


def test_a_click_in_the_list_opens_the_project_file() -> None:
    run_js(
        "import assert from 'node:assert/strict';\n"
        f"const {{ workspacePathIn }} = await import('{LIST}');\n"
        """
      function el(tag) {
        const n = {
          tag, className: '', innerHTML: '', textContent: '', children: [], listeners: {},
          classList: { toggle() {} },
          appendChild(c) { this.children.push(c); return c; },
          addEventListener(t, f) { this.listeners[t] = f; },
          querySelector(sel) {
            const cls = sel.replace(/^\\./, '');
            const walk = (x) => {
              for (const c of x.children) {
                if (String(c.className).split(' ').includes(cls)) return c;
                const f = walk(c); if (f) return f;
              }
              return null;
            };
            if (cls === 'tool-events-badge' || cls === 'tool-events-label') return (this['_' + cls] ||= el('span'));
            return walk(this);
          },
        };
        return n;
      }
      globalThis.document = { createElement: el };
      const escapeHtml = (s) => s;
      const i18n = { t: () => '2 file' };
      const sessionManager = { currentKey: 'project:orto' };
      const scopeChip = { projectsDir: 'wikis' };
      const opened = [];
      const msg = el('div');
      const chat = {
        _ensureMetaRow: () => msg,
        async _openFileInWorkspace(p) { opened.push(p); },
      """
        + member(CHAT_SRC, "_renderCollapsibleFileEdits")
        + """
      };
      chat._renderCollapsibleFileEdits(msg, new Map([['wiki/index.md', { added: 1, deleted: 0 }]]));
      const body = msg.querySelector('.tool-events-body');
      const item = body.children[0];
      await item.listeners.click({ stopPropagation() {} });
      assert.deepEqual(opened, ['wikis/orto/wiki/index.md']);
    """
    )
