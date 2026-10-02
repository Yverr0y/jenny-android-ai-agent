"""La mascotte flottante torna quando il service rinasce con il gateway vivo.

``GatewayService.onDestroy`` smontava la mascotte con ``teardown()``, che
metteva anche ``enabled = false``. L'unico che lo rimette a ``true`` è Python
(``apply_floating_config``), all'avvio del gateway o a un cambio
d'impostazione. Ma il service può essere distrutto e ricreato con il thread del
gateway ancora vivo: ``startGateway`` vede il thread e non fa niente, Python non
ripassa di lì, e la mascotte restava sparita — con l'interruttore nelle
impostazioni che diceva «accesa».

Il Kotlin non gira in CI: il contratto si fissa sul sorgente ridotto al solo
codice (``support.kotlin_source``).
"""

from __future__ import annotations

import re

from support.kotlin_source import function_body, read_code


def _controller() -> str:
    return read_code("FloatingOverlayController")


def _service() -> str:
    return read_code("GatewayService")


def test_teardown_detaches_without_forgetting_the_wanted_state() -> None:
    body = function_body(_controller(), "teardown")
    assert "detach()" in body
    assert not re.search(r"\benabled\s*=", body), (
        "teardown non deve spegnere la volontà di Python: solo lui la riaccende"
    )


def test_visibility_requires_a_live_service() -> None:
    """La condizione che il vecchio teardown esprimeva spegnendo il flag: senza
    service, nessuna finestra che raccolga domande."""
    body = function_body(_controller(), "applyVisibility")
    assert re.search(
        r"val wanted = enabled && GatewayService\.isRunning && !MainActivity\.isInForeground",
        body,
    ), body


def test_a_recreated_service_puts_the_mascot_back() -> None:
    on_create = function_body(_service(), "onCreate")
    assert "FloatingOverlayController.onServiceStarted()" in on_create
    # Dopo startGateway, e sul ramo buono: il ramo che non riesce ad andare in
    # foreground esce con `return` prima, e lì la mascotte non deve tornare.
    assert on_create.index("startGateway()") < on_create.index(
        "FloatingOverlayController.onServiceStarted()"
    )
    early_exit = on_create.index("stopSelf()")
    assert on_create.index("return", early_exit) < on_create.index(
        "FloatingOverlayController.onServiceStarted()"
    )
    started = function_body(_controller(), "onServiceStarted")
    assert "applyVisibility()" in started


def test_the_service_flag_goes_down_before_the_teardown() -> None:
    """Se `isRunning` scendesse dopo, un `applyVisibility` in coda fra le due
    righe (l'app che va in background) rimonterebbe la finestra a service
    morente."""
    on_destroy = function_body(_service(), "onDestroy")
    assert on_destroy.index("isRunning = false") < on_destroy.index(
        "FloatingOverlayController.teardown()"
    )


def test_detach_stops_every_animator_before_the_views_go() -> None:
    """Il respiro è ``INFINITE`` e resta registrato presso l'AnimationHandler
    anche con la vista staccata: ``detach`` lo lasciava chiedere un fotogramma
    a ogni vsync finché il GC non raccoglieva la colonna, e uno scivolamento in
    corso finiva ricollocando viste appena tolte.
    """
    body = function_body(_controller(), "detach")
    removal = body.index("wm.removeView(v)")
    for stop in (
        "slide?.cancel()",
        "breath?.cancel()",
        "column?.animate()?.cancel()",
        "sendButton?.animate()?.cancel()",
    ):
        assert stop in body, f"detach non ferma {stop.split('?')[0]}"
        assert body.index(stop) < removal
    # `onAnimationEnd` dello scivolamento guarda `sliding`: va spento prima del
    # `cancel`, o ricolloca la colonna e fa ripartire il respiro.
    assert body.index("sliding = false") < body.index("slide?.cancel()")
    assert "breath = null" in body and "slide = null" in body
