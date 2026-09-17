"""Test per ``jenny/channels/notification.py`` (la tendina come canale).

Il bridge Chaquopy non esiste fuori dal telefono: qui si sostituisce
``post_alert`` e si guarda **con che cosa** viene chiamato, più i due gate che
tengono la tendina pulita (eventi di coordinamento, messaggi vuoti).
"""

from __future__ import annotations

from typing import Any

import pytest

from jenny.bus.events import NOTIFICATION_CHANNEL, OutboundMessage
from jenny.channels import notification as nc
from jenny.channels.notification import REPLY_THREAD_TAG, NotificationChannel


class _Spy:
    def __init__(self, result: bool = True) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None, str | None]] = []
        self.result = result

    async def __call__(self, content, metadata, *, thread=None):
        self.calls.append((content, metadata, thread))
        return self.result


@pytest.fixture
def spy(monkeypatch) -> _Spy:
    s = _Spy()
    monkeypatch.setattr(nc, "post_alert", s)
    return s


def _msg(content: str = "ecco fatto", **meta: Any) -> OutboundMessage:
    return OutboundMessage(
        channel=NOTIFICATION_CHANNEL, chat_id="shade", content=content, metadata=meta
    )


class TestContratto:
    def test_il_canale_si_chiama_come_la_costante_condivisa(self):
        assert NotificationChannel.name == NOTIFICATION_CHANNEL

    def test_niente_progress_ne_reasoning(self):
        """Il dispatcher legge questi tre attributi prima di instradare."""
        assert NotificationChannel.send_progress is False
        assert NotificationChannel.send_tool_hints is False
        assert NotificationChannel.show_reasoning is False

    def test_un_solo_tentativo(self):
        """``post_alert`` non solleva: un retry ripubblicherebbe l'alert."""
        assert NotificationChannel.send_max_retries == 1

    async def test_start_e_stop_non_fanno_niente(self):
        ch = NotificationChannel()
        assert await ch.start() is None
        assert await ch.stop() is None

    async def test_i_send_di_streaming_ritornano_lista_vuota(self):
        ch = NotificationChannel()
        assert await ch.send_delta("x") == []
        assert await ch.send_reasoning_delta("x") == []
        assert await ch.send_reasoning_end("x") == []
        assert await ch.send_file_edit_events("x") == []
        assert ch.discard_stream_buffer("x") is None


class TestSend:
    async def test_posta_sul_thread_unico(self, spy: _Spy):
        ch = NotificationChannel()
        assert await ch.send(_msg("ecco fatto")) == []

        (content, _meta, thread) = spy.calls[0]
        assert content == "ecco fatto"
        assert thread == REPLY_THREAD_TAG

    async def test_i_metadata_arrivano_interi(self, spy: _Spy):
        """``alert_fields`` ne ricava il titolo: non vanno persi per strada."""
        ch = NotificationChannel()
        await ch.send(_msg("ping", webui_turn_id="t1"))
        assert spy.calls[0][1]["webui_turn_id"] == "t1"

    async def test_il_contenuto_viene_ripulito(self, spy: _Spy):
        ch = NotificationChannel()
        await ch.send(_msg("  con spazi  "))
        assert spy.calls[0][0] == "con spazi"

    @pytest.mark.parametrize("content", ["", "   "])
    async def test_un_messaggio_vuoto_non_squilla(self, spy: _Spy, content: str):
        ch = NotificationChannel()
        assert await ch.send(_msg(content)) == []
        assert spy.calls == []

    async def test_gli_eventi_di_coordinamento_non_squillano(self, spy: _Spy):
        """Il caso vero è ``_turn_end``: non porta flag di streaming, quindi il
        dispatcher lo fa arrivare fin qui. Senza questo gate ogni fine turno
        farebbe suonare una notifica."""
        ch = NotificationChannel()
        await ch.send(_msg("", _turn_end=True))
        await ch.send(_msg("testo di servizio", _progress=True))
        await ch.send(_msg("eco", _user_echo=True))
        await ch.send(_msg("delta", _stream_delta=True))
        assert spy.calls == []

    async def test_un_alert_soppresso_non_e_un_errore(self, monkeypatch):
        """App in primo piano: ``post_alert`` ritorna False e il canale tace."""
        monkeypatch.setattr(nc, "post_alert", _Spy(result=False))
        ch = NotificationChannel()
        assert await ch.send(_msg("ciao")) == []

    async def test_i_media_non_bloccano_il_testo(self, spy: _Spy):
        """Un alert è testo: gli allegati restano in chat, il messaggio parte lo stesso."""
        msg = _msg("guarda qui")
        msg.media = ["/workspace/foto.png"]
        assert await NotificationChannel().send(msg) == []
        assert spy.calls[0][0] == "guarda qui"
