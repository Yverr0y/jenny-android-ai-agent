"""Un volo della mascotte flottante non lascia due stati sbagliati dietro di sé.

- **la taglia cambiata in volo non arrivava mai**: ``applyMascotSize`` in volo
  esce (la fisica è costruita col lato di partenza) e il KDoc prometteva che
  «il volo successivo nasce con quella» — ma nessuno la applicava: la finestra
  restava della taglia vecchia, e la maniglia, che si misura su quella nuova,
  non combaciava più con lei;
- **l'attesa di una risposta sopravviveva al volo**: ``startFlight`` annullava
  il timeout ma non ``waitingForReply``. Se la risposta poi non arrivava,
  restava acceso per sempre — faccia che pensa, ``armHold`` spento.

Il Kotlin non gira in CI: il contratto sul sorgente ridotto al solo codice.
"""

from __future__ import annotations

from support.kotlin_source import function_body, read_code


def _code() -> str:
    return read_code("FloatingOverlayController")


def test_a_size_change_in_flight_is_remembered() -> None:
    body = function_body(_code(), "applyMascotSize")
    guard = body[: body.index("return") + len("return")]
    assert "flight != null" in guard
    assert "sizePendingAfterFlight = true" in guard, "in volo la taglia va segnata in sospeso"
    assert "sizePendingAfterFlight = false" in body[len(guard):]


def test_the_landing_applies_the_pending_size() -> None:
    body = function_body(_code(), "endFlight")
    assert body.index("flight = null") < body.index("applyMascotSize(ctx)"), (
        "applyMascotSize esce in volo: va chiamata dopo aver chiuso il volo"
    )
    assert "if (sizePendingAfterFlight)" in body
    # Senza cambio resta la ricollocazione di sempre.
    assert "setGrip(ctx, arena = false)" in body


def test_a_flight_ends_the_wait_for_a_reply() -> None:
    body = function_body(_code(), "startFlight")
    assert "cancelTimeout()" in body
    assert "waitingForReply = false" in body, (
        "il volo annulla il timeout: senza spegnere anche l'attesa resta accesa per sempre"
    )
    assert body.index("waitingForReply = false") < body.index("FloatingFlight(")


def test_detach_forgets_a_pending_size() -> None:
    body = function_body(_code(), "detach")
    assert "sizePendingAfterFlight = false" in body
