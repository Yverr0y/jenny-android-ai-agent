"""Dalla casa, l'officina si apre sulla conversazione che stavi guardando.

Era un buco dichiarato nel commento di ``HomeApp._openInWorkshop``: la pressione
lunga sulla riga di lavoro — e poi quella sul chip degli agenti — dentro un
quaderno apriva l'officina sulla chat personale, perché la chiave aperta non
viaggiava fra i due gusci e l'officina dal frammento leggeva solo ``bs``.

Le due metà si provano qui in node, con i metodi veri ritagliati dal sorgente:

- la casa scrive ``chat=project:<nome>`` nel frammento, e niente per la
  personale o per la porta delle Impostazioni;
- l'officina lo legge al boot (``conversationFromFragment``), accetta solo un
  quaderno col nome che il gateway accetterebbe, e lo toglie dall'URL alla prima
  entry che riscrive (``_navUrl``) — rimasto lì, un reload dopo il ritorno alla
  personale riaprirebbe il quaderno.

``conversation-list.js`` non importa niente, quindi si importa così com'è: la
regola sul nome è quella vera, non una copia.
"""

from __future__ import annotations

from support.js_harness import ASSETS, function, member, requires_node, run_js

pytestmark = requires_node

APP_JS = ASSETS / "mobile-app.js"
HOME_JS = ASSETS / "home-app.js"
CONVERSATIONS = (ASSETS / "shared" / "conversation-list.js").as_uri()


def _prelude() -> str:
    return f"""
import assert from 'node:assert/strict';
import {{ isOpenableProjectName, projectNameOf }} from '{CONVERSATIONS}';
"""


def test_the_home_names_the_notebook_in_the_fragment() -> None:
    home = HOME_JS.read_text(encoding="utf-8")
    run_js(_prelude() + f"""
      const navigated = [];
      const api = {{ navigate(target) {{ navigated.push(target); }} }};
      const app = {{ {member(home, "_openInWorkshop")} }};

      app._openInWorkshop('project:piante:17', 'project:piante');
      app._openInWorkshop(null, 'project:piante');
      app._openInWorkshop('default:9', 'websocket:default');
      app._openInWorkshop(null);
      app._openInWorkshop(null, 'project:../fuori');

      assert.deepEqual(navigated, [
        '/html-mobile/workshop.html#turn=project%3Apiante%3A17&chat=project%3Apiante',
        '/html-mobile/workshop.html#chat=project%3Apiante',
        // La personale non viaggia: e' gia' il default dell'officina.
        '/html-mobile/workshop.html#turn=default%3A9',
        '/html-mobile/workshop.html',
        // Un nome che il gateway rifiuterebbe non diventa un'istruzione.
        '/html-mobile/workshop.html',
      ]);
    """)


def test_both_conversation_doors_pass_the_open_key_and_settings_does_not() -> None:
    """Guardia sul testo: la riga di lavoro e il chip degli agenti sono dentro
    una conversazione, le Impostazioni no."""
    home = HOME_JS.read_text(encoding="utf-8")
    assert "onOpenInWorkshop: (turnId) => this._openInWorkshop(turnId, sessionManager.currentKey)," in home
    assert "onOpenInWorkshop: () => this._openInWorkshop(null, sessionManager.currentKey)," in home
    assert "onWorkshop: () => this._openInWorkshop(null)," in home


def test_the_workshop_reads_only_a_notebook_from_the_fragment() -> None:
    app = APP_JS.read_text(encoding="utf-8")
    run_js(_prelude() + f"""
      {function(app, "conversationFromFragment")}

      assert.equal(conversationFromFragment('#chat=project%3Apiante'), 'project:piante');
      assert.equal(conversationFromFragment('#turn=t%3A1&chat=project:piante'), 'project:piante');
      assert.equal(conversationFromFragment('chat=project:piante'), 'project:piante');

      for (const hash of ['', '#', '#turn=t%3A1', '#chat=', '#chat=websocket%3Adefault',
                          '#chat=project%3A..%2Ffuori', '#chat=project%3A.nascosto',
                          '#chat=unified%3Adefault', undefined]) {{
        assert.equal(conversationFromFragment(hash), null, String(hash));
      }}
    """)


def test_the_first_rewritten_entry_drops_the_instruction_and_keeps_the_rest() -> None:
    app = APP_JS.read_text(encoding="utf-8")
    run_js(_prelude() + f"""
      const window = {{ location: '' }};
      const app = {{ {member(app, "_navUrl")} }};

      window.location = 'http://127.0.0.1:18790/html-mobile/workshop.html#turn=t%3A1&chat=project%3Apiante';
      assert.equal(String(app._navUrl({{ mode: 'chat' }})),
                   'http://127.0.0.1:18790/html-mobile/workshop.html?mode=chat#turn=t%3A1');

      window.location = 'http://127.0.0.1:18790/html-mobile/workshop.html#chat=project%3Apiante';
      assert.equal(String(app._navUrl({{ mode: 'chat' }})),
                   'http://127.0.0.1:18790/html-mobile/workshop.html?mode=chat');

      // Senza `chat` il frammento non si tocca, nemmeno nella codifica.
      window.location = 'http://127.0.0.1:18790/html-mobile/workshop.html?mode=brain#turn=t:1';
      assert.equal(String(app._navUrl({{ mode: 'hands' }})),
                   'http://127.0.0.1:18790/html-mobile/workshop.html?mode=hands#turn=t:1');
    """)


def test_the_boot_switches_before_the_chat_exists() -> None:
    """Guardia sul testo dell'ordine di boot: la chiave si legge prima del
    ``replaceNav`` che la toglie dall'URL, sceglie la vista chat, e il cambio di
    conversazione avviene dentro ``_initSessions`` — prima di ``switchMode``,
    che è dove nasce il controller della chat e parte ``loadInitialHistory``."""
    app = APP_JS.read_text(encoding="utf-8")
    init = member(app, "init", body_only=True)
    read = init.index("conversationFromFragment(window.location.hash)")
    first_nav = init.index("this.replaceNav(this._navStateFor(initialMode))")
    sessions = init.index("await this._initSessions(openKey)")
    mode = init.index("this.switchMode(initialMode, false)")
    assert read < first_nav < sessions < mode
    assert "urlMode || (openKey ? 'chat' : null) || savedMode || 'chat'" in init
    sessions_body = member(app, "_initSessions", body_only=True)
    assert sessions_body.index("sessionManager.init()") < sessions_body.index(
        "sessionManager.switchTo(openKey)"
    )
