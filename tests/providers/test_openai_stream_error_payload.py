"""Un ``{"error": ...}`` dentro uno stream Chat Completions è un errore.

Lo status della risposta era 200: il gateway (OpenRouter, o un proxy davanti a un
modello sovraccarico) scrive l'errore come chunk SSE. Il ramo Chat Completions lo
scartava: ``finish_reason="stop"`` col testo arrivato fin lì, o vuoto, e nessun
retry (PC2 della terza revisione, tre casi riprodotti). Qui gli stessi tre casi.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from jenny.providers.openai_compat_provider import OpenAICompatProvider
from jenny.providers.retry_policy import is_transient_response

MESSAGES = [{"role": "user", "content": "x"}]


def _d(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


HALF = _d({"choices": [{"delta": {"content": "Metà risposta"}}]})
OK = (
    _d({"choices": [{"delta": {"content": "ok"}}]})
    + _d({"choices": [{"delta": {}, "finish_reason": "stop"}]})
    + "data: [DONE]\n\n"
)


def _provider(*bodies: str) -> tuple[OpenAICompatProvider, dict]:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        body = bodies[min(calls["n"], len(bodies) - 1)]
        calls["n"] += 1
        return httpx.Response(200, content=body.encode())

    provider = OpenAICompatProvider(
        api_key="k", api_base="https://openrouter.ai/api/v1", default_model="x/y",
    )
    provider._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return provider, calls


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("jenny.providers.base.asyncio.sleep", _sleep)


async def _delta(_text: str) -> None:
    await asyncio.sleep(0)


async def test_error_with_choices_mid_stream_keeps_the_partial_text() -> None:
    provider, calls = _provider(HALF + _d({
        "error": {"code": 502, "message": "Provider returned error"},
        "choices": [{"delta": {"content": ""}, "finish_reason": "error"}],
    }))
    response = await provider.chat_stream_with_retry(messages=MESSAGES, on_content_delta=_delta)
    assert response.finish_reason == "error"
    assert response.error_status_code == 502
    assert "Provider returned error" in (response.content or "")
    assert response.partial_content == "Metà risposta"
    assert is_transient_response(response)
    # Il testo era già sullo schermo: non si ritenta (come per ogni altro errore
    # arrivato dopo l'output), ma l'errore non si perde.
    assert calls["n"] == 1


async def test_error_without_choices_mid_stream_is_not_lost() -> None:
    provider, _ = _provider(HALF + _d({
        "error": {"code": "server_error", "message": "upstream overloaded"},
    }))
    response = await provider.chat_stream(messages=MESSAGES)
    assert response.finish_reason == "error"
    assert "upstream overloaded" in (response.content or "")
    assert response.partial_content == "Metà risposta"
    assert is_transient_response(response)


async def test_error_before_any_output_is_retried() -> None:
    provider, calls = _provider(_d({"error": {"code": 529, "message": "Overloaded"}}), OK)
    response = await provider.chat_stream_with_retry(messages=MESSAGES, on_content_delta=_delta)
    assert calls["n"] == 2
    assert response.finish_reason == "stop"
    assert response.content == "ok"


async def test_a_permanent_error_is_not_retried() -> None:
    provider, calls = _provider(
        _d({"error": {"code": 401, "message": "No auth credentials found"}}), OK,
    )
    response = await provider.chat_stream_with_retry(messages=MESSAGES, on_content_delta=_delta)
    assert calls["n"] == 1
    assert response.finish_reason == "error"
    assert not is_transient_response(response)
