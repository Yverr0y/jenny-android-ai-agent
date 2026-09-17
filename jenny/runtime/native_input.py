"""Ingresso del testo dell'utente dalle superfici native di Android.

Rovescio di ``jenny/runtime/notifier.py``: quello è l'uscita verso la tendina
delle notifiche, questo è l'ingresso dalla stessa tendina — la risposta rapida
(``RemoteInput``) che l'utente scrive senza aprire l'app.

**Il testo non prende una strada nuova.** Diventa un ``InboundMessage`` su un
canale utente come gli altri, e da lì in poi tutto il resto esiste già: la
risoluzione della session key manda ogni canale sulla conversazione unica
(:func:`jenny.session.keys.session_key_for_channel`), il coordinatore della
vista WebUI fa l'eco del messaggio in chat, e il dispatcher proietta la risposta
sul transcript. Quello che si scrive dalla tendina e la risposta che ne segue
finiscono quindi nella stessa conversazione di tutto il resto, e la memoria di
Dream copre anche quei turni.

**Come entra Kotlin.** Con la stessa grammatica di ``power.on_wake_tick``: da un
thread di lavoro JNI (mai dal main — l'attraversamento Chaquopy può restare
bloccato quanto il GIL resta preso da un turno in corso) chiama
``on_native_text(text, source)``. Da lì l'unica cosa lecita è
``loop.call_soon_threadsafe``: la pubblicazione è una coroutine e deve girare
sul loop del gateway, non sul thread chiamante. Toccare la coda direttamente da
quel thread sembrerebbe funzionare e perderebbe messaggi, perché non passerebbe
dal selector su cui il loop è bloccato.

**Una superficie, un canale.** La mappa ``_CHANNEL_BY_SOURCE`` è l'unico punto
in cui una sorgente nativa diventa un nome di canale, ed è chiusa: una sorgente
che non è là dentro viene rifiutata invece di fabbricare un canale che il
dispatcher non conosce. Il motivo è lo stesso per cui
``session_key_for_channel`` tiene un elenco chiuso di forme riconosciute — qui
il chiamante è codice nostro, ma la regola che vale è che un nome di canale non
si accetta da fuori.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from loguru import logger

from jenny.bus.events import NOTIFICATION_CHANNEL, InboundMessage

if TYPE_CHECKING:
    from jenny.bus.queue import MessageBus

# Chiave dei metadata che dice da quale superficie è arrivato il testo. Oggi c'è
# una sola sorgente e il canale la identifica già; la chiave esiste perché il
# canale dice *dove torna la risposta* e questa dice *da dove è entrata la
# domanda* — due domande diverse che oggi hanno la stessa risposta.
NATIVE_SOURCE_KEY = "_native_source"

# La sorgente "risposta dalla tendina". Stringa condivisa con Kotlin
# (``ReplyReceiver`` → ``GatewayService.deliverNativeText``): è un valore di
# protocollo, non un'etichetta.
SOURCE_NOTIFICATION = "notification"

# Sorgente → canale di consegna della risposta. Elenco chiuso: v. il docstring.
_CHANNEL_BY_SOURCE: dict[str, str] = {
    SOURCE_NOTIFICATION: NOTIFICATION_CHANNEL,
}

# ``chat_id`` dei messaggi che entrano da qui. La session key non lo guarda
# (tutto converge su ``unified:default``), quindi serve solo a leggersi nei log
# e a distinguere le impronte anti-duplicato del dispatcher.
NATIVE_CHAT_ID = "shade"

# Tetto duro sul testo accettato. È una risposta scritta col pollice in una
# casella di una riga, non un'interfaccia per saghe: oltre il tetto è quasi
# sempre un incolla accidentale, e rifiutarlo è più onesto che troncarlo e
# rispondere a metà domanda.
MAX_TEXT_CHARS = 2000

# Loop e bus del gateway corrente. Globali di modulo e non stato di un oggetto,
# per lo stesso motivo di ``power._WAKE_LOOP``: il chiamante è Kotlin via
# Chaquopy da un thread JNI, con in mano solo il nome del modulo.
_LOOP: asyncio.AbstractEventLoop | None = None
_BUS: Any = None

# I task di pubblicazione vanno tenuti referenziati fino al completamento:
# asyncio tiene solo weakref e il GC può cancellarli a metà. Stessa rete di
# ``notifier._TASKS``.
_TASKS: set[asyncio.Task[Any]] = set()


def reset_native_input() -> None:
    """Slega loop e bus a un nuovo start del gateway.

    Simmetrico a ``power.reset_power_state`` e chiamato dallo stesso posto
    (``android_entry.run_gateway``, prima del nuovo event loop): i riferimenti
    del giro precedente puntano a un loop morto, e un ``call_soon_threadsafe``
    su quello solleverebbe — o peggio, accoderebbe per nessuno.
    """
    global _LOOP, _BUS
    _LOOP = None
    _BUS = None
    # I task rimasti appartengono al loop morto: nessuno li completerà e
    # tenerli referenziati terrebbe in vita quel loop. Si lasciano andare.
    _TASKS.clear()


def bind_native_input(bus: "MessageBus") -> bool:
    """Aggancia il loop corrente al bus e abilita l'ingresso nativo.

    Da chiamare **dal** loop del gateway (``GatewayContainer.run``, come i push
    di power): ``get_running_loop`` è l'unico momento in cui siamo certi di
    essere dentro quel loop — Kotlin entrerà da un thread JNI, dove non esiste.
    Ritorna ``True`` se l'ingresso è davvero aperto. Senza bus non lo è, e lo
    dice invece di lasciare un log che dichiara agganciato ciò che non lo è: in
    produzione il bus esiste sempre a questo punto (lo crea ``_build``), quindi
    un ``False`` qui è un guasto d'avvio da leggere, non un caso previsto.
    """
    global _LOOP, _BUS
    if bus is None:
        logger.warning("Native input NOT bound: no message bus")
        return False
    _LOOP = asyncio.get_running_loop()
    _BUS = bus
    logger.info("Native input bound to the gateway bus")
    return True


def _clean(text: str | None) -> str:
    """Testo normalizzato, o stringa vuota se non c'è niente da consegnare."""
    return (text or "").strip()


def _accept(text: str) -> bool:
    """``True`` se *text* è pubblicabile. Validazione sincrona, senza effetti."""
    return bool(text) and len(text) <= MAX_TEXT_CHARS


def _schedule(bus: Any, channel: str, text: str, source: str) -> None:
    """Crea il task di pubblicazione. Gira **sul** loop, non sul thread JNI.

    Il task si crea qui e non nel chiamante per una ragione precisa: costruire
    la coroutine di là e poi non riuscire ad accodarla lascerebbe un oggetto
    coroutine mai awaitato — un ``RuntimeWarning`` a carico di chi non c'entra,
    e nel percorso d'errore, cioè quello che si legge peggio.
    """
    task = asyncio.get_running_loop().create_task(_publish(bus, channel, text, source))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


async def _publish(bus: Any, channel: str, text: str, source: str) -> None:
    """Costruisce l'``InboundMessage`` e lo mette sul bus.

    ``publish_inbound`` fa backpressure da solo (coda limitata): se il gateway è
    sommerso, questo task attende il proprio turno invece di scartare.
    """
    msg = InboundMessage(
        channel=channel,
        sender_id="user",
        chat_id=NATIVE_CHAT_ID,
        content=text,
        metadata={NATIVE_SOURCE_KEY: source},
    )
    await bus.publish_inbound(msg)
    logger.info("Native text published (source={}, chars={})", source, len(text))


def on_native_text(text: str, source: str = SOURCE_NOTIFICATION) -> bool:
    """Riceve il testo da una superficie nativa. Chiamata da Kotlin (thread JNI).

    **Mai solleva verso Kotlin** — lo stesso contratto di ``power.on_wake_tick``.
    Ritorna ``False`` quando il testo non può arrivare a destinazione: gateway
    non agganciato (ancora in avvio, loop morto, reset), sorgente sconosciuta,
    testo vuoto o oltre il tetto.

    ``True`` significa soltanto "accettato e in viaggio verso il bus": la
    risposta dell'agente arriverà dopo, sul suo tempo, e per la tendina torna in
    superficie come nuovo alert (``NotificationChannel``).

    A differenza di un tick di sveglia, un ``False`` qui **non** è un esito
    innocuo: il tick perso lo recupera il giro successivo del cron, le parole
    dell'utente no. È il chiamante Kotlin a doverci riprovare, e a dirlo se non
    ce la fa.
    """
    loop = _LOOP
    bus = _BUS
    if loop is None or bus is None or loop.is_closed():
        logger.info("Native text dropped: no gateway bound yet (source={})", source)
        return False
    channel = _CHANNEL_BY_SOURCE.get(source)
    if channel is None:
        logger.warning("Native text rejected: unknown source {!r}", source)
        return False
    clean = _clean(text)
    if not _accept(clean):
        logger.warning(
            "Native text rejected (source={}, chars={}, max={})",
            source, len(clean), MAX_TEXT_CHARS,
        )
        return False
    try:
        loop.call_soon_threadsafe(_schedule, bus, channel, clean, source)
    except RuntimeError:
        # Loop chiuso fra il controllo e la chiamata: nessun destinatario.
        logger.opt(exception=True).warning("Native text could not reach the event loop")
        return False
    return True
