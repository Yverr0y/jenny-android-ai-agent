"""Rileggere il filo della casa mentre succede qualcosa: frame vivi, un'altra
rilettura, una lettura che non arriva.

Il filo si rilegge in quattro occasioni — l'avvio, un cambio di conversazione,
una riconnessione, un ``session_boundary`` — e in tutte la lettura e' una
fetch che dura: nel frattempo il socket continua a portare frame. I difetti
misurati dalla terza revisione stanno tutti in quell'attesa:

- **HJ1**: la bolla viva che arriva durante la lettura finiva *sopra* tutta la
  storia, perche' la storia si appendeva dopo di lei;
- **HJ7**: due riletture della stessa conversazione insieme disegnavano il
  filo due volte;
- **HJ10**: la riga di un rifiuto restava nella conversazione dopo, perche'
  la ricarica toglieva i messaggi e i confini ma non le note;
- **HJ5/HJ6**: una lettura fallita all'avvio non si riprovava piu', una
  fallita al resync lasciava il filo vuoto senza dirlo, e quella del
  ``session_boundary`` era un rifiuto di promessa che nessuno prendeva.

Si guida la casa intera (``support.home_dom``): il legame fra la chat, il
guscio e il socket e' proprio quel che una classe finta riscriverebbe.
"""

from __future__ import annotations

from support.home_dom import requires_jsdom, run_home

pytestmark = requires_jsdom

_HEAD = """
import assert from 'node:assert/strict';
import { boot, tick, frame, threads, hooks, failed, thread, unhandled, FakeWS, $ } from './boot.mjs';
threads['websocket:default'] = { messages: [
  { role: 'user', text: 'hello' },
  { role: 'assistant', text: 'hello to you', turnId: 'h' },
] };
threads['project:orto'] = { messages: [
  { role: 'user', text: 'Q1' },
  { role: 'assistant', text: 'A1', turnId: 'a' },
  { role: 'user', text: 'Q2 in progress' },
] };
/* La storia arriva tardi: il tempo in cui il socket porta i frame vivi. */
const slowThread = (ms) => {
  hooks.fetch = async (u) => { if (u.pathname.endsWith('/webui-thread')) await tick(ms); };
};
const reconnect = async () => {
  FakeWS.last.onclose();
  FakeWS.last.readyState = 3;
  // Lo stesso modulo che usa la casa: la riconnessione del ws-manager, subito.
  const { wsManager } = await import(__WS__);
  wsManager.connectChat();
};
"""


def _run(body: str) -> str:
    from support.home_dom import UI

    ws = (UI / "assets" / "shared" / "ws-manager.js").as_posix()
    return run_home(_HEAD.replace("__WS__", repr(ws)) + body)


def test_a_live_answer_stays_below_the_history_when_you_enter_its_conversation() -> None:
    """HJ1: entri nel quaderno mentre Jenny ci sta rispondendo."""
    _run("""
const app = await boot();
slowThread(120);
const opening = app.switchConversation('project:orto');
await tick(30);
frame({ event: 'delta', chat_id: 'project:orto', turn_id: 'b', text: 'Here is the answer' });
await tick(40);
frame({ event: 'delta', chat_id: 'project:orto', turn_id: 'b', text: ' to Q2' });
await opening;
await tick(150);
assert.deepEqual(thread(), [
  'you: Q1', 'jenny: A1', 'you: Q2 in progress', 'jenny: Here is the answer to Q2',
]);
""")


def test_a_live_answer_stays_below_the_history_across_a_resync() -> None:
    """HJ1, il resync a meta' turno: i delta arrivati durante la rilettura
    stanno sotto la storia riletta."""
    _run("""
const app = await boot();
assert.deepEqual(thread(), ['you: hello', 'jenny: hello to you']);
threads['websocket:default'].messages.push({ role: 'user', text: 'and now?' });
slowThread(120);
await reconnect();
await tick(30);
frame({ event: 'delta', chat_id: 'default', turn_id: 'n', text: 'now this' });
await tick(200);
assert.deepEqual(thread(), ['you: hello', 'jenny: hello to you', 'you: and now?', 'jenny: now this']);
""")


def test_two_reloads_of_the_same_conversation_draw_it_once() -> None:
    """HJ7: due riletture insieme, e il filo resta uno."""
    _run("""
const app = await boot();
slowThread(40);
await Promise.all([app.chat.reload(), app.chat.reload()]);
assert.deepEqual(thread(), ['you: hello', 'jenny: hello to you']);
""")


def test_a_reconnect_during_a_switch_does_not_duplicate_the_thread() -> None:
    """HJ7, la forma che capita davvero: si cambia conversazione e il socket
    si riapre mentre la lettura e' in volo."""
    _run("""
const app = await boot();
await app.showConversation('project:orto');
await tick(20);
slowThread(120);
const back = app.showConversation('websocket:default');
await tick(20);
await reconnect();
await back;
await tick(300);
assert.deepEqual(thread(), ['you: hello', 'jenny: hello to you']);
""")


def test_a_refusal_note_does_not_follow_you_into_another_conversation() -> None:
    """HJ10: la riga di rifiuto e' della conversazione in cui e' nata."""
    _run("""
const app = await boot();
await app.showConversation('project:orto');
await tick(20);
app.chat.noteRefusal('too_many_images');
assert.ok(thread().some((row) => row.startsWith('note: ')), 'la nota non e\\u2019 comparsa');
await app.showConversation('websocket:default');
await tick(20);
assert.deepEqual(thread(), ['you: hello', 'jenny: hello to you']);
""")
