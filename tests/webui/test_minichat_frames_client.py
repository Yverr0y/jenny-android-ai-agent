"""La minichat dell'officina legge i frame del turno come la mascotte madre.

``JennyCompanion._handleFrame`` (``mobile-jenny.js``) aveva una sua copia
dell'intera macchina a stati di ``JennyMascot._handleChatStream``
(``shared/jenny-mascot.js``), con in più il fumetto. Qui si fissa cosa fa la
minichat, così che la copia possa diventare un gancio senza cambiare niente:
cosa mostra il fumetto, in che stato resta Jenny, quando si invalida lo storico
della chat e quali frame si scartano.

In node, coi moduli veri (``mobile-jenny.js`` e ``shared/jenny-mascot.js``) e i
vicini finti. L'istanza nasce da ``Object.create`` senza costruttore: il
costruttore disegna il DOM, e qui interessa la lettura dei frame. Lo stato di
Jenny e l'umore si registrano invece di disegnarli.
"""

from __future__ import annotations

import shutil
import tempfile
import textwrap
from pathlib import Path

from support.js_harness import requires_node, run_module

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "jenny" / "templates" / "ui" / "assets"

pytestmark = requires_node

_NEIGHBORS = {
    "state.js": "export const AppState = { currentMode: 'home', on() {} };\n",
    "ws-manager.js": "export const wsManager = new EventTarget();\n",
    "session-manager.js": "export const sessionManager = { currentKey: 'websocket:default' };\n",
    "i18n.js": "export const i18n = { t: (k) => k, locale: 'it', load: async () => {} };\n",
    "mascot.js":"""
export const OUT_SHIFT_RATIO = 0.5;
export function mascotVisible() { return true; }
export function applyMascotSize() {}
""",
    "mascot-drag.js":"""
export function bindMascotDrag() {}
export function buildFlyLayer() {}
""",
}

_PRELUDE = """
import assert from 'node:assert/strict';
globalThis.window = { matchMedia: () => ({ matches: false }) };
const { JennyCompanion } = await import('./mobile-jenny.js');

function classes(...initial) {
  const s = new Set(initial);
  return { add: (c) => s.add(c), remove: (c) => s.delete(c), contains: (c) => s.has(c) };
}

/* Una minichat aperta, con la domanda in volo: `awaiting` e il flag del turno
   alzati come li alza `_send`. */
function minichat({ open = true, expected = true, inTurn = true } = {}) {
  const j = Object.create(JennyCompanion.prototype);
  Object.assign(j, {
    mode: 'home', awaiting: expected, _replyShown: false, _replyTimer: null,
    _deltaBuffer: '', _turnActive: false, _pendingTurn: inTurn,
    _streamTurnId: null, _lastClosedTurnId: null,
    el: { classList: classes() },
    mc: { classList: open ? classes('open') : classes(), dataset: {} },
    bubble: { textContent: '' },
  });
  j.states = [];
  j.moods = [];
  j._setAgentState = (s) => { j.states.push(s); j._agentState = s; };
  j._applyMood = (m) => j.moods.push(m);
  j.invalidations = 0;
  window.mobileApp = { controllers: { chat: { invalidateHistory: () => { j.invalidations += 1; } } } };
  return j;
}
const last = (j) => j.states[j.states.length - 1];
"""


def _run(body: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "shared").mkdir()
        shutil.copy(ASSETS / "mobile-jenny.js", root / "mobile-jenny.js")
        shutil.copy(ASSETS / "shared" / "jenny-mascot.js", root / "shared" / "jenny-mascot.js")
        shutil.copy(ASSETS / "shared" / "wire-error.js", root / "shared" / "wire-error.js")
        for name, text in _NEIGHBORS.items():
            (root / "shared" / name).write_text(text, encoding="utf-8")
        entry = root / "prova.mjs"
        entry.write_text(_PRELUDE + textwrap.dedent(body), encoding="utf-8")
        run_module(entry)


def test_deltas_accumulate_into_the_bubble() -> None:
    _run(
        """
        const j = minichat();
        j._handleFrame({ event: 'delta', text: 'Ciao ', turn_id: 't1' });
        j._handleFrame({ event: 'delta', text: '**Luca**', turn_id: 't1' });
        assert.equal(j.bubble.textContent, 'Ciao Luca', 'testo piano, accumulato');
        assert.equal(j.mc.dataset.state, 'reply');
        assert.equal(last(j), 'talking');
        assert.equal(j._streamTurnId, 't1', 'il primo frame adotta il turno');
        """
    )


def test_stream_end_shows_its_text_and_then_settles() -> None:
    """Il fumetto prima, lo stato dopo: `_showReply` mette `talking`, e se
    venisse per ultimo Jenny resterebbe a parlare a turno fermo."""
    _run(
        """
        const j = minichat();
        j._handleFrame({ event: 'stream_end', text: 'Fatto.' });
        assert.equal(j.bubble.textContent, 'Fatto.');
        assert.equal(last(j), 'idle');
        j._turnActive = true;
        j._handleFrame({ event: 'stream_end' });
        assert.equal(j.bubble.textContent, 'Fatto.', 'senza testo il fumetto resta');
        assert.equal(last(j), 'thinking', 'col goal in corso si torna a pensare');
        """
    )


def test_a_message_with_text_is_shown_and_a_hint_is_not() -> None:
    _run(
        """
        const j = minichat();
        j._handleFrame({ event: 'message', kind: 'tool_hint', text: 'leggo il file' });
        assert.equal(j.bubble.textContent, '', 'un suggerimento non va nel fumetto');
        assert.equal(last(j), 'thinking');
        j._handleFrame({ event: 'message', kind: 'progress', text: 'ancora un attimo' });
        assert.equal(j.bubble.textContent, '');
        assert.equal(last(j), 'thinking');
        j._handleFrame({ event: 'message', tool_events: [{}] });
        assert.equal(last(j), 'thinking');
        j._handleFrame({ event: 'message', text: 'Eccola' });
        assert.equal(j.bubble.textContent, 'Eccola');
        assert.equal(last(j), 'talking');
        """
    )


def test_turn_end_without_a_reply_shows_the_flower_and_invalidates_history() -> None:
    _run(
        """
        const j = minichat();
        let fired = false;
        j._replyTimer = setTimeout(() => { fired = true; }, 5);
        j._handleFrame({ event: 'turn_end', turn_id: 't1' });
        assert.equal(j.bubble.textContent, '✿');
        assert.equal(last(j), 'idle', 'il fiore non lascia Jenny a parlare');
        assert.equal(j.awaiting, false);
        assert.equal(j._pendingTurn, false);
        assert.equal(j._replyTimer, null);
        assert.equal(j._lastClosedTurnId, 't1');
        assert.equal(j.invalidations, 1);
        await new Promise((r) => setTimeout(r, 20));
        assert.equal(fired, false, 'il timer della risposta lenta va spento');
        """
    )


def test_turn_end_after_a_reply_keeps_the_reply() -> None:
    _run(
        """
        const j = minichat();
        j._handleFrame({ event: 'delta', text: 'Risposta', turn_id: 't1' });
        j._handleFrame({ event: 'turn_end', turn_id: 't1' });
        assert.equal(j.bubble.textContent, 'Risposta');
        assert.equal(last(j), 'idle');
        assert.equal(j._streamTurnId, null);
        """
    )


def test_error_shows_its_text_and_the_sad_face() -> None:
    """Le parole del rifiuto sono quelle di ``describeWireError``, come in
    chat: prima il fumetto mostrava ``detail`` o
    ``reason`` grezzi, un testo per il log o un identificatore."""
    _run(
        """
        const j = minichat();
        j._handleFrame({ event: 'error', reason: 'size', detail: 'image_rejected' });
        assert.equal(j.bubble.textContent, 'common.wireError.size');
        assert.equal(last(j), 'idle');
        assert.deepEqual(j.moods, ['sad']);
        assert.equal(j.awaiting, false);
        assert.equal(j._pendingTurn, false);

        const k = minichat();
        k._handleFrame({ event: 'error' });
        assert.equal(k.bubble.textContent, 'common.wireError.unknown');

        const u = minichat();
        u._handleFrame({ event: 'error', reason: 'provider_down' });
        assert.equal(u.bubble.textContent, 'common.wireError.unknown (provider_down)');
        """
    )


def test_the_closing_frame_of_a_foreign_turn_is_ignored() -> None:
    """L'avviso proattivo atterrato durante l'attesa non chiude la domanda."""
    _run(
        """
        const j = minichat();
        j._handleFrame({ event: 'delta', text: 'sto', turn_id: 'mio' });
        j._handleFrame({ event: 'turn_end', turn_id: 'avviso' });
        j._handleFrame({ event: 'error', turn_id: 'avviso', detail: 'no' });
        assert.equal(j.awaiting, true);
        assert.equal(j._pendingTurn, true);
        assert.equal(j.bubble.textContent, 'sto');
        assert.equal(j.invalidations, 0);
        assert.deepEqual(j.moods, []);
        """
    )


def test_with_nothing_on_screen_only_the_pending_closing_passes() -> None:
    """Minichat chiusa a metà turno: i delta si scartano, la chiusura no —
    è l'unico punto che invalida lo storico della chat."""
    _run(
        """
        const j = minichat({ open: false, expected: false });
        j._handleFrame({ event: 'delta', text: 'invisibile', turn_id: 't1' });
        assert.deepEqual(j.states, []);
        assert.equal(j._deltaBuffer, '');
        assert.equal(j._streamTurnId, null, 'un frame scartato non apre il tracciamento');
        j._handleFrame({ event: 'turn_end', turn_id: 't1' });
        assert.equal(j.invalidations, 1);
        assert.equal(j._pendingTurn, false);
        assert.equal(j.bubble.textContent, '', 'a minichat chiusa il fumetto non si scrive');

        const k = minichat({ open: false, expected: false, inTurn: false });
        k._handleFrame({ event: 'turn_end', turn_id: 't1' });
        assert.equal(k.invalidations, 0, 'senza turno in volo non è roba nostra');
        """
    )


def test_goal_status_and_reasoning_move_the_state() -> None:
    _run(
        """
        const j = minichat();
        j._handleFrame({ event: 'goal_status', status: 'running' });
        assert.equal(j._turnActive, true);
        assert.equal(last(j), 'thinking');
        j._handleFrame({ event: 'reasoning_delta', text: 'uhm' });
        j._handleFrame({ event: 'file_edit' });
        assert.equal(last(j), 'thinking');
        j._handleFrame({ event: 'goal_status', status: 'idle' });
        assert.equal(j._turnActive, false);
        assert.equal(last(j), 'idle');
        """
    )


def test_in_the_chat_view_the_bubble_is_not_touched() -> None:
    """In chat la minichat non c'è: il frame va alla macchina della madre."""
    _run(
        """
        const j = minichat({ expected: false, inTurn: false });
        j.mode = 'chat';
        j._handleFrame({ event: 'delta', text: 'in chat', turn_id: 'c1' });
        assert.equal(j.bubble.textContent, '');
        assert.equal(j._deltaBuffer, '');
        assert.equal(last(j), 'talking');
        j._handleFrame({ event: 'turn_end', turn_id: 'c1' });
        assert.equal(j.bubble.textContent, '');
        assert.equal(j.invalidations, 0);
        assert.equal(last(j), 'idle');
        """
    )


def test_an_empty_message_means_thinking_as_in_the_mother() -> None:
    """Cambio voluto (3.5 della pulizia): un ``message`` senza testo né
    ``tool_events`` nella minichat non faceva niente, nella madre porta a
    ``thinking``. Con una macchina sola vale la regola della madre."""
    _run(
        """
        const j = minichat();
        j._handleFrame({ event: 'message' });
        assert.deepEqual(j.states, ['thinking']);
        assert.equal(j.bubble.textContent, '');
        """
    )


def test_a_question_asked_mid_answer_follows_that_turn_but_not_its_old_words() -> None:
    """Una domanda fatta alla minichat mentre Jenny
    sta rispondendo in chat non apre un turno suo: il gateway la inietta nel
    turno in volo. La minichat adottava «il primo turno che vede» e ne mostrava
    il segmento che stava scorrendo — la risposta alla domanda **di prima**.
    Ora segue quel turno, salta il segmento in corso e mostra da quello dopo."""
    _run(
        """
        const { wsManager } = await import('./shared/ws-manager.js');
        const { sessionManager } = await import('./shared/session-manager.js');
        const sent = [];
        Object.assign(wsManager, { connectChat() {}, chatConnected: true,
                                   sendToChat: (key, text) => { sent.push(text); return true; } });
        sessionManager.ensureAttached = () => {};
        globalThis.setTimeout = () => 0;
        const j = minichat({ expected: false, inTurn: false, open: true });
        j.mc.dataset.state = 'ask';
        // In chat il turno t1 sta scorrendo; la minichat non lo disegna.
        j._handleFrame({ event: 'delta', text: 'Ecco il riassunto del documento', turn_id: 't1' });
        assert.equal(j.bubble.textContent, '');
        await j._send('che ore sono?');
        assert.deepEqual(sent, ['che ore sono?']);
        assert.equal(j._streamTurnId, 't1', 'la domanda entra nel turno in volo');
        j._handleFrame({ event: 'delta', text: ' che mi avevi chiesto', turn_id: 't1' });
        assert.equal(j.bubble.textContent, '', 'le parole di prima non sono la risposta');
        j._handleFrame({ event: 'stream_end', text: 'Ecco il riassunto…', turn_id: 't1' });
        assert.equal(j.bubble.textContent, '');
        j._handleFrame({ event: 'delta', text: 'Sono le 10.', turn_id: 't1' });
        assert.equal(j.bubble.textContent, 'Sono le 10.');
        j._handleFrame({ event: 'turn_end', turn_id: 't1' });
        assert.equal(j.awaiting, false);
        assert.equal(j._pendingTurn, false);
        assert.equal(j.invalidations, 1);
        """
    )


def test_a_question_asked_at_rest_adopts_its_own_turn() -> None:
    _run(
        """
        const { wsManager } = await import('./shared/ws-manager.js');
        const { sessionManager } = await import('./shared/session-manager.js');
        Object.assign(wsManager, { connectChat() {}, chatConnected: true, sendToChat: () => true });
        sessionManager.ensureAttached = () => {};
        globalThis.setTimeout = () => 0;
        const j = minichat({ expected: false, inTurn: false, open: true });
        j._handleFrame({ event: 'delta', text: 'vecchio', turn_id: 't0' });
        j._handleFrame({ event: 'turn_end', turn_id: 't0' });
        await j._send('ciao');
        assert.equal(j._streamTurnId, null);
        j._handleFrame({ event: 'delta', text: 'Ciao!', turn_id: 't2' });
        assert.equal(j.bubble.textContent, 'Ciao!');
        assert.equal(j._streamTurnId, 't2');
        """
    )


def test_the_minichat_names_where_and_how_it_sends() -> None:
    """La minichat manda nella conversazione aperta
    e col modo di scrittura scelto, ma diceva sempre «Chiedi qualcosa». Ora
    prende il placeholder della chat vera, che lo scope chip tiene aggiornato
    col progetto e con la sola lettura."""
    _run(
        """
        const inputs = { 'chat-input': { placeholder: 'Chiedi su orto (sola lettura)…' } };
        globalThis.document = { getElementById: (id) => inputs[id] || null };
        const j = minichat({ open: false });
        Object.assign(j, {
          scrim: { classList: classes() },
          input: { placeholder: '', focus() {} },
        });
        j._openMini();
        assert.equal(j.input.placeholder, 'Chiedi su orto (sola lettura)…');
        inputs['chat-input'].placeholder = 'Chiedi qualcosa…';
        j._openMini();
        assert.equal(j.input.placeholder, 'Chiedi qualcosa…', 'si rilegge a ogni apertura');
        delete inputs['chat-input'];
        j._syncPlaceholder();
        assert.equal(j.input.placeholder, 'jenny.askHere', 'senza la chat, il ripiego di sempre');
        """
    )
