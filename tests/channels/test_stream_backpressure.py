"""Un delta scartato sotto backpressure non si perde per sempre (PC3).

La coda outbound è limitata (512 in produzione) e i delta passano da
``try_publish_outbound``, che li scarta quando è piena; il finale del turno è
``_streamed`` e il dispatcher non lo rispedisce alla WebUI. Con Telegram in 429
o un download lento davanti, il testo scartato mancava per sempre dalla bolla e
dal transcript: 512 parole su 800, misurato. Adesso lo ``stream_end`` di uno
stream che ha perso delta porta il testo intero, e il canale lo manda al posto
del buffer — anche quando è lo ``stream_end`` stesso a non entrare in coda.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from port_alloc import free_port
from support.aio import wait_until

from jenny.bus.events import OutboundMessage
from jenny.bus.queue import MessageBus
from jenny.channels.dispatcher import WebSocketDispatcher
from jenny.channels.websocket import WebSocketChannel, WebSocketConfig
from jenny.config.schema import Config
from jenny.webui.gateway_services import build_gateway_services

WORDS = [f"parola{i} " for i in range(40)]
FULL = "".join(WORDS)


@pytest.fixture(autouse=True)
def isolate_webui_workspace_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("jenny.config.paths.get_data_dir", lambda: tmp_path)


def _delta(text: str) -> OutboundMessage:
    return OutboundMessage(channel="websocket", chat_id="default", content=text,
                           metadata={"_stream_delta": True, "_stream_id": "s1"})


def _end() -> OutboundMessage:
    return OutboundMessage(channel="websocket", chat_id="default", content="",
                           metadata={"_stream_end": True, "_stream_id": "s1"})


def _final() -> OutboundMessage:
    return OutboundMessage(channel="websocket", chat_id="default", content=FULL.strip(),
                           metadata={"_streamed": True})


def test_the_bus_attaches_the_full_text_to_a_degraded_end() -> None:
    bus = MessageBus(outbound_maxsize=4)
    for word in WORDS[:3]:
        assert bus.try_publish_outbound(_delta(word))
    accepted = [bus.try_publish_outbound(_delta(word)) for word in WORDS[3:]]
    assert not all(accepted)
    bus.outbound.get_nowait()  # un posto libero per l'end
    assert bus.try_publish_outbound(_end())
    queued = [bus.outbound.get_nowait() for _ in range(bus.outbound_size)]
    assert queued[-1].metadata["_stream_full_text"] == FULL


def test_an_intact_stream_is_left_alone() -> None:
    bus = MessageBus(outbound_maxsize=100)
    for word in WORDS:
        assert bus.try_publish_outbound(_delta(word))
    assert bus.try_publish_outbound(_end())
    queued = [bus.outbound.get_nowait() for _ in range(bus.outbound_size)]
    assert "_stream_full_text" not in queued[-1].metadata


async def test_a_dropped_end_is_delivered_before_the_final() -> None:
    bus = MessageBus(outbound_maxsize=2)
    for word in WORDS:
        bus.try_publish_outbound(_delta(word))
    assert not bus.try_publish_outbound(_end())  # anche l'end è respinto
    publishing = asyncio.create_task(bus.publish_outbound(_final()))
    got = [await asyncio.wait_for(bus.consume_outbound(), timeout=1) for _ in range(2)]
    await asyncio.wait_for(publishing, timeout=1)
    got += [bus.outbound.get_nowait() for _ in range(bus.outbound_size)]
    ends = [m for m in got if m.metadata.get("_stream_end")]
    assert len(ends) == 1
    assert ends[0].metadata["_stream_full_text"] == FULL
    assert got.index(ends[0]) < got.index(next(m for m in got if m.metadata.get("_streamed")))


def _ws_channel(bus: MessageBus) -> WebSocketChannel:
    cfg: dict[str, Any] = {
        "enabled": True, "allowFrom": ["*"], "host": "127.0.0.1", "port": free_port(),
        "path": "/ws", "websocketRequiresToken": False, "streaming": True,
    }
    gateway = build_gateway_services(
        config=WebSocketConfig.model_validate(cfg), bus=bus, session_manager=None,
        workspace_path=Path.cwd(), default_restrict_to_workspace=False,
        runtime_model_name=None,
    )
    return WebSocketChannel(cfg, bus, gateway=gateway)


async def test_the_webui_receives_the_whole_text_after_drops() -> None:
    bus = MessageBus(outbound_maxsize=4)
    dispatcher = WebSocketDispatcher(Config(), bus)
    channel = _ws_channel(bus)
    dispatcher.channels = {"websocket": channel}
    ws = AsyncMock()
    channel._attach(ws, "default")

    # Il produttore corre più del dispatcher: la coda si riempie e scarta.
    for word in WORDS:
        bus.try_publish_outbound(_delta(word))
    bus.try_publish_outbound(_end())
    publishing = asyncio.create_task(bus.publish_outbound(_final()))

    task = asyncio.create_task(dispatcher._dispatch_outbound())
    try:
        await publishing
        await wait_until(
            lambda: any(
                json.loads(c.args[0]).get("event") == "stream_end"
                for c in ws.send.await_args_list
            ),
            timeout=2.0,
        )
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    frames = [json.loads(c.args[0]) for c in ws.send.await_args_list]
    shown = "".join(f["text"] for f in frames if f["event"] == "delta")
    assert len(shown) < len(FULL)  # i delta sono davvero stati scartati
    end = next(f for f in frames if f["event"] == "stream_end")
    assert end["text"] == FULL
