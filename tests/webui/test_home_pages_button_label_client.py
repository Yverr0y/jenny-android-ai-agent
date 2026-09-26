"""L'etichetta del bottone delle pagine del quaderno segue la lingua.

``#home-notebook-pages-open`` non ha testo: chi non vede il libro sente
l'``aria-label`` («Pagine del quaderno: orto, 3 pagine»). La scriveva solo il
conteggio delle pagine, cioe' un cambio di conversazione; ``_applyTranslations``
la saltava, e dopo un cambio di lingua restava nella precedente (terza
revisione, RC9).
"""

from __future__ import annotations

from support.home_dom import UI, requires_jsdom, run_home

pytestmark = requires_jsdom


def test_the_pages_button_label_is_translated_again() -> None:
    i18n_js = (UI / "assets" / "shared" / "i18n.js").as_posix()
    run_home(f"""
import assert from 'node:assert/strict';
import {{ boot, tick, locales, $ }} from './boot.mjs';
const {{ i18n }} = await import({i18n_js!r});
const app = await boot();
await app.showConversation('project:orto');
await tick(30);
const other = i18n.locale === 'it' ? 'en' : 'it';
await i18n.load(other);
i18n.locale = other;
app._applyTranslations();
const label = $('home-notebook-pages-open').getAttribute('aria-label');
assert.ok(label.startsWith(locales[other].home.notebookPages.open + ': orto'), label);
""")
