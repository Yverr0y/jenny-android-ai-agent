"""Go rifiuta ``name`` sui messaggi, e nessun altro provider deve perderlo.

``name`` è opzionale nello schema OpenAI e Jenny lo mette sui risultati dei tool
(``agent/runner.py``). OpenCode Go non lo ignora: risponde ``HTTP 400 ...
messages[N]: "name" is not supported by this endpoint``. Il guasto è tardivo e
sembra peggiore di quello che è — la prima richiesta del turno passa, e il turno
muore solo quando il modello usa un tool, cioè quasi sempre.

Come nel file sui header, metà di questi test guarda OpenCode e metà guarda
tutti gli altri: la riga tolta vive dentro il percorso comune a ogni provider
OpenAI-compat, quindi il modo in cui può far danno è togliere ``name`` a chi lo
vuole. Il corpo si legge da ``httpx.MockTransport``, cioè da quello che parte
davvero sul filo.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from jenny.providers.openai_compat_provider import OpenAICompatProvider
from jenny.providers.opencode import message_keys

GO_BASE = "https://opencode.ai/zen/go/v1"

_BODY = json.dumps({
    "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
}).encode()

# Una cronologia con un giro di tool dentro: è l'unica forma in cui ``name``
# compare, ed è la seconda richiesta del turno vero.
_HISTORY: list[dict[str, Any]] = [
    {"role": "user", "content": "che ore sono?"},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "call_1",
            "type": "function",
            "function": {"name": "clock", "arguments": "{}"},
        }],
    },
    {"role": "tool", "tool_call_id": "call_1", "name": "clock", "content": "18:30"},
]


def _capture(provider: OpenAICompatProvider) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_BODY, headers={"content-type": "application/json"})

    provider._http_client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    return seen


def _openai(api_base: str, **kwargs: Any) -> OpenAICompatProvider:
    return OpenAICompatProvider(api_key="k", api_base=api_base, default_model="m", **kwargs)


def _sent_messages(request: httpx.Request) -> list[dict[str, Any]]:
    return json.loads(request.content)["messages"]


class TestIlFiltro:
    """``message_keys`` è il gate, e guarda solo la base."""

    def test_su_opencode_toglie_name(self) -> None:
        assert "name" not in message_keys(GO_BASE, frozenset({"role", "content", "name"}))

    def test_altrove_non_tocca_niente(self) -> None:
        allowed = frozenset({"role", "content", "name"})
        assert message_keys("https://api.openai.com/v1", allowed) == allowed

    def test_senza_base_non_tocca_niente(self) -> None:
        allowed = frozenset({"role", "content", "name"})
        assert message_keys(None, allowed) == allowed

    def test_lascia_intatte_le_altre_chiavi(self) -> None:
        # Togliere una chiave di troppo romperebbe la correlazione dei tool.
        assert message_keys(GO_BASE, frozenset({"role", "content", "tool_call_id", "name"})) == (
            frozenset({"role", "content", "tool_call_id"})
        )


class TestVersoOpenCode:

    async def test_il_risultato_del_tool_parte_senza_name(self) -> None:
        provider = _openai(GO_BASE)
        seen = _capture(provider)
        await provider.chat(list(_HISTORY))
        tool_msg = _sent_messages(seen[0])[-1]
        assert tool_msg["role"] == "tool"
        assert "name" not in tool_msg

    async def test_il_tool_call_id_resta(self) -> None:
        # È lui la correlazione vera: senza, togliere ``name`` sarebbe una perdita.
        provider = _openai(GO_BASE)
        seen = _capture(provider)
        await provider.chat(list(_HISTORY))
        sent = _sent_messages(seen[0])
        assert sent[-1]["tool_call_id"] == sent[-2]["tool_calls"][0]["id"]

    async def test_il_nome_della_funzione_nel_tool_call_resta(self) -> None:
        # ``function.name`` non è una chiave di messaggio: se sparisse, il modello
        # non saprebbe più quale tool ha chiamato.
        provider = _openai(GO_BASE)
        seen = _capture(provider)
        await provider.chat(list(_HISTORY))
        assert _sent_messages(seen[0])[-2]["tool_calls"][0]["function"]["name"] == "clock"

    async def test_la_cronologia_del_chiamante_non_viene_toccata(self) -> None:
        provider = _openai(GO_BASE)
        _capture(provider)
        history = [dict(m) for m in _HISTORY]
        await provider.chat(history)
        assert history[-1]["name"] == "clock"


class TestVersoGliAltri:
    """Il cuore: fuori da OpenCode ``name`` continua a partire."""

    async def test_openai_diretto_riceve_name(self) -> None:
        provider = _openai("https://api.openai.com/v1")
        seen = _capture(provider)
        await provider.chat(list(_HISTORY))
        assert _sent_messages(seen[0])[-1]["name"] == "clock"

    async def test_deepseek_riceve_name(self) -> None:
        provider = _openai("https://api.deepseek.com")
        seen = _capture(provider)
        await provider.chat(list(_HISTORY))
        assert _sent_messages(seen[0])[-1]["name"] == "clock"

    async def test_un_gateway_locale_riceve_name(self) -> None:
        provider = _openai("http://127.0.0.1:1234/v1")
        seen = _capture(provider)
        await provider.chat(list(_HISTORY))
        assert _sent_messages(seen[0])[-1]["name"] == "clock"
