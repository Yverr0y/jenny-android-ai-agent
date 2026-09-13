"""Hot-reload di provider e modello in ``GatewayContainer``.

La guardia di ``_on_settings_changed`` decide se il provider vivo va
ricostruito. Ha sbagliato due volte, e sempre per la stessa ragione: guardava
tre attributi dell'oggetto provider (modello, api_base, ``generation``) invece
di cio' che il factory legge dal config.

* la prima volta si perdeva ``max_tokens``/``temperature``/``reasoning_effort``;
* la seconda ``caBundle`` — issue #12. Una CA salvata restava inerte perche' il
  client della chat era quello di prima, mentre la sonda del catalogo modelli,
  costruita a ogni richiesta, la onorava: da fuori sembrava che la fiducia TLS
  arrivasse a un client e non all'altro.

Da qui i test: uno per il caso della CA, e uno che passa **su ogni campo** di
``ProviderConfig``, cosi' che il prossimo campo aggiunto non possa essere
dimenticato in silenzio.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from jenny.config.schema import Config, ProviderConfig, ProvidersConfig
from jenny.providers.base import GenerationSettings
from jenny.providers.factory import provider_fingerprint
from jenny.runtime.container import GatewayContainer

MODEL = "deepseek-v4-flash"


def _provider(model: str, generation: GenerationSettings, api_base: str = "https://api.test"):
    return SimpleNamespace(api_base=api_base, generation=generation, default_model=model)


def _config(model: str = MODEL, **provider_overrides: Any) -> Config:
    """Config di partenza: un provider attivo e i default dell'agente."""
    fields: dict[str, Any] = {
        "name": "p",
        "format": "openai_compat",
        "api_key": "k",
        "api_base": "https://api.test",
    }
    fields.update(provider_overrides)
    config = Config(
        providers=ProvidersConfig(providers=[ProviderConfig(**fields)], default=fields["name"]),
    )
    config.agents.defaults.model = model
    return config


@pytest.fixture
def container_with_agent():
    """Container con un agente finto, allineato a ``_config()``."""
    container = GatewayContainer.__new__(GatewayContainer)
    old_generation = GenerationSettings(temperature=0.1, max_tokens=8192)
    agent = SimpleNamespace(
        model=MODEL,
        provider=_provider(MODEL, old_generation),
        _apply_provider_switch=MagicMock(),
    )
    container._agent = agent
    container.provider = agent.provider
    # Lo stato che ``build()`` lascia dietro di se': l'impronta del config da
    # cui il provider vivo e' stato costruito.
    container._provider_fingerprint = provider_fingerprint(_config())
    return container, agent


def _patch_reload(
    monkeypatch: pytest.MonkeyPatch,
    *,
    config: Config,
    generation: GenerationSettings | None = None,
) -> None:
    # I moduli si importano qui e si patcha l'oggetto, non il target come stringa:
    # ``_on_settings_changed`` importa entrambi dentro la funzione, quindi con la
    # forma a stringa il test passa o falla in base a chi ha già importato
    # ``jenny.providers.factory`` prima di lui.
    from jenny.config import loader as config_loader
    from jenny.providers import factory as provider_factory

    gen = generation or GenerationSettings(temperature=0.1, max_tokens=8192)
    monkeypatch.setattr(config_loader, "load_config", lambda *a, **k: config)
    monkeypatch.setattr(
        provider_factory,
        "make_provider",
        lambda cfg, *a, **k: _provider(cfg.agents.defaults.model, gen),
    )


def test_generation_change_is_applied(container_with_agent, monkeypatch) -> None:
    container, agent = container_with_agent
    config = _config()  # modello invariato: cambiano solo i parametri
    config.agents.defaults.max_tokens = 4096
    _patch_reload(
        monkeypatch,
        config=config,
        generation=GenerationSettings(temperature=0.1, max_tokens=4096),
    )

    container._on_settings_changed()

    agent._apply_provider_switch.assert_called_once()
    assert agent._apply_provider_switch.call_args.kwargs["publish_update"] is False


def test_identical_settings_still_short_circuit(container_with_agent, monkeypatch) -> None:
    """La guardia resta: senza differenze non si ricostruisce niente."""
    container, agent = container_with_agent
    _patch_reload(monkeypatch, config=_config())

    container._on_settings_changed()

    agent._apply_provider_switch.assert_not_called()


def test_model_change_still_publishes_the_switch(container_with_agent, monkeypatch) -> None:
    """Un cambio di modello va annunciato; uno dei soli parametri no."""
    container, agent = container_with_agent
    _patch_reload(monkeypatch, config=_config(model="other-model"))

    container._on_settings_changed()

    agent._apply_provider_switch.assert_called_once()
    assert agent._apply_provider_switch.call_args.kwargs["publish_update"] is True


def test_ca_bundle_alone_rebuilds_the_provider(container_with_agent, monkeypatch) -> None:
    """Issue #12: una CA salvata deve raggiungere il client della chat.

    Modello, api_base e parametri di generazione restano identici — e' tutto
    cio' che la vecchia guardia guardava — quindi il provider restava quello di
    prima, costruito senza quella CA. Riprodotto sul Titan 2 il 13/09/2026:
    la sonda del catalogo modelli caricava la lista mentre la chat continuava a
    rispondere ``[SSL: CERTIFICATE_VERIFY_FAILED] ... unable to get local issuer
    certificate``, e bastava riavviare l'app per farla funzionare.
    """
    container, agent = container_with_agent
    _patch_reload(monkeypatch, config=_config(ca_bundle="uploads/ca.pem"))

    container._on_settings_changed()

    agent._apply_provider_switch.assert_called_once()
    assert agent._apply_provider_switch.call_args.kwargs["publish_update"] is False


# Un valore diverso da quello di ``_config()`` per **ogni** campo di
# ``ProviderConfig``. Il test sotto verifica che l'elenco sia completo: un campo
# nuovo fa fallire la suite finche' non gli si da' un valore qui, che e'
# esattamente il passaggio saltato quando ``caBundle`` e' stato aggiunto.
_CHANGED_FIELD_VALUES: dict[str, Any] = {
    "name": "altro",
    "format": "anthropic",
    "api_key": "k2",
    "api_base": "https://altro.test",
    "ca_bundle": "uploads/ca.pem",
    "extra_headers": {"X-Test": "1"},
    "extra_body": {"reasoning": {"effort": "high"}},
    "extra_query": {"api-version": "2026-01-01"},
    "api_type": "responses",
}


def test_every_provider_field_is_covered_by_the_fixture() -> None:
    """L'elenco qui sopra deve nominare tutti i campi, non quelli di ieri."""
    assert set(_CHANGED_FIELD_VALUES) == set(ProviderConfig.model_fields)


@pytest.mark.parametrize("field", sorted(_CHANGED_FIELD_VALUES))
def test_any_provider_field_change_rebuilds_the_provider(
    field: str, container_with_agent, monkeypatch
) -> None:
    """Ogni campo del provider deve far ricostruire il client, da solo."""
    container, agent = container_with_agent
    overrides: dict[str, Any] = {field: _CHANGED_FIELD_VALUES[field]}
    if field == "name":
        # ``default`` segue il nome: rinominare il provider attivo non deve
        # lasciare il container senza provider attivo per un motivo diverso.
        overrides["name"] = _CHANGED_FIELD_VALUES["name"]
    _patch_reload(monkeypatch, config=_config(**overrides))

    container._on_settings_changed()

    agent._apply_provider_switch.assert_called_once()


def test_context_window_change_is_applied(container_with_agent, monkeypatch) -> None:
    """La finestra di contesto viaggia con lo switch e non la guardava nessuno."""
    container, agent = container_with_agent
    config = _config()
    config.agents.defaults.context_window_tokens = 131072
    _patch_reload(monkeypatch, config=config)

    container._on_settings_changed()

    agent._apply_provider_switch.assert_called_once()
    assert agent._apply_provider_switch.call_args.args[2] == 131072


def test_a_failed_rebuild_leaves_the_fingerprint_alone(container_with_agent, monkeypatch) -> None:
    """Se il provider nuovo non si costruisce, il prossimo salvataggio ritenta."""
    from jenny.providers import factory as provider_factory

    container, agent = container_with_agent
    before = container._provider_fingerprint
    config = _config(ca_bundle="uploads/sparita.pem")
    _patch_reload(monkeypatch, config=config)

    def _boom(*a, **k):
        raise RuntimeError("CA bundle not found")

    monkeypatch.setattr(provider_factory, "make_provider", _boom)

    container._on_settings_changed()  # non solleva: logga e basta

    agent._apply_provider_switch.assert_not_called()
    assert container._provider_fingerprint == before


def test_fingerprint_is_stable_across_equal_configs() -> None:
    assert provider_fingerprint(_config()) == provider_fingerprint(_config())


def test_fingerprint_without_an_active_provider() -> None:
    """Nessun provider e' uno stato a se': uscirne conta come cambio."""
    empty = Config()
    assert provider_fingerprint(empty) != provider_fingerprint(_config())
