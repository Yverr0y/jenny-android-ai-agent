"""Un turno aspetta solo i subagent che ha lanciato lui.

``_drain_pending`` si bloccava fino a 300 secondi quando **qualunque** subagent
della sessione era vivo, anche uno lanciato da un turno precedente: un «ciao» con
un subagent di prima in giro teneva il turno aperto — e il tasto Ferma acceso —
per cinque minuti. L'attesa esiste perché i risultati dei subagent lanciati *in
questo* turno rientrino in ordine nello stesso turno; quelli di un altro turno
rientrano dalla coda quando arrivano, come un messaggio qualunque.
"""

from __future__ import annotations

import asyncio

from jenny.bus.events import InboundMessage
from jenny.providers.base import LLMResponse, ToolCallRequest
from tests.support.agent import make_loop, make_provider
from tests.support.aio import wait_until

KEY = "unified:default"


def _loop_answering(tmp_path, chat):
    provider = make_provider()
    provider.chat_with_retry = chat
    provider.chat_stream_with_retry = chat
    return make_loop(tmp_path, provider=provider)


async def test_a_plain_answer_does_not_wait_for_an_earlier_subagent(tmp_path):
    async def chat(**_kw):
        return LLMResponse(content="Ciao! Tutto bene.")

    loop = _loop_answering(tmp_path, chat)
    # Un subagent lanciato da un turno PRECEDENTE di questa sessione, ancora vivo.
    loop.subagents.get_running_ids_by_session = (
        lambda key: frozenset({"vecchio"}) if key == KEY else frozenset()
    )
    loop.subagents.get_running_count_by_session = lambda key: 1 if key == KEY else 0
    queue: asyncio.Queue = asyncio.Queue(maxsize=20)
    loop._pending_queues[KEY] = queue
    msg = InboundMessage(channel="websocket", sender_id="u", chat_id="default", content="ciao")

    await asyncio.wait_for(loop._dispatch(msg, queue), timeout=5.0)


async def test_a_subagent_spawned_in_this_turn_is_still_waited_for(tmp_path):
    """Il rovescio: l'attesa resta per chi è nato in questo turno."""
    running: set[str] = set()
    calls = {"n": 0}

    async def chat(**_kw):
        calls["n"] += 1
        if calls["n"] == 1:
            # Il modello «lancia» un subagent: da qui la sessione ne ha uno vivo.
            running.add("nuovo")
            return LLMResponse(
                content="", finish_reason="tool_calls",
                tool_calls=[ToolCallRequest(id="c1", name="list_dir", arguments={"path": "."})],
            )
        return LLMResponse(content="fatto")

    loop = _loop_answering(tmp_path, chat)
    loop.subagents.get_running_ids_by_session = (
        lambda key: frozenset(running) if key == KEY else frozenset()
    )
    loop.subagents.get_running_count_by_session = lambda key: len(running) if key == KEY else 0
    queue: asyncio.Queue = asyncio.Queue(maxsize=20)
    loop._pending_queues[KEY] = queue
    msg = InboundMessage(channel="websocket", sender_id="u", chat_id="default",
                         content="lancia un aiutante")

    task = asyncio.create_task(loop._dispatch(msg, queue))
    try:
        await wait_until(lambda: calls["n"] >= 1, timeout=5.0)
        await asyncio.sleep(0.3)
        # Dopo i tool il turno aspetta il risultato del suo subagent, invece di
        # tornare dal modello a mani vuote.
        assert calls["n"] == 1 and not task.done()
        running.clear()
        queue.put_nowait(InboundMessage(channel="websocket", sender_id="subagent",
                                        chat_id="default", content="risultato dell'aiutante"))
        await asyncio.wait_for(task, timeout=5.0)
        assert calls["n"] == 2
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
