"""Test per ``jenny/runtime/native_input.py`` (ingresso dalla tendina).

Il chiamante vero è Kotlin da un thread JNI, e questo file lo imita: l'unica
prova che conta davvero è quella che entra da un thread che **non** è il loop,
perché è l'unica in cui un ``publish_inbound`` chiamato male perderebbe il
messaggio invece di consegnarlo.
"""

from __future__ import annotations

import asyncio
import pathlib

import pytest

from jenny.bus.events import NOTIFICATION_CHANNEL, InboundMessage
from jenny.runtime import native_input as ni
from jenny.session.keys import UNIFIED_SESSION_KEY


class _FakeBus:
    """Bus minimo: registra gli inbound e segnala l'arrivo."""

    def __init__(self) -> None:
        self.inbound: list[InboundMessage] = []
        self.arrived = asyncio.Event()

    async def publish_inbound(self, msg: InboundMessage) -> None:
        self.inbound.append(msg)
        self.arrived.set()


@pytest.fixture(autouse=True)
def _clean_state():
    """Ogni test parte e finisce slegato: i globali sono di modulo."""
    ni.reset_native_input()
    yield
    ni.reset_native_input()


async def _bound() -> _FakeBus:
    bus = _FakeBus()
    assert ni.bind_native_input(bus) is True
    return bus


class TestRifiuti:
    async def test_senza_bind_non_solleva_e_dice_no(self):
        assert ni.on_native_text("ciao") is False

    async def test_dopo_il_reset_non_riusa_il_loop_morto(self):
        await _bound()
        ni.reset_native_input()
        assert ni.on_native_text("ciao") is False

    @pytest.mark.parametrize("text", ["", "   ", "\n\t "])
    async def test_testo_vuoto(self, text: str):
        bus = await _bound()
        assert ni.on_native_text(text) is False
        assert bus.inbound == []

    async def test_oltre_il_tetto(self):
        bus = await _bound()
        assert ni.on_native_text("x" * (ni.MAX_TEXT_CHARS + 1)) is False
        assert bus.inbound == []

    async def test_il_tetto_e_incluso(self):
        bus = await _bound()
        assert ni.on_native_text("x" * ni.MAX_TEXT_CHARS) is True
        await asyncio.wait_for(bus.arrived.wait(), 2)
        assert len(bus.inbound[0].content) == ni.MAX_TEXT_CHARS

    async def test_sorgente_sconosciuta(self):
        """L'elenco delle sorgenti è chiuso: Kotlin non può inventare un canale."""
        bus = await _bound()
        assert ni.on_native_text("ciao", "overlay-che-non-esiste") is False
        assert bus.inbound == []

    async def test_il_tetto_si_misura_sul_testo_pulito(self):
        """Spazi in coda non devono far sforare un messaggio che ci sta."""
        bus = await _bound()
        assert ni.on_native_text("x" * ni.MAX_TEXT_CHARS + "   \n") is True
        await asyncio.wait_for(bus.arrived.wait(), 2)
        assert len(bus.inbound[0].content) == ni.MAX_TEXT_CHARS


class TestBind:
    async def test_senza_bus_non_dice_di_essere_agganciato(self):
        """Un log che dichiara agganciato ciò che non lo è costa una diagnosi."""
        assert ni.bind_native_input(None) is False
        assert ni.on_native_text("ciao") is False

    def test_il_gateway_lo_aggancia_all_avvio(self):
        """Il bind vive in ``GatewayContainer.run`` e nessun test lo esercita
        end-to-end: senza questa guardia, toglierlo lascerebbe la suite verde e
        la tendina muta sul telefono. Stessa forma di
        ``test_the_agent_is_handed_the_generic_hook``.
        """
        import inspect

        from jenny.runtime.container import GatewayContainer

        source = inspect.getsource(GatewayContainer.run)
        assert "bind_native_input(self.bus)" in source

    def test_il_gateway_lo_slega_a_ogni_riavvio(self):
        """``run_gateway`` riparte nello stesso processo: il loop del giro
        precedente è morto e i suoi riferimenti vanno buttati."""
        import inspect

        from jenny import android_entry

        source = inspect.getsource(android_entry)
        assert "reset_native_input()" in source


class TestConfineConKotlin:
    """Il punto in cui un rename rompe solo sul telefono.

    Kotlin raggiunge questo modulo per **nome**, attraverso Chaquopy: né il
    compilatore Kotlin né pyright vedono quel legame, e rinominare il modulo, la
    funzione o la stringa della sorgente lascerebbe tutto verde qui e muta la
    tendina là. Queste tre asserzioni sono l'unico posto in cui quel legame è
    controllato.
    """

    @staticmethod
    def _gateway_service() -> str:
        repo = pathlib.Path(__file__).resolve().parents[2]
        kt = repo / "android/app/src/main/java/com/flagdizero/jenny/GatewayService.kt"
        return kt.read_text(encoding="utf-8")

    def test_kotlin_chiama_questo_modulo(self):
        assert 'getModule("jenny.runtime.native_input")' in self._gateway_service()
        assert ni.__name__ == "jenny.runtime.native_input"

    def test_kotlin_chiama_questa_funzione(self):
        assert 'callAttr("on_native_text"' in self._gateway_service()
        assert callable(ni.on_native_text)

    def test_kotlin_passa_anche_il_filo(self):
        """Terzo argomento: il tag della notifica. Se qui e là divergono, la
        risposta finisce su un filo di ripiego e la seconda scheda torna."""
        assert '"on_native_text", text, "notification", sourceTag' in self._gateway_service()

    def test_la_sorgente_che_passa_kotlin_e_riconosciuta(self):
        """Una sorgente fuori elenco viene rifiutata: se le due stringhe
        divergono, ogni risposta dalla tendina viene scartata."""
        assert '"on_native_text", text, "notification"' in self._gateway_service()
        assert ni.SOURCE_NOTIFICATION in ni._CHANNEL_BY_SOURCE


class TestConsegna:
    async def test_caso_felice(self):
        bus = await _bound()
        assert ni.on_native_text("ricordamelo domani") is True
        await asyncio.wait_for(bus.arrived.wait(), 2)

        (msg,) = bus.inbound
        assert msg.channel == NOTIFICATION_CHANNEL
        assert msg.chat_id == ni.NATIVE_CHAT_ID
        assert msg.sender_id == "user"
        assert msg.content == "ricordamelo domani"
        assert msg.metadata[ni.NATIVE_SOURCE_KEY] == ni.SOURCE_NOTIFICATION

    async def test_atterra_sulla_conversazione_unica(self):
        """La ragione per cui questa funzionalità vale: stessa conversazione.

        Se questa asserzione cade, il testo scritto dalla tendina apre una
        sessione parallela — invisibile in chat e fuori dalla memoria di Dream.
        """
        bus = await _bound()
        ni.on_native_text("ciao")
        await asyncio.wait_for(bus.arrived.wait(), 2)
        assert bus.inbound[0].session_key == UNIFIED_SESSION_KEY

    async def test_da_un_thread_che_non_e_il_loop(self):
        """Il test che conta: è la condizione vera, Kotlin da un thread JNI.

        Da lì l'unica cosa lecita è ``call_soon_threadsafe``. Una versione che
        toccasse la coda direttamente passerebbe tutti gli altri test di questo
        file e perderebbe messaggi sul telefono.
        """
        bus = await _bound()
        ok = await asyncio.to_thread(ni.on_native_text, "scritto dal thread JNI")
        assert ok is True
        await asyncio.wait_for(bus.arrived.wait(), 2)
        assert bus.inbound[0].content == "scritto dal thread JNI"

    async def test_il_tag_del_filo_entra_nei_metadata(self):
        """È il tag della notifica da cui è partita la domanda: torna a valle e
        ci fa postare la risposta **su quella scheda**."""
        bus = await _bound()
        assert ni.on_native_text("ok", ni.SOURCE_NOTIFICATION, "cron:spesa") is True
        await asyncio.wait_for(bus.arrived.wait(), 2)
        assert bus.inbound[0].metadata[ni.NATIVE_THREAD_KEY] == "cron:spesa"

    @pytest.mark.parametrize("thread", [None, "", "   ", 42])
    async def test_un_filo_assente_non_lascia_una_chiave_vuota(self, thread):
        """Una chiave a ``None`` è una chiave che ogni lettore a valle deve
        imparare a ignorare: meglio non scriverla."""
        bus = await _bound()
        assert ni.on_native_text("ok", ni.SOURCE_NOTIFICATION, thread) is True
        await asyncio.wait_for(bus.arrived.wait(), 2)
        assert ni.NATIVE_THREAD_KEY not in bus.inbound[0].metadata

    async def test_il_tag_viene_ripulito(self):
        bus = await _bound()
        ni.on_native_text("ok", ni.SOURCE_NOTIFICATION, "  heartbeat \n")
        await asyncio.wait_for(bus.arrived.wait(), 2)
        assert bus.inbound[0].metadata[ni.NATIVE_THREAD_KEY] == "heartbeat"

    async def test_due_messaggi_di_fila_restano_due(self):
        bus = await _bound()
        assert ni.on_native_text("primo") is True
        assert ni.on_native_text("secondo") is True
        for _ in range(50):
            if len(bus.inbound) == 2:
                break
            await asyncio.sleep(0.005)
        assert [m.content for m in bus.inbound] == ["primo", "secondo"]

    async def test_il_rebind_sposta_il_bus(self):
        """Un gateway che riparte nello stesso processo non deve consegnare al vecchio."""
        vecchio = await _bound()
        nuovo = _FakeBus()
        ni.bind_native_input(nuovo)
        ni.on_native_text("dopo il riavvio")
        await asyncio.wait_for(nuovo.arrived.wait(), 2)
        assert vecchio.inbound == []
        assert nuovo.inbound[0].content == "dopo il riavvio"
