"""Le parole dell'officina passano dall'i18n, anche quelle di ripiego.

WJ18 della terza revisione (26/09/2026): ``'New session started.'`` come testo
di un confine senza parole del server, un ``|| 'Close'`` morto (``i18n.t``
torna la chiave, mai un falso), e in ``shared/provider-brand.js`` le due
etichette che non sono nomi propri — ``'Unknown'`` e ``'Anthropic
Compatible'`` — lette in inglese da Info sessione. Ora hanno una chiave, e
``brandLabel`` la traduce.
"""

from __future__ import annotations

import json

from support.js_harness import ASSETS, locale, member, requires_node, run_js

pytestmark = requires_node

CHAT_SRC = (ASSETS / "mobile-chat.js").read_text(encoding="utf-8")
BRAND = (ASSETS / "shared" / "provider-brand.js").as_uri()


def test_the_brand_labels_that_are_not_names_are_translated() -> None:
    it = locale("it")
    out = run_js(
        f"const {{ brandLabel, getProviderBrand }} = await import('{BRAND}');\n"
        f"const IT = {json.dumps(it)};\n"
        """
      const t = (key) => key.split('.').reduce((o, k) => o?.[k], IT) ?? key;
      console.log(JSON.stringify([
        brandLabel(getProviderBrand('anthropic'), t),
        brandLabel(getProviderBrand(''), t),
        brandLabel(getProviderBrand('openai'), t),
        brandLabel(getProviderBrand('mio_provider'), t),
        brandLabel(getProviderBrand('anthropic'), (k) => k),
        getProviderBrand('anthropic').label,
      ]));
    """
    )
    labels = json.loads(out)
    assert labels == [
        it["provider"]["anthropic"],
        it["provider"]["unknown"],
        "OpenAI",
        "mio_provider",
        "Anthropic Compatible",  # senza traduzione, il ripiego
        "Anthropic Compatible",  # il dato che `shortBrand` legge resta com'era
    ], labels


def test_the_session_boundary_fallback_is_a_key() -> None:
    body = member(CHAT_SRC, "_appendSessionBoundary")
    assert "i18n.t('chat.sessionStarted')" in body, body
    assert "New session started" not in body
    for loc in ("it", "en"):
        assert locale(loc)["chat"]["sessionStarted"].strip(), loc


def test_no_dead_english_fallback_after_a_translation() -> None:
    assert "|| 'Close'" not in CHAT_SRC
