"""AC5 della terza revisione: un surrogato UTF-16 isolato non avvelena la sessione.

``json.loads`` accetta ``"\\ud83d"`` — metà di un'emoji, quel che resta di un frame
tagliato nel mezzo — e ne fa una stringa Python con un code point che in UTF-8 non
esiste. Finita in un messaggio, faceva fallire **ogni** ``SessionManager.save``
da lì in poi: anche i turni puliti rispondevano con l'errore generico, fino al
riavvio. Ora il testo si ripulisce all'ingresso (U+FFFD al posto del surrogato), e
``save`` regge comunque se un surrogato arriva da un'altra porta.
"""

from __future__ import annotations

import json

from jenny.bus.events import InboundMessage
from jenny.providers.base import LLMResponse
from jenny.session.manager import SessionManager, scrub_lone_surrogates
from tests.support.agent import make_loop, make_provider

KEY = "unified:default"
GENERIC_ERROR = "Sorry, I encountered an error."


async def test_the_turns_after_a_lone_surrogate_still_work(tmp_path):
    provider = make_provider()

    async def chat(**_kw):
        return LLMResponse(content="ok")

    provider.chat_with_retry = chat
    provider.chat_stream_with_retry = chat
    loop = make_loop(tmp_path, provider=provider)
    published: list[str] = []
    original = loop.bus.publish_outbound

    async def capture(message):
        published.append(message.content)
        await original(message)

    loop.bus.publish_outbound = capture
    cut = json.loads('"guarda \\ud83d"')  # un frame tagliato dentro un'emoji
    for content in (cut, "messaggio normale", "un altro"):
        await loop._dispatch(InboundMessage(channel="websocket", sender_id="u",
                                            chat_id="default", content=content))

    assert GENERIC_ERROR not in published
    reloaded = SessionManager(tmp_path).get_or_create(KEY)
    users = [m["content"] for m in reloaded.messages if m.get("role") == "user"]
    assert any("guarda �" in str(c) for c in users)
    assert any("un altro" in str(c) for c in users)


def test_save_survives_a_surrogate_that_came_from_elsewhere(tmp_path):
    sessions = SessionManager(tmp_path)
    session = sessions.get_or_create(KEY)
    session.add_message("assistant", "mezza emoji \ud83d dal modello")
    session.metadata["nota"] = {"testo": "anche qui \udc00"}

    sessions.save(session)

    reloaded = SessionManager(tmp_path).get_or_create(KEY)
    assert reloaded.messages[0]["content"] == "mezza emoji � dal modello"
    assert reloaded.metadata["nota"] == {"testo": "anche qui �"}


def test_scrub_leaves_real_emoji_alone():
    assert scrub_lone_surrogates("ciao 😀 \ud83d") == "ciao 😀 �"
